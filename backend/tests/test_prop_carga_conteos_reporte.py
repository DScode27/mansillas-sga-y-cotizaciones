"""Property test P2: conteos del reporte y no-alteración por filas inválidas (HU-19).

# Feature: carga-masiva-y-exportacion-inventario, Property 2

**Property 2: Las filas válidas siempre se aplican e informan**

*Para todo* archivo con el Formato_Carga, tras procesarlo el total de filas
aplicadas es igual al número de filas sin Error_Fila, el total procesado es
igual al número de filas de datos, y procesadas = aplicadas + número de errores;
las filas inválidas no alteran la base de datos.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

Estrategia
----------
Hypothesis genera una lista de filas de datos, cada una marcada como válida o
inválida. Una fila inválida deja vacía alguna columna obligatoria del
Formato_Carga (`sede`, `departamento`, `nombre`, `cargo`); una fila válida trae
las cuatro obligatorias. El archivo `.xlsx` se construye en memoria con
`openpyxl` (incluida siempre la fila de encabezados), igual que harán las
pruebas de ejemplo, y se procesa con `carga_excel_service.procesar_carga`.

Para que cada ejemplo sea independiente pese a que las fixtures `db`/`fabrica`
tienen ámbito de función (Hypothesis las reutiliza entre ejemplos) y a que el
esquema impone `UNIQUE (id_empresa, documento)` y `correo` UNIQUE global, todos
los valores de las filas válidas llevan un sufijo tomado de un contador global
(`_SECUENCIA`): así cada fila válida crea sedes/departamentos/empleados nuevos y
nunca choca con los de otro ejemplo. El `ADMIN_CLIENTE` y su empresa se crean
una sola vez por test y se cachean en `_ESTADO`.

Verificaciones por ejemplo:

- `total_procesadas == número de filas de datos` (R3.1/R3.4).
- `total_aplicadas == número de filas sin Error_Fila` (R3.3).
- `total_procesadas == total_aplicadas + len(errores)` (invariante R3.4).
- Cada `Error_Fila` corresponde a una fila realmente inválida (R3.2) y su
  `fila` (1-based) cae dentro del rango de filas de datos.
- La base solo creció en `total_aplicadas` empleados de la empresa, y ningún
  empleado quedó con el `nombre` de una fila inválida: las filas inválidas no
  alteran la base (R3.2/R3.3).

Se suprime `HealthCheck.function_scoped_fixture` porque la reutilización de las
fixtures entre ejemplos es deliberada y cada ejemplo usa identidades únicas.
"""

from __future__ import annotations

import io
import itertools

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from openpyxl import Workbook
from sqlalchemy import func, select

from app.models import Empleado
from app.services import carga_excel_service as svc

# Encabezados del Formato_Carga en el orden en que los escribimos en el .xlsx.
ENCABEZADOS = ("sede", "departamento", "nombre", "cargo", "documento", "correo")

# Columnas obligatorias: dejar una vacía hace la fila inválida (R3.2).
OBLIGATORIAS = svc.COLUMNAS_OBLIGATORIAS

# Contador global: da un sufijo único a los valores de cada fila válida, de modo
# que cada ejemplo cree sedes/departamentos/empleados nuevos sin chocar con los
# `UNIQUE (id_empresa, documento)` / `correo UNIQUE` global del esquema.
_SECUENCIA = itertools.count(1)

# Admin/empresa creados una sola vez por ejecución del test (ver docstring).
_ESTADO: dict = {}


# Una fila generada: `valida` indica si trae todas las obligatorias; cuando es
# inválida, `columna_vacia` dice cuál obligatoria se deja en blanco.
_fila = st.fixed_dictionaries(
    {
        "valida": st.booleans(),
        "columna_vacia": st.sampled_from(OBLIGATORIAS),
    }
)

# Hasta 6 filas de datos por ejemplo (incluye el caso de 0 filas de datos, que
# `leer_filas` trataría como archivo vacío y por eso lo filtramos abajo).
_filas = st.lists(_fila, min_size=1, max_size=6)


