"""Property test P4: aislamiento multiempresa (HU-18).

# Feature: qr-publico-permisos-tickets, Property 4

**Property 4: Aislamiento multiempresa**

*Para todo* par de empresas distintas, un `ADMIN_CLIENTE` de la empresa A que
intente leer (`GET`) o modificar (`PUT`) el permiso de la empresa B recibe HTTP
403 "No autorizado para esta empresa" y el `permiso_qr` de B permanece sin
cambios.

**Validates: Requirements 2.5**

Estrategia
----------
Hypothesis genera la operación intentada (`GET` o `PUT`) y, para el `PUT`, el
nuevo valor de `permiso_qr` que el atacante intenta escribir sobre la empresa B
(se cubren tanto niveles válidos {1,2,3} como valores fuera de ese conjunto: la
autorización de empresa actúa ANTES de la validación del nivel, así que en ambos
casos la respuesta debe ser 403 y B no debe cambiar). La verificación de que el
`permiso_qr` de B no se altera se hace leyendo la columna con SQL parametrizado
sobre `settings.db_schema`, sin pasar por el endpoint (que para A sobre B
siempre es 403).

Las fixtures `db`, `fabrica`, `cliente` y `auth` son de ámbito de función (se
crean una sola vez por test) y `@given` reejecuta el cuerpo muchas veces. Las
empresas A y B y el `ADMIN_CLIENTE` de A se crean UNA vez fuera del `@given`;
cada ejemplo fija el `permiso_qr` base de B, ejercita el endpoint y comprueba
que B sigue con ese valor base. La prueba no deja estado acumulado (solo relee y
reescribe el permiso base de B). Se suprime
`HealthCheck.function_scoped_fixture` porque la reutilización de las fixtures
entre ejemplos es deliberada.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app.config import settings as app_settings

from helpers_qr import NIVELES_PERMISO_QR, ajustar_permiso_qr, crear_admin_cliente

RUTA = "/qr/empresas/{id_empresa}/permiso-qr"
MENSAJE_NO_AUTORIZADO = "No autorizado para esta empresa"

# Valor base del permiso de B en cada ejemplo. Debe ser válido (CHECK IN (1,2,3))
# para poder fijarlo con un UPDATE directo sin violar la restricción de la BD.
PERMISO_BASE_B = 2

# Valores que el atacante intenta escribir: niveles válidos y valores fuera de
# {1,2,3}. En todos los casos la operación debe fallar con 403 antes de tocar B.
_permiso_intentado = st.one_of(
    st.sampled_from(NIVELES_PERMISO_QR),
    st.integers(min_value=-10, max_value=10).filter(
        lambda v: v not in NIVELES_PERMISO_QR
    ),
)


def _leer_permiso(db, id_empresa: int) -> int:
    """Lee `empresa.permiso_qr` directamente por SQL (sin pasar por el endpoint)."""
    return db.execute(
        text(
            f"SELECT permiso_qr FROM {app_settings.db_schema}.empresa "
            "WHERE id_empresa = :id_empresa"
        ),
        {"id_empresa": id_empresa},
    ).scalar_one()


# Feature: qr-publico-permisos-tickets, Property 4: Aislamiento multiempresa
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(operacion=st.sampled_from(("GET", "PUT")), permiso_intentado=_permiso_intentado)
def test_admin_de_a_no_lee_ni_modifica_permiso_de_b(
    cliente,
    fabrica,
    auth,
    db,
    operacion,
    permiso_intentado,
):
    """Un `ADMIN_CLIENTE` de A sobre B → 403 y el `permiso_qr` de B intacto.

    _Requirements: 2.5_
    """
    # Empresas distintas y el ADMIN_CLIENTE de A: creados una sola vez por test.
    empresa_a = fabrica.empresa("Empresa A")
    empresa_b = fabrica.empresa("Empresa B")
    admin_a = crear_admin_cliente(fabrica, empresa=empresa_a)

    # Fija el permiso base de B para este ejemplo y confirma el punto de partida.
    ajustar_permiso_qr(db, empresa_b, PERMISO_BASE_B)
    assert _leer_permiso(db, empresa_b.id_empresa) == PERMISO_BASE_B

    ruta_b = RUTA.format(id_empresa=empresa_b.id_empresa)

    if operacion == "GET":
        respuesta = cliente.get(ruta_b, headers=auth(admin_a))
    else:
        respuesta = cliente.put(
            ruta_b,
            json={"permiso_qr": permiso_intentado},
            headers=auth(admin_a),
        )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == MENSAJE_NO_AUTORIZADO

    # El permiso de B no cambió por el intento de A (relectura por SQL directo).
    assert _leer_permiso(db, empresa_b.id_empresa) == PERMISO_BASE_B
