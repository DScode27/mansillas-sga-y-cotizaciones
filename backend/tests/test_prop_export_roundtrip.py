"""Property test P6: round-trip de la exportación de inventario (HU-11).

# Feature: carga-masiva-y-exportacion-inventario, Property 6

**Property 6: La exportación preserva el inventario consultado**

*Para toda* lista de inventario y todo formato admitido (`csv`, `xlsx`), el
archivo generado tiene exactamente una fila de datos por cada ítem del
inventario más la fila de encabezados, y al re-leer el archivo se recuperan los
mismos valores de cada columna del inventario (round-trip).

**Validates: Requirements 6.1, 7.1, 7.2, 7.4**

Estrategia
----------
La propiedad es sobre la lógica pura de `inventario_export_service.exportar`
(filas en memoria → bytes), por lo que el test no toca la base: genera con
Hypothesis listas arbitrarias de ítems de inventario y, para cada formato
admitido, exporta, vuelve a leer el archivo generado y compara.

Cada ítem es un dict con las claves de `ENCABEZADOS`. Los valores se generan con
`st.text` sobre un alfabeto imprimible (incluye la cadena vacía) para recorrer
un amplio espacio de entradas sin introducir caracteres de control que compliquen
la re-lectura. El servicio normaliza cada celda con `str` (y `None` → cadena
vacía) antes de escribirla; el oráculo del round-trip aplica esa misma
normalización a los valores esperados y a los leídos, de modo que la comparación
es exactamente la que garantiza el servicio.

Para los dos formatos se comprueba:

- El archivo tiene `len(filas) + 1` filas (encabezados + una por ítem) (R7.4).
- La primera fila es exactamente `ENCABEZADOS` (R7.4).
- Cada fila de datos recupera, columna por columna, el valor normalizado del
  ítem correspondiente (round-trip, R6.1/R7.1/R7.2).
- El `media_type` devuelto corresponde al formato (coherente con R7.2).
"""

from __future__ import annotations

import csv
import io

from hypothesis import given, settings
from hypothesis import strategies as st
from openpyxl import load_workbook

from app.services import inventario_export_service as svc

ENCABEZADOS = svc.ENCABEZADOS

# Alfabeto imprimible sin caracteres de control: evita romper la re-lectura de
# CSV/XLSX mientras se recorre un espacio amplio de valores. Incluye la cadena
# vacía (min_size=0) para cubrir celdas sin contenido.
_ALFABETO = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789 .,-_@áéíóúÁÉÍÓÚñÑ"
)
_valor = st.text(alphabet=_ALFABETO, min_size=0, max_size=30)

# Un ítem del inventario: un dict con una clave por cada encabezado. Se incluye
# también `id_silla` (lo trae la consulta real) para comprobar que `exportar`
# solo proyecta las columnas de `ENCABEZADOS` y lo ignora.
_item = st.builds(
    lambda valores, id_silla: {**dict(zip(ENCABEZADOS, valores)), "id_silla": id_silla},
    valores=st.lists(_valor, min_size=len(ENCABEZADOS), max_size=len(ENCABEZADOS)),
    id_silla=st.integers(min_value=1, max_value=10_000),
)

# Hasta 8 ítems por ejemplo, incluida la lista vacía (solo encabezados).
_inventario = st.lists(_item, min_size=0, max_size=8)


def _normalizar(valor: object) -> str:
    """Normaliza un valor como lo hace el servicio (`None` → "", resto `str`)."""
    return "" if valor is None else str(valor)


def _leer_csv(contenido: bytes) -> list[list[str]]:
    """Re-lee el CSV generado y devuelve todas sus filas como texto."""
    buffer = io.StringIO(contenido.decode("utf-8"))
    return [list(fila) for fila in csv.reader(buffer)]


def _leer_xlsx(contenido: bytes) -> list[list[str]]:
    """Re-lee el XLSX generado y devuelve todas sus filas normalizadas a texto.

    Las celdas vacías vuelven como `None` desde openpyxl; se normalizan igual que
    en la escritura para comparar contra el valor esperado normalizado.
    """
    libro = load_workbook(io.BytesIO(contenido))
    hoja = libro.active
    return [
        [_normalizar(celda) for celda in fila]
        for fila in hoja.iter_rows(values_only=True)
    ]


_LECTORES = {"csv": _leer_csv, "xlsx": _leer_xlsx}


# Feature: carga-masiva-y-exportacion-inventario, Property 6: La exportación preserva el inventario consultado
@settings(max_examples=100)
@given(inventario=_inventario, formato=st.sampled_from(("csv", "xlsx")))
def test_exportar_preserva_el_inventario_round_trip(inventario, formato):
    """Exportar y re-leer recupera encabezados y valores del inventario.

    _Requirements: 6.1, 7.1, 7.2, 7.4_
    """
    contenido, media_type = svc.exportar(inventario, formato)

    # El media_type corresponde al formato solicitado.
    assert media_type == svc.MEDIA_TYPES[formato]

    filas_leidas = _LECTORES[formato](contenido)

    # Encabezados + una fila de datos por ítem (R7.4).
    assert len(filas_leidas) == len(inventario) + 1
    assert filas_leidas[0] == list(ENCABEZADOS)

    # Round-trip columna por columna: cada fila de datos recupera los valores
    # normalizados del ítem correspondiente, en el orden de ENCABEZADOS.
    for item, fila_leida in zip(inventario, filas_leidas[1:]):
        esperada = [_normalizar(item.get(columna)) for columna in ENCABEZADOS]
        assert fila_leida == esperada
