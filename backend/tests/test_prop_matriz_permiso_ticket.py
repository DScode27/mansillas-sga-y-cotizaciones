"""Property test P6: matriz de permiso para tickets de empleado (HU-24).

# Feature: qr-publico-permisos-tickets, Property 6

**Property 6: Matriz de permiso para tickets de empleado**

Para toda empresa, el envío de ticket por un empleado a través del QR
(`POST /qr/silla/{token}/ticket`) tiene éxito si y solo si `empresa.permiso_qr`
es exactamente 2: con `permiso_qr = 2` la respuesta es 201 y el ticket queda
creado; con `permiso_qr = 1` la respuesta es 403 "Permiso insuficiente"; y con
`permiso_qr = 3` la respuesta es 403 "Solo el administrador del cliente puede
crear tickets". En los dos casos de rechazo no se crea ningún ticket.

**Validates: Requirements 3.2, 3.3, 3.4**

Estrategia
----------
Hypothesis genera el nivel de permiso con `st.sampled_from([1, 2, 3])` y el
cuerpo del test comprueba el resultado esperado para cada nivel.

Las fixtures `cliente`, `fabrica`, `db` (y las de `helpers_qr`) son de ámbito de
función: pytest las crea una sola vez por función de prueba y `@given` reejecuta
el cuerpo muchas veces reutilizando esas mismas instancias. Como cada ejemplo
muta la BD (el nivel 2 crea un ticket y consume el OTP), se construye un
escenario + silla FRESCOS por ejemplo y, en un `finally`, se borran las filas de
`ticket` y `codigo_verificacion` creadas, además del escenario, para no acumular
estado entre ejemplos. El fixture autouse `_limpiar_tablas` solo trunca entre
funciones de prueba, no entre ejemplos de `@given`; por eso la limpieza por
ejemplo es explícita. Se suprime `HealthCheck.function_scoped_fixture` porque la
reutilización de las fixtures entre ejemplos es deliberada.

El OTP se emite SIEMPRE con `permiso_qr = 2` (el endpoint de OTP no comprueba el
permiso) y solo después se fija el nivel bajo prueba, de modo que exista un OTP
válido aun cuando el permiso deba cortar la creación antes de validarlo
(niveles 1 y 3). El OTP en claro se lee del `EmailSender` falso, nunca de la
columna `codigo_hash`.
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

MENSAJE_PERMISO_INSUFICIENTE = "Permiso insuficiente"
MENSAJE_SOLO_ADMIN = "Solo el administrador del cliente puede crear tickets"


def _tickets_de_silla(db, id_silla: int) -> list[int]:
    """Ids de `ticket` asociados a la silla (fuente de verdad en la BD)."""
    db.expire_all()
    filas = db.execute(
        text(
            f"SELECT id_ticket FROM {app_settings.db_schema}.ticket "
            "WHERE id_silla = :id_silla"
        ),
        {"id_silla": id_silla},
    ).scalars().all()
    return [int(fila) for fila in filas]


def _limpiar_ejemplo(db, datos: dict, silla) -> None:
    """Borra las filas creadas en un ejemplo de Hypothesis.

    El orden respeta las claves foráneas: primero `ticket` y
    `codigo_verificacion` (que referencian la silla/empleado), luego la silla y
    el resto del escenario. Se usa SQL parametrizado por esquema para no
    depender del estado de la sesión ORM entre ejemplos.
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


# Feature: qr-publico-permisos-tickets, Property 6: Matriz de permiso para tickets
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(permiso=st.sampled_from([1, 2, 3]))
def test_matriz_permiso_ticket_empleado(
    cliente,
    fabrica,
    db,
    con_permiso,
    email_falso,
    permiso,
):
    """El ticket por QR del empleado tiene éxito si y solo si `permiso_qr == 2`.

    _Requirements: 3.2, 3.3, 3.4_
    """
    # Escenario + silla frescos por ejemplo: `silla.id_empleado` apunta a un
    # empleado identificable por su correo.
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    token = str(silla.token_publico)
    correo = datos["empleado"].correo

    try:
        # Emitir el OTP con permiso 2 (el endpoint de OTP no comprueba permiso):
        # garantiza un OTP válido aun cuando el nivel deba cortar antes.
        con_permiso(datos["empresa"], 2)
        otp_resp = cliente.post(f"/qr/silla/{token}/otp", json={"correo": correo})
        assert otp_resp.status_code == 204, otp_resp.text
        codigo = email_falso.ultimo_codigo(correo)

        # Fijar el nivel bajo prueba y enviar el ticket.
        con_permiso(datos["empresa"], permiso)
        respuesta = cliente.post(
            f"/qr/silla/{token}/ticket",
            json={
                "asunto": "Rueda rota",
                "descripcion": "La silla no gira",
                "correo": correo,
                "codigo": codigo,
            },
        )

        if permiso == 2:
            # Éxito: 201 y el ticket queda creado y asociado a la silla.
            assert respuesta.status_code == 201, respuesta.text
            cuerpo = respuesta.json()
            assert cuerpo["id_silla"] == silla.id_silla
            assert cuerpo["estado"] == "ABIERTO"
            assert _tickets_de_silla(db, silla.id_silla) == [cuerpo["id_ticket"]]
        elif permiso == 1:
            # Rechazo: 403 "Permiso insuficiente"; no se crea ningún ticket.
            assert respuesta.status_code == 403, respuesta.text
            assert respuesta.json()["detail"] == MENSAJE_PERMISO_INSUFICIENTE
            assert _tickets_de_silla(db, silla.id_silla) == []
        else:  # permiso == 3
            # Rechazo: 403 "Solo el administrador..."; no se crea ningún ticket.
            assert respuesta.status_code == 403, respuesta.text
            assert respuesta.json()["detail"] == MENSAJE_SOLO_ADMIN
            assert _tickets_de_silla(db, silla.id_silla) == []
    finally:
        _limpiar_ejemplo(db, datos, silla)
