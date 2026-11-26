"""Property test P5: el alcance de la consulta de inventario respeta el rol (HU-11).

# Feature: carga-masiva-y-exportacion-inventario, Property 5

**Property 5: El alcance de la consulta respeta el rol**

*Para todo* usuario autorizado y todo estado de la base, el inventario devuelto
contiene todas las empresas cuando el rol es `COMERCIAL_MANSILLAS`, y únicamente
filas con `id_empresa == user.empresa_id` cuando el rol es `ADMIN_CLIENTE`.

**Validates: Requirements 5.3, 5.4, 6.1, 6.2**

Estrategia
----------
Hypothesis genera un estado multiempresa arbitrario: una lista de empresas, cada
una con un número variable de sillas (incluido 0, para ejercitar empresas sin
inventario), y el rol con el que se consulta. Con la fábrica de `conftest.py` se
materializa cada empresa completa (empresa → sede → departamento → empleado →
comercial → técnico → visita) y sus sillas, registrando el `id_silla` de cada
una agrupado por empresa. La verificación opera directamente sobre la lógica del
service (`inventario_export_service.consultar_inventario`), usando la base
desechable como indica el diseño.

La propiedad se comprueba sobre el conjunto de `id_silla` devuelto:

- `COMERCIAL_MANSILLAS`: el alcance es todas las empresas, así que el conjunto
  devuelto es exactamente la unión de las sillas de todas las empresas (R5.3).
- `ADMIN_CLIENTE`: el alcance es solo `user.empresa_id`, así que el conjunto
  devuelto es exactamente las sillas de su propia empresa (R5.4). Cuando esa
  empresa no tiene sillas, el inventario es vacío (R6.2). Para el admin se elige
  siempre una de las empresas realmente creadas, de modo que `id_empresa` sea un
  valor válido del estado generado.

Además, cada ítem devuelto trae las columnas del inventario (empresa, sede,
departamento, empleado, cargo, código QR y estado), lo que cubre R6.1.

Las fixtures `db`/`fabrica` tienen ámbito de función y Hypothesis las reutiliza
entre ejemplos. Para que cada ejemplo parta de un estado limpio (y los conteos
por rol no arrastren sillas de ejemplos previos) se vacían las tablas de datos
con `TRUNCATE ... CASCADE` al inicio de cada ejemplo. Se suprime
`HealthCheck.function_scoped_fixture` porque esa reutilización es deliberada.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app.config import settings as app_settings
from app.services import inventario_export_service as svc

# Tablas de datos que se vacían al inicio de cada ejemplo para aislarlo. El orden
# respeta las dependencias de claves foráneas (las hijas antes que las padres),
# aunque `CASCADE` lo cubre igualmente.
_TABLAS_DATOS = (
    "silla",
    "visita",
    "empleado",
    "departamento",
    "sede",
    "usuario",
    "empresa",
)

# Cada empresa del estado generado trae un número de sillas (incluido 0 para
# ejercitar empresas sin inventario, R6.2). Entre 1 y 4 empresas por ejemplo.
_empresas = st.lists(
    st.integers(min_value=0, max_value=3),
    min_size=1,
    max_size=4,
)


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


def _crear_empresa_con_sillas(fabrica, cantidad_sillas: int) -> list[int]:
    """Crea una empresa completa con `cantidad_sillas` sillas.

    Devuelve la lista de `id_silla` creados para esa empresa. Se apoya en
    `fabrica.escenario()` (empresa → sede → departamento → empleado → comercial
    → técnico → visita) y añade las sillas con `fabrica.silla(...)`, cuyo
    `codigo_qr` lo asigna el disparador de la base (`SIC-00000001`...).
    """
    escenario = fabrica.escenario()
    ids_silla: list[int] = []
    for _ in range(cantidad_sillas):
        silla = fabrica.silla(escenario["visita"], escenario["empleado"])
        ids_silla.append(silla.id_silla)
    return ids_silla


# Feature: carga-masiva-y-exportacion-inventario, Property 5: El alcance de la consulta respeta el rol
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    cantidades=_empresas,
    rol=st.sampled_from(("COMERCIAL_MANSILLAS", "ADMIN_CLIENTE")),
    indice_admin=st.integers(min_value=0, max_value=3),
)
def test_alcance_de_la_consulta_respeta_el_rol(
    db,
    fabrica,
    cantidades,
    rol,
    indice_admin,
):
    """El inventario devuelto respeta el alcance por rol.

    Para un estado multiempresa arbitrario, el `COMERCIAL_MANSILLAS` ve las
    sillas de todas las empresas y el `ADMIN_CLIENTE` solo las de su propia
    empresa (vacío si no tiene sillas).

    _Requirements: 5.3, 5.4, 6.1, 6.2_
    """
    # Estado limpio por ejemplo: evita arrastrar sillas de ejemplos previos.
    _reset_datos(db)

    # Materializa el estado: por cada empresa, su id y el conjunto de sus sillas.
    empresas: list[dict] = []
    for cantidad in cantidades:
        escenario = fabrica.escenario()
        ids_silla = set()
        for _ in range(cantidad):
            silla = fabrica.silla(escenario["visita"], escenario["empleado"])
            ids_silla.add(silla.id_silla)
        empresas.append(
            {"id_empresa": escenario["empresa"].id_empresa, "sillas": ids_silla}
        )

    # Conjunto de todas las sillas del estado (alcance del comercial).
    todas_las_sillas = set().union(*(e["sillas"] for e in empresas))

    if rol == "ADMIN_CLIENTE":
        # El admin opera siempre sobre una empresa realmente creada.
        empresa_admin = empresas[indice_admin % len(empresas)]
        id_empresa = empresa_admin["id_empresa"]
        esperadas = empresa_admin["sillas"]
    else:
        id_empresa = None
        esperadas = todas_las_sillas

    inventario = svc.consultar_inventario(db, rol=rol, id_empresa=id_empresa)
    devueltas = {fila["id_silla"] for fila in inventario}

    # El alcance devuelto es exactamente el esperado para el rol (R5.3/R5.4/R6.2).
    assert devueltas == esperadas

    # Cada ítem devuelto trae todas las columnas del inventario (R6.1).
    for fila in inventario:
        for columna in ("id_silla", *svc.ENCABEZADOS):
            assert columna in fila
