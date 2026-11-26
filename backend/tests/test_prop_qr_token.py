"""Property test P1: validez del token de consulta pública (HU-17).

# Feature: qr-publico-permisos-tickets, Property 1

**Property 1: Validez del token de consulta pública**

Para toda silla registrada, la consulta pública por su `token_publico`
(`GET /qr/silla/{token}`) devuelve la información básica de la silla y el
`permiso_qr` de la empresa dueña; y para todo identificador que NO resuelve a
una silla registrada (UUID bien formado pero inexistente, o cadena sin formato
UUID) la respuesta es siempre HTTP 404 "QR no válido".

**Validates: Requirements 1.1, 1.3, 1.4, 3.1**

Nota sobre Hypothesis + fixtures de pytest con ámbito de función: `cliente` y
`fabrica` (y la sesión `db` de la que depende `fabrica`) se crean una sola vez
por función de prueba. Hypothesis reutilizaría esa misma instancia en cada
ejemplo generado, lo que dispara `HealthCheck.function_scoped_fixture`. Para
evitarlo, la silla registrada se crea UNA vez fuera del `@given` (rama positiva,
un ejemplo representativo) y la parte generativa se concentra en la rama 404,
que es de solo lectura (`GET`) y no escribe en la BD. Como el fixture
`_limpiar_tablas` trunca `silla` antes de cada prueba, en el test generativo la
tabla está vacía y ningún identificador puede resolver; se suprime de forma
explícita `HealthCheck.function_scoped_fixture`.
"""

import uuid

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

MENSAJE_QR_INVALIDO = "QR no válido"


def _parsea_como_uuid(valor: str) -> bool:
    """`True` si `valor` es aceptado por `uuid.UUID(...)` (igual que el router)."""
    try:
        uuid.UUID(valor)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


# Identificadores con formato UUID válido: resuelven a UUID pero, en una BD sin
# sillas, no pertenecen a ninguna silla registrada.
_uuids = st.uuids().map(str)

# Cadenas arbitrarias que NO parsean como UUID: `get_silla_by_token` las rechaza
# al intentar `uuid.UUID(...)`. El `filter` descarta las que, por casualidad, sí
# serían un UUID válido (p. ej. 32 dígitos hex).
_no_uuid = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="/"),
    min_size=1,
    max_size=40,
).filter(lambda s: not _parsea_como_uuid(s))

# Mezcla de ambas familias de identificadores inválidos para la rama 404.
_identificadores_invalidos = st.one_of(_uuids, _no_uuid)


def test_silla_registrada_devuelve_datos_basicos_y_permiso(cliente, fabrica):
    """Rama positiva (un ejemplo): token de una silla registrada → 200.

    Devuelve la información básica (`id_silla`, `codigo_qr`, `estado`, `cargo`) y
    el `permiso_qr` de la empresa dueña.

    _Requirements: 1.1, 3.1_
    """
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])

    respuesta = cliente.get(f"/qr/silla/{silla.token_publico}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id_silla"] == silla.id_silla
    assert cuerpo["codigo_qr"] == silla.codigo_qr
    assert cuerpo["estado"] == silla.estado
    assert cuerpo["cargo"] == silla.cargo
    # Empresa recién creada: la BD aplica el DEFAULT 1 (CHECK IN (1, 2, 3)).
    assert cuerpo["permiso_qr"] == 1


@settings(
    max_examples=100,
    # `cliente` es un fixture de pytest con ámbito de función: Hypothesis lo
    # reutiliza entre ejemplos. Aquí es seguro porque el caso 404 es de solo
    # lectura (`GET`) y no muta estado entre ejemplos; suprimimos el aviso.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(identificador=_identificadores_invalidos)
def test_identificador_sin_silla_siempre_da_404(cliente, identificador):
    """Rama generativa: todo identificador que no resuelve a una silla → 404.

    Cubre tanto UUIDs bien formados pero inexistentes como cadenas sin formato
    UUID. En ambos casos la respuesta es siempre HTTP 404 con el mensaje
    "QR no válido". La tabla `silla` está vacía en esta prueba (el fixture
    `_limpiar_tablas` la trunca), así que ningún identificador puede resolver.

    _Requirements: 1.3, 1.4, 3.1_
    """
    respuesta = cliente.get(f"/qr/silla/{identificador}")

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == MENSAJE_QR_INVALIDO
