"""Property test P3 (carga masiva): idempotencia del buscar-o-crear (HU-19).

# Feature: carga-masiva-y-exportacion-inventario, Property 3

**Property 3: Idempotencia del buscar-o-crear de sede y departamento**

*Para toda* empresa y todo conjunto de filas válidas, procesar el mismo archivo
dos veces no crea sedes ni departamentos duplicados: la cantidad de sedes y
departamentos tras la segunda carga es igual a la de después de la primera.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

Estrategia
----------
Hypothesis genera un conjunto no vacío de filas válidas del Formato_Carga (cada
una con `sede`, `departamento`, `nombre`, `cargo` no vacíos). Se construye el
`.xlsx` en memoria con `openpyxl` y se procesa DOS veces con el mismo contenido
mediante `carga_excel_service.procesar_carga`. Tras cada carga se cuentan las
sedes y los departamentos de la empresa; la propiedad exige que los conteos tras
la segunda carga sean iguales a los de la primera (los helpers reutilizan lo ya
creado en lugar de duplicarlo).

El test omite deliberadamente `documento`/`correo`: la identidad del empleado no
es relevante para esta propiedad (que mide solo sedes/departamentos) y evitar
`correo` previene choques con la restricción global `UNIQUE (correo)` entre
ejemplos reutilizados por Hypothesis.

Para aislar cada ejemplo se crea una empresa nueva (con su `ADMIN_CLIENTE`) en
cada ejecución del cuerpo `@given`; así los conteos se miden sobre un espacio
limpio y la reutilización de las fixtures de ámbito de función entre ejemplos no
acumula estado observable. Se suprime `HealthCheck.function_scoped_fixture`
porque esa reutilización es deliberada.
"""

from __future__ import annotations

import io

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from openpyxl import Workbook
from sqlalchemy import func, select

from app.models import Departamento, Sede
from app.services import carga_excel_service

# Texto no vacío tras recortar espacios: garantiza filas válidas (ninguna
# columna obligatoria queda en `None` tras `_normalizar`). Se evita el espacio en
# blanco al inicio/fin generando solo caracteres visibles ASCII.
_texto = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
    min_size=1,
    max_size=20,
)

# Conjunto pequeño de nombres de sede/departamento para forzar repeticiones
# frecuentes (el caso interesante del buscar-o-crear: muchas filas que apuntan a
# la misma sede/departamento no deben duplicarlos).
_nombre_estructura = st.sampled_from(["Sede A", "Sede B", "Sede C", "Area X", "Area Y"])


@st.composite
def _filas_validas(draw):
    """Genera entre 1 y 8 filas válidas del Formato_Carga.

    Cada fila trae `sede`, `departamento`, `nombre`, `cargo` no vacíos. Los
    nombres de sede y departamento se toman de un conjunto reducido para provocar
    repeticiones (varias filas hacia la misma sede/departamento).
    """
    cantidad = draw(st.integers(min_value=1, max_value=8))
    filas = []
    for _ in range(cantidad):
        filas.append(
            {
                "sede": draw(_nombre_estructura),
                "departamento": draw(_nombre_estructura),
                "nombre": draw(_texto),
                "cargo": draw(_texto),
            }
        )
    return filas


def _construir_xlsx(filas: list[dict[str, str]]) -> bytes:
    """Construye en memoria un `.xlsx` con el Formato_Carga y las filas dadas."""
    libro = Workbook()
    hoja = libro.active
    encabezados = ["sede", "departamento", "nombre", "cargo"]
    hoja.append(encabezados)
    for fila in filas:
        hoja.append([fila[columna] for columna in encabezados])
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _contar(db, modelo, columna_conteo, id_empresa: int) -> int:
    """Cuenta filas de `modelo` de la empresa (p. ej. sedes o departamentos)."""
    return db.execute(
        select(func.count()).select_from(modelo).where(modelo.id_empresa == id_empresa)
    ).scalar_one()


# Feature: carga-masiva-y-exportacion-inventario, Property 3: Idempotencia del buscar-o-crear de sede y departamento
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(filas=_filas_validas())
def test_procesar_dos_veces_no_duplica_sedes_ni_departamentos(
    fabrica,
    db,
    filas,
):
    """Procesar el mismo archivo dos veces no duplica sedes ni departamentos.

    Se crea una empresa nueva (y su `ADMIN_CLIENTE`) por ejemplo, se procesa el
    mismo `.xlsx` dos veces y se comprueba que la cantidad de sedes y de
    departamentos tras la segunda carga coincide con la de la primera.

    _Requirements: 4.1, 4.2, 4.3, 4.4_
    """
    empresa = fabrica.empresa("Carga P3")
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)
    id_empresa = empresa.id_empresa

    contenido = _construir_xlsx(filas)

    carga_excel_service.procesar_carga(
        db,
        id_empresa=id_empresa,
        id_usuario=admin.id_usuario,
        nombre_archivo="carga.xlsx",
        contenido=contenido,
    )
    sedes_primera = _contar(db, Sede, Sede.id_sede, id_empresa)
    departamentos_primera = _contar(db, Departamento, Departamento.id_departamento, id_empresa)

    carga_excel_service.procesar_carga(
        db,
        id_empresa=id_empresa,
        id_usuario=admin.id_usuario,
        nombre_archivo="carga.xlsx",
        contenido=contenido,
    )
    sedes_segunda = _contar(db, Sede, Sede.id_sede, id_empresa)
    departamentos_segunda = _contar(db, Departamento, Departamento.id_departamento, id_empresa)

    assert sedes_segunda == sedes_primera
    assert departamentos_segunda == departamentos_primera
