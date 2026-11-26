"""Property test P9: rechazo de OTP inválido, expirado o usado (HU-24).

# Feature: qr-publico-permisos-tickets, Property 9

**Property 9: Rechazo de OTP inválido, expirado o usado**

Para todo OTP cuyo hash no coincide con el almacenado, el envío de ticket
(`POST /qr/silla/{token}/ticket`) responde HTTP 400 "OTP inválido"; y para todo
OTP expirado (`fecha_expiracion < now()`) o ya utilizado, responde HTTP 400
"OTP expirado o ya utilizado". En ambos casos no se crea ningún ticket.

**Validates: Requirements 3.8, 3.9**

Estrategia
----------
Hypothesis elige con `st.sampled_from(["invalido", "expirado", "usado"])` cuál
de las tres ramas de rechazo ejercita cada ejemplo:

- "invalido": NO se emite ningún OTP; se envía un código numérico aleatorio
  (`st.text(digits)`). Como no existe fila en `codigo_verificacion`, ningún
  `codigo_hash` casa con el código enviado y el servicio responde
  400 "OTP inválido". No emitir OTP garantiza el *hash mismatch* sin depender de
  que el código aleatorio difiera del real.
- "expirado": se emite un OTP real (endpoint con `permiso_qr = 2`), se lee en
  claro del `EmailSender` falso y luego un `UPDATE` directo retrocede
  `fecha_expiracion` al pasado; el ticket se envía con el código CORRECTO, de
  modo que el hash casa pero está caducado → 400 "OTP expirado o ya utilizado".
- "usado": se emite un OTP real y un `UPDATE` directo lo marca
  `utilizado = true`; el ticket se envía con el código CORRECTO, de modo que el
  hash casa pero ya fue consumido → 400 "OTP expirado o ya utilizado".

En las tres ramas el permiso de la empresa se fija en 2 ANTES de enviar el
ticket, para que el flujo llegue a la validación del OTP (con permiso 1 o 3 el
servicio cortaría antes, en la comprobación de permiso).

Las fixtures `cliente`, `fabrica`, `db` (y las de `helpers_qr`) son de ámbito de
función: pytest las crea una sola vez por función de prueba y `@given` reejecuta
el cuerpo muchas veces reutilizando esas mismas instancias. Como cada ejemplo
muta la BD (emite OTP, lo expira/consume), se construye un escenario + silla
FRESCOS por ejemplo y, en un `finally`, se borran las filas de `ticket` y
`codigo_verificacion` creadas, además del escenario, para no acumular estado
entre ejemplos. Se suprime `HealthCheck.function_scoped_fixture` porque la
reutilización de las fixtures entre ejemplos es deliberada.

El OTP en claro se lee del `EmailSender` falso, nunca de la columna
`codigo_hash`. Las comprobaciones sobre `ticket` se hacen con `sqlalchemy.text`
sobre `settings.db_schema`, para observar el estado real persistido.
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

MENSAJE_OTP_INVALIDO = "OTP inválido"
MENSAJE_OTP_EXPIRADO_O_USADO = "OTP expirado o ya utilizado"

# Códigos numéricos aleatorios para la rama "invalido": al no emitirse ningún
# OTP, cualquier cadena de dígitos sirve (su hash nunca casa con una fila
# inexistente). Se acota la longitud para mantener los ejemplos legibles.
_codigo_aleatorio = st.text(alphabet="0123456789", min_size=1, max_size=10)


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


def _expirar_otp(db, id_empleado: int) -> None:
    """Retrocede `fecha_expiracion` del OTP del empleado al pasado.

    Deja el hash intacto (el ticket se enviará con el código correcto), de modo
    que el servicio encuentre la fila pero la considere caducada.
    """
    db.execute(
        text(
            f"UPDATE {app_settings.db_schema}.codigo_verificacion "
            "SET fecha_expiracion = now() - interval '1 minute' "
            "WHERE id_empleado = :id_empleado"
        ),
        {"id_empleado": id_empleado},
    )
    db.commit()


def _marcar_otp_usado(db, id_empleado: int) -> None:
    """Marca el OTP del empleado como `utilizado = true` sin tocar el hash."""
    db.execute(
        text(
            f"UPDATE {app_settings.db_schema}.codigo_verificacion "
            "SET utilizado = true WHERE id_empleado = :id_empleado"
        ),
        {"id_empleado": id_empleado},
    )
    db.commit()


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


# Feature: qr-publico-permisos-tickets, Property 9: Rechazo de OTP inválido/expirado/usado
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(rama=st.sampled_from(["invalido", "expirado", "usado"]), codigo_falso=_codigo_aleatorio)
def test_rechazo_otp_invalido_expirado_o_usado(
    cliente,
    fabrica,
    db,
    con_permiso,
    email_falso,
    rama,
    codigo_falso,
):
    """El envío de ticket con OTP inválido/expirado/usado da 400 y no crea ticket.

    _Requirements: 3.8, 3.9_
    """
    # Escenario + silla frescos por ejemplo: `silla.id_empleado` apunta a un
    # empleado identificable por su correo.
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    token = str(silla.token_publico)
    correo = datos["empleado"].correo

    try:
        if rama == "invalido":
            # No se emite ningún OTP: ninguna fila existe, así que el hash del
            # código enviado no casa → "OTP inválido".
            codigo = codigo_falso
            mensaje_esperado = MENSAJE_OTP_INVALIDO
        else:
            # Emitir un OTP real (el endpoint de OTP no comprueba permiso) y
            # leer el código en claro del sender falso.
            con_permiso(datos["empresa"], 2)
            otp_resp = cliente.post(f"/qr/silla/{token}/otp", json={"correo": correo})
            assert otp_resp.status_code == 204, otp_resp.text
            codigo = email_falso.ultimo_codigo(correo)

            if rama == "expirado":
                _expirar_otp(db, datos["empleado"].id_empleado)
            else:  # rama == "usado"
                _marcar_otp_usado(db, datos["empleado"].id_empleado)
            mensaje_esperado = MENSAJE_OTP_EXPIRADO_O_USADO

        # Permiso 2 para que el flujo llegue a la validación del OTP.
        con_permiso(datos["empresa"], 2)
        respuesta = cliente.post(
            f"/qr/silla/{token}/ticket",
            json={
                "asunto": "Rueda rota",
                "descripcion": "La silla no gira",
                "correo": correo,
                "codigo": codigo,
            },
        )

        # Rechazo: 400 con el mensaje de la rama; no se crea ningún ticket.
        assert respuesta.status_code == 400, respuesta.text
        assert respuesta.json()["detail"] == mensaje_esperado
        assert _tickets_de_silla(db, silla.id_silla) == []
    finally:
        _limpiar_ejemplo(db, datos, silla)