def _construir_xlsx(especificaciones: list[dict]) -> tuple[bytes, list[dict]]:
    """Arma un `.xlsx` en memoria y devuelve (contenido, filas esperadas).

    Cada especificación se traduce a una fila del archivo. Las filas válidas
    reciben valores únicos (sufijo del contador global); las inválidas dejan
    vacía la columna obligatoria indicada. La lista de filas esperadas conserva,
    por cada fila, si es válida y el `nombre` que se escribió (para comprobar
    después que las inválidas no crearon empleados).
    """
    libro = Workbook()
    hoja = libro.active
    hoja.append(list(ENCABEZADOS))

    esperadas: list[dict] = []
    for especificacion in especificaciones:
        n = next(_SECUENCIA)
        valores = {
            "sede": f"Sede {n}",
            "departamento": f"Área {n}",
            "nombre": f"Empleado {n}",
            "cargo": f"Cargo {n}",
            "documento": f"DOC{n:09d}",
            "correo": f"empleado{n}@carga.local",
        }
        valida = especificacion["valida"]
        if not valida:
            # Dejar vacía una obligatoria hace la fila inválida (R3.2).
            valores[especificacion["columna_vacia"]] = None

        hoja.append([valores[columna] for columna in ENCABEZADOS])
        esperadas.append({"valida": valida, "nombre": valores["nombre"]})

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue(), esperadas


def _contar_empleados(db, id_empresa: int) -> int:
    """Número de empleados de la empresa (para medir la alteración de la base)."""
    return db.execute(
        select(func.count())
        .select_from(Empleado)
        .where(Empleado.id_empresa == id_empresa)
    ).scalar_one()


# Feature: carga-masiva-y-exportacion-inventario, Property 2: Las filas válidas siempre se aplican e informan
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(especificaciones=_filas)
def test_conteos_del_reporte_y_no_alteracion_por_filas_invalidas(
    db,
    fabrica,
    especificaciones,
):
    """Los conteos del reporte cuadran y las filas inválidas no tocan la base.

    _Requirements: 3.1, 3.2, 3.3, 3.4_
    """
    # Admin/empresa creados una sola vez por test y reutilizados entre ejemplos.
    admin = _ESTADO.get("admin")
    if admin is None:
        empresa = fabrica.empresa("Carga")
        admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)
        _ESTADO["admin"] = admin
    id_empresa = admin.id_empresa

    contenido, esperadas = _construir_xlsx(especificaciones)
    n_filas = len(esperadas)
    n_validas = sum(1 for e in esperadas if e["valida"])
    nombres_invalidos = {e["nombre"] for e in esperadas if not e["valida"]}

    empleados_antes = _contar_empleados(db, id_empresa)

    reporte = svc.procesar_carga(
        db,
        id_empresa=id_empresa,
        id_usuario=admin.id_usuario,
        nombre_archivo="carga.xlsx",
        contenido=contenido,
    )

    # R3.1/R3.4: todas las filas de datos se procesan.
    assert reporte.total_procesadas == n_filas
    # R3.3: las aplicadas son exactamente las filas sin Error_Fila.
    assert reporte.total_aplicadas == n_validas
    # R3.4 (invariante): procesadas = aplicadas + errores.
    assert reporte.total_procesadas == reporte.total_aplicadas + len(reporte.errores)
    assert len(reporte.errores) == n_filas - n_validas

    # R3.2: cada Error_Fila apunta a una fila realmente inválida y en rango.
    for error in reporte.errores:
        assert 1 <= error.fila <= n_filas
        assert not esperadas[error.fila - 1]["valida"]
        assert error.motivo

    # Las filas inválidas no alteran la base: solo crecieron los empleados de las
    # filas válidas (todas con identidad única, así que cada una crea un empleado
    # nuevo) y ningún empleado quedó con el nombre de una fila inválida (R3.2/R3.3).
    empleados_despues = _contar_empleados(db, id_empresa)
    assert empleados_despues - empleados_antes == n_validas

    if nombres_invalidos:
        creados_con_nombre_invalido = db.execute(
            select(func.count())
            .select_from(Empleado)
            .where(
                Empleado.id_empresa == id_empresa,
                Empleado.nombre.in_(nombres_invalidos),
            )
        ).scalar_one()
        assert creados_con_nombre_invalido == 0
