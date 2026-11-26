"""Property test P8: round-trip del OTP y creación del ticket (HU-24).

# Feature: qr-publico-permisos-tickets, Property 8

**Property 8: Round-trip del OTP y creación del ticket**

*Para todo* OTP emitido a un empleado, cuando se envía un ticket con
`empresa.permiso_qr = 2` y ese mismo OTP (hash coincidente, no expirado, no
utilizado), se crea un ticket con `id_silla` igual a la silla consultada,
`estado = 'ABIERTO'` y `fecha_creacion` definida; el `codigo_verificacion`
correspondiente queda `utilizado = true` en la MISMA transacción; y reusar el
mismo OTP ya no valida (segundo intento → 400 "OTP expirado o ya utilizado" y
sin ticket adicional).

**Validates: Requirements 3.7, 3.9, 3.10**

Estrategia
----------
Hypothesis genera el `asunto` y la `descripcion` con `st.text` para variar el
contenido del ticket a través de muchos ejemplos. El resto del flujo es el
round-trip canónico del OTP: emitir con `permiso_qr = 2`, leer el OTP en claro
del `EmailSender` falso (la BD solo guarda su hash), crear el ticket y comprobar
que la fila de `codigo_verificacion` quedó `utilizado = true`; luego reintentar
con el mismo OTP y exigir el rechazo sin ticket extra.

Las fixtures `cliente`, `fabrica`, `db` (y las de `helpers_qr`) son de ámbito de
función: pytest las crea una sola vez por función y `@given` reejecuta el cuerpo
muchas veces reutilizando esas instancias. Como cada ejemplo muta la BD (crea un
ticket y consume el OTP), se construye un escenario + silla FRESCOS por ejemplo
y, en un `finally`, se borran las filas de `ticket` y `codigo_verificacion`
creadas, además del escenario, para no acumular estado entre ejemplos. El
fixture autouse `_limpiar_tablas` solo trunca entre funciones de prueba, no entre
ejemplos de `@given`; por eso la limpieza por ejemplo es explícita. Se suprime
`HealthCheck.function_scoped_fixture` porque la reutilización es deliberada.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app.config import settings as app_settings

# Las fixtures `email_falso` y `con_permiso` viven en `tests/helpers_qr.py`; se
# importan aquí para que pytest las resuelva en este módulo (no están
# registradas como plugin global).
from helpers_qr import con_permiso, email_falso  # noqa: F401

MENSAJE_OTP_EXPIRADO_O_USADO = "OTP expirado o ya utilizado"


def _tickets_de_silla(db, id_silla: int) -> list[dict]:
    """Filas de `ticket` asociadas a la silla (fuente de verdad en la BD)."""
    db.expire_all()
    filas = db.execute(
        text(
            "SELECT id_ticket, id_silla, estado, fecha_creacion "
            f"FROM {app_settings.db_schema}.ticket WHERE id_silla = :id_silla"
        ),
        {"id_silla": id_silla},
    ).mappings().all()
    return [dict(fila) for fila in filas]


def _codigo_utilizado(db, id_empleado: int) -> bool:
    """`utilizado` de la (única) fila de `codigo_verificacion` del empleado."""
    db.expire_all()
    return bool(
        db.execute(
            text(
                f"SELECT utilizado FROM {app_settings.db_schema}.codigo_verificacion "
                "WHERE id_empleado = :id_empleado"
            ),
            {"id_empleado": id_empleado},
        ).scalar_one()
    )


def _limpiar_ejemplo(db, datos: dict, silla) -> None:
    """Borra las filas creadas en un ejemplo de Hypothesis.

    El orden respeta las claves foráneas: primero `ticket` y
    `codigo_verificacion` (que referencian la silla/empleado), luego la silla y
    el resto del escenario. SQL parametrizado por esquema para no depender del
    estado de la sesión ORM entre ejemplos.
    """
    esquema = app_settings.db_schema
    db.execute(
        text(f"DELETE FROM {esquema}.ticket WHERE id_silla = :id"),
        {"id": silla.id_silla},
    )
    db.execute(
        text(f"DELETE FROM {esquema}.codigo_verificacion WHERE id_empleado = :id"),
        {"id": datos["empleado"].id_empleado},
    )
    db.execute(
        text(f"DELETE FROM {esquema}.silla WHERE id_silla = :id"),
        {"id": silla.id_silla},
    )
    db.execute(
        text(f"DELETE FROM {esquema}.visita WHERE id_visita = :id"),
        {"id": datos["visita"].id_visita},
    )
    db.execute(
        text(f"DELETE FROM {esquema}.empleado WHERE id_empleado = :id"),
        {"id": datos["empleado"].id_empleado},
    )
    db.execute(
        text(f"DELETE FROM {esquema}.departamento WHERE id_departamento = :id"),
        {"id": datos["departamento"].id_departamento},
    )
    db.execute(
        text(f"DELETE FROM {esquema}.sede WHERE id_sede = :id"),
        {"id": datos["sede"].id_sede},
    )
    db.execute(
        text(f"DELETE FROM {esquema}.usuario WHERE id_usuario IN (:c, :t)"),
        {"c": datos["comercial"].id_usuario, "t": datos["tecnico"].id_usuario},
    )
    db.execute(
        text(f"DELETE FROM {esquema}.empresa WHERE id_empresa = :id"),
        {"id": datos["empresa"].id_empresa},
    )
    db.commit()


# Feature: qr-publico-permisos-tickets, Property 8: Round-trip del OTP y ticket
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    asunto=st.text(max_size=150),
    descripcion=st.text(max_size=500),
)
def test_roundtrip_otp_crea_ticket_y_consume_codigo(
    cliente,
    fabrica,
    db,
    con_permiso,
    email_falso,
    asunto,
    descripcion,
):
    """OTP emitido → ticket creado, OTP consumido y no reutilizable.

    Con `permiso_qr = 2` y el OTP válido: 201, ticket con `id_silla` de la silla
    consultada, `estado = 'ABIERTO'` y `fecha_creacion` definida; la fila de
    `codigo_verificacion` queda `utilizado = true`. Reusar el mismo OTP → 400
    "OTP expirado o ya utilizado" sin ticket adicional.

    _Requirements: 3.7, 3.9, 3.10_
    """
    # Escenario + silla frescos por ejemplo: `silla.id_empleado` apunta a un
    # empleado identificable por su correo.
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    token = str(silla.token_publico)
    correo = datos["empleado"].correo

    try:
        # Emitir el OTP con permiso 2 (nivel bajo prueba del flujo exitoso).
        con_permiso(datos["empresa"], 2)
        otp_resp = cliente.post(f"/qr/silla/{token}/otp", json={"correo": correo})
        assert otp_resp.status_code == 204, otp_resp.text
        # El OTP en claro se lee del sender falso (la BD solo guarda su hash).
        codigo = email_falso.ultimo_codigo(correo)

        # Primer envío: el ticket se crea y el OTP se consume.
        primera = cliente.post(
            f"/qr/silla/{token}/ticket",
            json={
                "asunto": asunto,
                "descripcion": descripcion,
                "correo": correo,
                "codigo": codigo,
            },
        )

        assert primera.status_code == 201, primera.text
        cuerpo = primera.json()
        assert cuerpo["id_silla"] == silla.id_silla
        assert cuerpo["estado"] == "ABIERTO"
        assert cuerpo["fecha_creacion"]  # definida por la BD

        # El ticket vive en la BD, ligado a la silla, con estado y fecha.
        filas = _tickets_de_silla(db, silla.id_silla)
        assert len(filas) == 1
        assert filas[0]["id_ticket"] == cuerpo["id_ticket"]
        assert filas[0]["estado"] == "ABIERTO"
        assert filas[0]["fecha_creacion"] is not None

        # El OTP quedó marcado como utilizado en la misma transacción.
        assert _codigo_utilizado(db, datos["empleado"].id_empleado) is True

        # Segundo envío con el MISMO OTP: ya consumido, no vuelve a validar.
        segunda = cliente.post(
            f"/qr/silla/{token}/ticket",
            json={
                "asunto": asunto,
                "descripcion": descripcion,
                "correo": correo,
                "codigo": codigo,
            },
        )

        assert segunda.status_code == 400, segunda.text
        assert segunda.json()["detail"] == MENSAJE_OTP_EXPIRADO_O_USADO
        # No se creó un ticket adicional: solo el del primer envío.
        assert len(_tickets_de_silla(db, silla.id_silla)) == 1
    finally:
        _limpiar_ejemplo(db, datos, silla)
