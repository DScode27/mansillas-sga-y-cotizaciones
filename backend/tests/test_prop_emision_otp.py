"""Property test P7: emisión de OTP (HU-24).

# Feature: qr-publico-permisos-tickets, Property 7

**Property 7: Emisión de OTP**

*Para todo* `Empleado_Identificado` de la empresa dueña de la silla, solicitar
un OTP (por correo o documento) inserta en `codigo_verificacion` exactamente una
fila con ese `id_empleado`, `correo_destino` igual al correo del empleado,
`codigo_hash` distinto del OTP en claro, `fecha_expiracion` futura y
`utilizado = false`; y *para todo* correo o documento que no corresponde a un
empleado de esa empresa la respuesta es HTTP 404 "Empleado no encontrado".

**Validates: Requirements 3.5, 3.6**

Estrategia
----------
Las fixtures `cliente`, `fabrica` y la sesión `db` son de ámbito de función (se
crean una sola vez por test) mientras que `@given` reejecuta el cuerpo muchas
veces; Hypothesis reutiliza esas instancias entre ejemplos, lo que dispara
`HealthCheck.function_scoped_fixture`. La reutilización es deliberada: la empresa
+ sede + departamento + silla se crean UNA vez con `Fabrica.escenario()` y, en
CADA ejemplo, se solicita el OTP y se LIMPIAN las filas de `codigo_verificacion`
del empleado en un `finally`. Sin esa limpieza, la aserción "exactamente una
fila" acumularía filas entre ejemplos. Se suprime de forma explícita
`HealthCheck.function_scoped_fixture`.

El OTP en claro se lee del `EmailSenderFalso` instalado por la fixture
`email_falso` (vía `app.dependency_overrides[get_email_sender]`); la BD solo
guarda su hash. `st.booleans()` elige si el empleado se identifica por correo o
por documento. El permiso de la empresa se fija en 2 por consistencia con el
flujo de ticket, aunque la solicitud de OTP no lo exige.

Las filas de `codigo_verificacion` se leen con `sqlalchemy.text` sobre
`settings.db_schema`, sin pasar por el ORM, para que la comprobación observe el
estado real persistido.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app.config import settings as app_settings

# Las fixtures `email_falso` y `con_permiso` viven en `tests/helpers_qr.py`; se
# importan aquí para que pytest las resuelva en este módulo.
from helpers_qr import con_permiso, email_falso  # noqa: F401

MENSAJE_EMPLEADO_NO_ENCONTRADO = "Empleado no encontrado"

# Alfabeto legible para construir identificadores que NO pertenecen a ningún
# empleado de la empresa (prefijo centinela + sufijo aleatorio).
_ALFABETO = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_sufijo = st.text(alphabet=_ALFABETO, min_size=1, max_size=20)
_digitos = st.text(alphabet="0123456789", min_size=1, max_size=10)


def _token(silla) -> str:
    """Token público de la silla, tal como viaja en la URL del QR."""
    return str(silla.token_publico)


def _codigos_de_empleado(db, id_empleado: int) -> list[dict]:
    """Filas de `codigo_verificacion` del empleado (fuente de verdad en la BD)."""
    db.expire_all()
    filas = db.execute(
        text(
            "SELECT id_empleado, correo_destino, codigo_hash, utilizado, "
            "fecha_expiracion > now() AS vigente "
            f"FROM {app_settings.db_schema}.codigo_verificacion "
            "WHERE id_empleado = :id_empleado"
        ),
        {"id_empleado": id_empleado},
    ).mappings().all()
    return [dict(fila) for fila in filas]


def _limpiar_codigos(db, id_empleado: int) -> None:
    """Borra las filas de `codigo_verificacion` creadas en un ejemplo.

    Evita que la aserción "exactamente una fila" acumule estado entre ejemplos
    de Hypothesis (las fixtures son de ámbito de función).
    """
    db.execute(
        text(
            f"DELETE FROM {app_settings.db_schema}.codigo_verificacion "
            "WHERE id_empleado = :id_empleado"
        ),
        {"id_empleado": id_empleado},
    )
    db.commit()


# Feature: qr-publico-permisos-tickets, Property 7: Emisión de OTP (rama positiva)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(por_correo=st.booleans())
def test_solicitar_otp_inserta_exactamente_una_fila(
    cliente, fabrica, db, email_falso, con_permiso, por_correo
):
    """Empleado identificado → 204 y exactamente una fila de OTP correcta.

    La fila tiene su `id_empleado`, `correo_destino` igual al correo del
    empleado, `codigo_hash` distinto del OTP en claro, `fecha_expiracion` futura
    y `utilizado = false`.

    _Requirements: 3.5, 3.6_
    """
    datos = fabrica.escenario()
    empleado = datos["empleado"]
    silla = fabrica.silla(datos["visita"], empleado)
    # Permiso 2 por consistencia con el flujo de ticket (el OTP no lo exige).
    con_permiso(datos["empresa"], 2)

    # `st.booleans()` elige el identificador: correo o documento.
    if por_correo:
        payload = {"correo": empleado.correo}
    else:
        payload = {"documento": empleado.documento}

    try:
        respuesta = cliente.post(f"/qr/silla/{_token(silla)}/otp", json=payload)

        assert respuesta.status_code == 204, respuesta.text

        # El OTP en claro se recupera del sender falso (nunca de la BD).
        otp_claro = email_falso.ultimo_codigo(empleado.correo)

        filas = _codigos_de_empleado(db, empleado.id_empleado)
        assert len(filas) == 1
        fila = filas[0]
        assert fila["id_empleado"] == empleado.id_empleado
        assert fila["correo_destino"] == empleado.correo
        # El código se guarda hasheado: nunca igual al OTP en claro (RN-5).
        assert fila["codigo_hash"] != otp_claro
        assert fila["vigente"] is True  # fecha_expiracion futura
        assert fila["utilizado"] is False
    finally:
        _limpiar_codigos(db, empleado.id_empleado)


# Feature: qr-publico-permisos-tickets, Property 7: Emisión de OTP (rama negativa)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(sufijo_correo=_sufijo, sufijo_documento=_digitos, por_correo=st.booleans())
def test_solicitar_otp_identificador_desconocido_da_404(
    cliente, fabrica, db, email_falso, con_permiso, sufijo_correo, sufijo_documento, por_correo
):
    """Correo/documento sin empleado en la empresa → 404 y ninguna fila.

    Los identificadores llevan un prefijo centinela que no colisiona con los que
    genera la `Fabrica` (`empleado{n}@test.local` / `10{n:08d}`), de modo que
    nunca corresponden al empleado real de la silla.

    _Requirements: 3.6_
    """
    datos = fabrica.escenario()
    empleado = datos["empleado"]
    silla = fabrica.silla(datos["visita"], empleado)
    con_permiso(datos["empresa"], 2)

    if por_correo:
        payload = {"correo": f"fantasmaZZ-{sufijo_correo}@ausente.test"}
    else:
        payload = {"documento": f"77{sufijo_documento}"}

    try:
        respuesta = cliente.post(f"/qr/silla/{_token(silla)}/otp", json=payload)

        assert respuesta.status_code == 404
        assert respuesta.json()["detail"] == MENSAJE_EMPLEADO_NO_ENCONTRADO
        # No hubo empleado al que enviar el OTP ni fila que insertar.
        assert email_falso.enviados == []
        assert _codigos_de_empleado(db, empleado.id_empleado) == []
    finally:
        _limpiar_codigos(db, empleado.id_empleado)
