"""Property test P3: round-trip del permiso QR (HU-18).

# Feature: qr-publico-permisos-tickets, Property 3

**Property 3: Round-trip del permiso QR**

*Para todo* valor `v` en {1, 2, 3}, cuando un `ADMIN_CLIENTE` actualiza el
permiso de su empresa a `v` (`PUT /qr/empresas/{id_empresa}/permiso-qr`) y a
continuación lo lee (`GET /qr/empresas/{id_empresa}/permiso-qr`), obtiene
exactamente `v`.

**Validates: Requirements 2.1, 2.2**

Nota sobre Hypothesis + fixtures de pytest con ámbito de función: `cliente`,
`fabrica` (y la sesión `db` de la que depende) se crean una sola vez por función
de prueba, y Hypothesis reutiliza esas instancias en cada ejemplo. Aquí la
reutilización es deliberada y segura: el `ADMIN_CLIENTE` y su empresa se crean
UNA vez fuera del `@given`, y cada ejemplo solo hace un PUT seguido de un GET.
Como el PUT sobrescribe `empresa.permiso_qr`, no se acumula estado entre
ejemplos (el valor anterior queda reemplazado), así que no hace falta limpiar.
Se suprime `HealthCheck.function_scoped_fixture` por esta reutilización
intencionada.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from helpers_qr import NIVELES_PERMISO_QR, crear_admin_cliente

# Niveles válidos de `empresa.permiso_qr` (CHECK IN (1, 2, 3) en la BD).
_niveles = st.sampled_from(NIVELES_PERMISO_QR)

# Caché del admin/empresa creados una sola vez por ejecución del test: el cuerpo
# de `@given` se reejecuta por cada `v`, pero las filas se crean solo la primera
# vez (ver nota en el docstring sobre la reutilización deliberada de fixtures).
_estado: dict = {}


# Feature: qr-publico-permisos-tickets, Property 3
@settings(
    max_examples=100,
    # `cliente`/`fabrica`/`db` son fixtures con ámbito de función que Hypothesis
    # reutiliza entre ejemplos. El admin/empresa se crean UNA vez (cacheados en
    # `_estado`) y se reutilizan en cada ejemplo; cada ejemplo solo escribe (PUT)
    # y lee (GET) el permiso, y el PUT sobrescribe el valor anterior, de modo que
    # la reutilización no acumula estado. Suprimimos el aviso de forma explícita.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(permiso=_niveles)
def test_put_permiso_luego_get_devuelve_el_mismo_valor(
    cliente,
    fabrica,
    auth,
    permiso,
):
    """PUT de un permiso válido seguido de GET devuelve exactamente ese valor.

    El `ADMIN_CLIENTE` (ligado a su empresa) y la empresa se crean una sola vez
    (fuera del bucle de ejemplos, vía caché) y se reutilizan; para cada `v` en
    {1, 2, 3} el test hace PUT del permiso y luego GET, y comprueba que el valor
    leído coincide con el escrito (y que `id_empresa` es el de la empresa del
    admin). Como el PUT sobrescribe el permiso, reutilizar la misma empresa entre
    ejemplos es seguro.

    _Requirements: 2.1, 2.2_
    """
    # Crear el admin/empresa una sola vez y reutilizarlos entre ejemplos: el
    # cuerpo de `@given` se reejecuta por cada `v`, pero solo la primera llamada
    # crea filas; las siguientes toman el admin cacheado.
    admin = _estado.get("admin")
    if admin is None:
        admin = crear_admin_cliente(fabrica)
        _estado["admin"] = admin

    id_empresa = admin.id_empresa
    headers = auth(admin)

    put_resp = cliente.put(
        f"/qr/empresas/{id_empresa}/permiso-qr",
        json={"permiso_qr": permiso},
        headers=headers,
    )
    assert put_resp.status_code == 200, put_resp.text
    assert put_resp.json()["permiso_qr"] == permiso

    get_resp = cliente.get(
        f"/qr/empresas/{id_empresa}/permiso-qr",
        headers=headers,
    )
    assert get_resp.status_code == 200, get_resp.text
    cuerpo = get_resp.json()
    assert cuerpo["id_empresa"] == id_empresa
    assert cuerpo["permiso_qr"] == permiso
