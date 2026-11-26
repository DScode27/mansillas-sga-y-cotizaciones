"""Property test P5: rechazo de permiso inválido (HU-18).

# Feature: qr-publico-permisos-tickets, Property 5

**Property 5: Rechazo de permiso inválido**

Para todo valor entero fuera de {1, 2, 3}, la actualización del permiso QR
(`PUT /qr/empresas/{id_empresa}/permiso-qr`) por el `ADMIN_CLIENTE` dueño se
rechaza con HTTP 422 y el mensaje de dominio "permiso_qr debe ser 1, 2 o 3",
y el valor almacenado en `empresa.permiso_qr` no cambia respecto al valor base
fijado antes del intento.

**Validates: Requirements 2.6**

Nota sobre Hypothesis + fixtures de pytest con ámbito de función: `cliente`,
`fabrica`, `auth` y la sesión `db` se crean una sola vez por función de prueba.
Hypothesis reutiliza esas instancias entre ejemplos, lo que dispara
`HealthCheck.function_scoped_fixture`. Aquí es seguro y deliberado: el admin y
la empresa se crean UNA vez fuera del `@given`, y antes de cada ejemplo se
restablece el permiso a un valor base conocido (1) mediante `ajustar_permiso_qr`
(un `UPDATE` directo que no depende de la validación de dominio). Cada intento
inválido solo hace un `PUT` que debe rechazarse, por lo que `permiso_qr` debe
seguir siendo el valor base al releerlo. Se suprime de forma explícita
`HealthCheck.function_scoped_fixture`.

Nota sobre el tipo: `PermisoQrUpdate.permiso_qr` es `int`, por lo que cuerpos no
enteros los rechaza Pydantic (422 de validación). Esta propiedad se concentra en
enteros fuera de rango que SÍ llegan al servicio de dominio y producen el 422
`PermisoInvalido` con el mensaje de dominio.
"""

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app.config import settings as app_settings
from helpers_qr import NIVELES_PERMISO_QR, ajustar_permiso_qr, crear_admin_cliente

RUTA = "/qr/empresas/{id_empresa}/permiso-qr"
MENSAJE_PERMISO_INVALIDO = "permiso_qr debe ser 1, 2 o 3"
PERMISO_BASE = 1

# Enteros fuera de los niveles válidos {1, 2, 3}: incluye negativos, cero y
# valores por encima de 3. Es el espacio de entradas que debe rechazar el
# servicio de dominio con 422.
_permisos_invalidos = st.integers().filter(lambda n: n not in NIVELES_PERMISO_QR)


def _permiso_almacenado(db, id_empresa: int) -> int:
    """Lee `empresa.permiso_qr` directamente de la BD (parametrizado)."""
    return db.execute(
        text(
            f"SELECT permiso_qr FROM {app_settings.db_schema}.empresa "
            "WHERE id_empresa = :id_empresa"
        ),
        {"id_empresa": id_empresa},
    ).scalar_one()


@settings(
    max_examples=100,
    # `cliente`, `fabrica`, `auth` y `db` son fixtures de pytest con ámbito de
    # función que Hypothesis reutiliza entre ejemplos. Es seguro aquí porque
    # cada ejemplo restablece el permiso base antes del intento y solo verifica
    # que un PUT inválido no muta el estado; suprimimos el aviso.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(permiso_invalido=_permisos_invalidos)
def test_permiso_invalido_se_rechaza_y_no_cambia_el_almacenado(
    cliente, fabrica, auth, db, permiso_invalido
):
    """Todo entero fuera de {1, 2, 3} → 422 y `permiso_qr` queda en el valor base.

    _Requirements: 2.6_
    """
    empresa = fabrica.empresa()
    admin = crear_admin_cliente(fabrica, empresa=empresa)
    ruta = RUTA.format(id_empresa=empresa.id_empresa)

    # Base conocida mediante UPDATE directo (no pasa por la validación de dominio).
    ajustar_permiso_qr(db, empresa, PERMISO_BASE)

    respuesta = cliente.put(
        ruta, json={"permiso_qr": permiso_invalido}, headers=auth(admin)
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detail"] == MENSAJE_PERMISO_INVALIDO

    # El valor almacenado no cambió: sigue siendo la base.
    db.expire_all()
    assert _permiso_almacenado(db, empresa.id_empresa) == PERMISO_BASE
