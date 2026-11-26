"""Property test P1: aislamiento multiempresa de la carga masiva (HU-19).

# Feature: carga-masiva-y-exportacion-inventario, Property 1

**Property 1: Aislamiento multiempresa de la carga**

*Para toda* carga masiva ejecutada por un `ADMIN_CLIENTE` y todo archivo de
entrada, todas las sedes, departamentos y empleados creados o actualizados
durante esa carga pertenecen a la `Empresa_Propia` del admin
(`id_empresa == user.empresa_id`), sin importar el contenido del archivo.

**Validates: Requirements 1.3, 1.4, 4.1, 4.3, 4.5**

Estrategia
----------
Hypothesis genera una lista arbitraria de filas (con valores libres para
`sede`, `departamento`, `nombre`, `cargo` y opcionales `documento`/`correo`,
incluyendo celdas vacías para ejercitar tanto filas válidas como inválidas) y
una columna espuria `id_empresa` con un valor cualquiera, para comprobar que el
service NUNCA toma la empresa del archivo. Con esas filas se construye un
`.xlsx` en memoria con `openpyxl` y se invoca directamente
`carga_excel_service.procesar_carga(...)` contra la base desechable.

La propiedad se verifica leyendo por SQL directo todas las sedes,
departamentos y empleados que existen tras la carga: cada uno debe tener
`id_empresa == admin.empresa_id`. Como un `ADMIN_CLIENTE` siempre opera sobre su
`empresa_id`, el único origen válido de filas es esa empresa, así que basta con
comprobar que no quedó ninguna fila de otra empresa.

Las fixtures `fabrica` y `db` son de ámbito de función y `@given` reejecuta el
cuerpo muchas veces. Para que cada ejemplo parta de un estado limpio (el
`empleado.correo` es UNIQUE global y acumular filas provocaría colisiones
espurias), al inicio de cada ejemplo se vacían las tablas de datos con
`TRUNCATE ... CASCADE` y se recrean las dos empresas (la propia del admin y una
empresa "ajena" que sirve de testigo de aislamiento). Se suprime
`HealthCheck.function_scoped_fixture` porque la reutilización de las fixtures
entre ejemplos es deliberada.
"""

from __future__ import annotations

import io

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from openpyxl import Workbook
from sqlalchemy import text

from app.config import settings as app_settings
from app.services import carga_excel_service

# Columnas del Formato_Carga más una columna espuria `id_empresa` que el archivo
# nunca debería poder usar para apuntar a otra empresa.
_ENCABEZADOS = ("sede", "departamento", "nombre", "cargo", "documento", "correo", "id_empresa")

_TABLAS_DATOS = ("empleado", "departamento", "sede", "carga_excel")

# Texto legible para celdas; `None` modela una celda vacía (fila potencialmente
# inválida por obligatoria ausente).
_celda_texto = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        min_size=0,
        max_size=20,
    ),
)

# Una fila es una tupla con un valor (o None) por cada encabezado.
_fila = st.tuples(
    _celda_texto,  # sede
    _celda_texto,  # departamento
    _celda_texto,  # nombre
    _celda_texto,  # cargo
    _celda_texto,  # documento
    _celda_texto,  # correo
    # id_empresa espuria: cualquier entero (incl. otra empresa) o vacío.
    st.one_of(st.none(), st.integers(min_value=-5, max_value=1_000_000)),
)

_filas = st.lists(_fila, min_size=1, max_size=8)


def _construir_xlsx(filas: list[tuple]) -> bytes:
    """Construye un `.xlsx` en memoria con los encabezados y las filas dadas."""
    libro = Workbook()
    hoja = libro.active
    hoja.append(list(_ENCABEZADOS))
    for fila in filas:
        hoja.append(["" if valor is None else valor for valor in fila])
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _empresas_de(db, tabla: str) -> set[int]:
    """Conjunto de `id_empresa` presentes en una tabla de datos (por SQL directo)."""
    db.expire_all()
    filas = db.execute(
        text(f"SELECT DISTINCT id_empresa FROM {app_settings.db_schema}.{tabla}")
    ).scalars().all()
    return set(filas)


def _reset_datos(db) -> None:
    """Vacía las tablas de datos para que cada ejemplo parta de cero."""
    db.rollback()
    db.execute(
        text(
            "TRUNCATE TABLE "
            + ", ".join(f"{app_settings.db_schema}.{t}" for t in _TABLAS_DATOS)
            + " RESTART IDENTITY CASCADE"
        )
    )
    db.commit()


# Feature: carga-masiva-y-exportacion-inventario, Property 1: Aislamiento multiempresa de la carga
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(filas=_filas)
def test_carga_solo_toca_la_empresa_del_admin(fabrica, db, filas):
    """Todo lo creado/actualizado por la carga queda en la empresa del admin.

    Independientemente del contenido del archivo (incluida una columna
    `id_empresa` espuria), tras procesar la carga ninguna sede, departamento ni
    empleado pertenece a una empresa distinta de la del `ADMIN_CLIENTE`.

    _Requirements: 1.3, 1.4, 4.1, 4.3, 4.5_
    """
    # Estado limpio por ejemplo: evita colisiones de `correo` UNIQUE global.
    _reset_datos(db)

    empresa_propia = fabrica.empresa("Propia")
    empresa_ajena = fabrica.empresa("Ajena")
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa_propia)

    contenido = _construir_xlsx(filas)

    carga_excel_service.procesar_carga(
        db,
        id_empresa=admin.id_empresa,
        id_usuario=admin.id_usuario,
        nombre_archivo="carga.xlsx",
        contenido=contenido,
    )

    # Toda sede/departamento/empleado existente pertenece a la empresa del admin;
    # la empresa ajena (testigo) nunca aparece en esas tablas.
    for tabla in ("sede", "departamento", "empleado"):
        empresas = _empresas_de(db, tabla)
        assert empresas <= {empresa_propia.id_empresa}, (
            f"La tabla {tabla} contiene filas de otra empresa: {empresas}"
        )
        assert empresa_ajena.id_empresa not in empresas
