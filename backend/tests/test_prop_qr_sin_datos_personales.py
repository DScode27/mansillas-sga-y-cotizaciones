"""Property test P2 de la feature qr-publico-permisos-tickets.

**Property 2: No exposición de datos personales**

*Para toda* respuesta pública (consulta o resultado de envío de ticket), el
cuerpo nunca contiene el nombre, el documento ni el correo del empleado asignado
a la silla (RN-3/RN-4).

**Validates: Requirements 1.5**

Estrategia
----------
Hypothesis genera `nombre`, `documento` y `correo` aleatorios (no vacíos) para el
empleado asignado a la silla. Dado que las fixtures `db` y `fabrica` son de
ámbito de función (se crean una sola vez por test) y `@given` reejecuta el cuerpo
muchas veces, la empresa/sede/departamento se crean una única vez con
`Fabrica.escenario()` y, en CADA ejemplo, se crea el empleado con esos valores
personales más su silla, se ejercitan los endpoints públicos y se eliminan esas
filas al final para no acumular estado ni chocar con restricciones UNIQUE. Se
suprime `HealthCheck.function_scoped_fixture` porque la reutilización de las
fixtures entre ejemplos es deliberada.

Se cubren las DOS respuestas públicas de la propiedad:

1. `GET /qr/silla/{token}` (consulta pública, HU-17).
2. El `TicketOut` de `POST /qr/silla/{token}/ticket` (envío de ticket, HU-24),
   con `empresa.permiso_qr = 2` y el OTP leído del `EmailSender` falso.

Los valores personales se generan con un prefijo centinela distintivo para que
la comprobación de subcadena sea discriminante y no tropiece con coincidencias
triviales (un documento "1", por ejemplo, podría aparecer como subcadena de un
id sin ser una fuga real). La propiedad vale para valores arbitrarios; el
centinela solo hace el test sensible a fugas reales.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app.config import settings as app_settings
from app.models import Empleado, Silla

# Alfabeto legible para los valores personales (sin caracteres de control ni
# espacios en blanco que compliquen la comprobación de subcadena).
_ALFABETO = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

_sufijo = st.text(alphabet=_ALFABETO, min_size=1, max_size=20)
_digitos = st.text(alphabet="0123456789", min_size=1, max_size=12)


def _eliminar_silla_y_empleado(db, silla: Silla, empleado: Empleado) -> None:
    """Borra la silla y el empleado creados en un ejemplo de Hypothesis.

    Se usa SQL parametrizado por esquema para no depender del estado de la
    sesión ORM entre ejemplos. El orden respeta la FK silla -> empleado.
    """
    db.execute(
        text(f"DELETE FROM {app_settings.db_schema}.silla WHERE id_silla = :id"),
        {"id": silla.id_silla},
    )
    db.execute(
        text(
            f"DELETE FROM {app_settings.db_schema}.empleado "
            "WHERE id_empleado = :id"
        ),
        {"id": empleado.id_empleado},
    )
    db.commit()


# Feature: qr-publico-permisos-tickets, Property 2: No exposición de datos personales
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    nombre_sufijo=_sufijo,
    documento_sufijo=_digitos,
    correo_sufijo=_sufijo,
)
def test_respuesta_publica_nunca_expone_datos_personales(
    cliente,
    fabrica,
    db,
    con_permiso,
    email_falso,
    nombre_sufijo,
    documento_sufijo,
    correo_sufijo,
):
    """Ni la consulta pública ni el `TicketOut` exponen nombre/documento/correo.

    _Requirements: 1.5_
    """
    # Empresa + sede + departamento compartidos (una sola vez por test). El
    # empleado y la silla, con los datos personales aleatorios, se crean por
    # ejemplo y se eliminan al terminar.
    datos = fabrica.escenario()
    empresa = datos["empresa"]
    sede = datos["sede"]
    departamento = datos["departamento"]

    # permiso_qr = 2 habilita el flujo de ticket por empleado (HU-24).
    con_permiso(empresa, 2)

    # Valores personales distintivos: prefijo centinela + sufijo aleatorio.
    nombre = f"NombreZZ-{nombre_sufijo}"
    documento = f"99{documento_sufijo}"
    correo = f"correoZZ-{correo_sufijo}@fuga.test"

    empleado = Empleado(
        id_empresa=empresa.id_empresa,
        id_sede=sede.id_sede,
        id_departamento=departamento.id_departamento,
        nombre=nombre,
        documento=documento,
        correo=correo,
        cargo="Analista",
        activo=True,
    )
    db.add(empleado)
    db.commit()
    db.refresh(empleado)

    silla = fabrica.silla(datos["visita"], empleado)

    try:
        # --- Respuesta 1: consulta pública (HU-17) ---
        consulta = cliente.get(f"/qr/silla/{silla.token_publico}")
        assert consulta.status_code == 200, consulta.text
        _asegurar_sin_datos_personales(consulta, nombre, documento, correo)

        # --- Respuesta 2: resultado de envío de ticket (HU-24) ---
        # Solicitar OTP y leerlo del EmailSender falso (en claro, sin tocar la
        # columna codigo_hash de la BD).
        otp_resp = cliente.post(
            f"/qr/silla/{silla.token_publico}/otp",
            json={"correo": correo},
        )
        assert otp_resp.status_code == 204, otp_resp.text
        codigo = email_falso.ultimo_codigo(correo)

        ticket_resp = cliente.post(
            f"/qr/silla/{silla.token_publico}/ticket",
            json={
                "asunto": "Falla en la silla",
                "descripcion": "La silla presenta un desperfecto.",
                "correo": correo,
                "codigo": codigo,
            },
        )
        assert ticket_resp.status_code == 201, ticket_resp.text
        _asegurar_sin_datos_personales(ticket_resp, nombre, documento, correo)
    finally:
        _eliminar_silla_y_empleado(db, silla, empleado)


def _asegurar_sin_datos_personales(respuesta, nombre, documento, correo) -> None:
    """Comprueba que ni el JSON ni el texto crudo contienen los datos personales."""
    crudo = respuesta.text
    assert nombre not in crudo
    assert documento not in crudo
    assert correo not in crudo

    cuerpo = respuesta.json()
    valores = [str(valor) for valor in cuerpo.values()]
    assert nombre not in valores
    assert documento not in valores
    assert correo not in valores
