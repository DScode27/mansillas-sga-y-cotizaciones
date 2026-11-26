"""Pruebas de ejemplo de HU-18: configuración del permiso QR por empresa.

Cubren los endpoints `GET`/`PUT /qr/empresas/{id_empresa}/permiso-qr` del router
`app/routers/qr.py`: lectura y actualización del permiso de la propia empresa,
aislamiento multiempresa, validación del nivel y control de rol.

- _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
"""

import pytest

from helpers_qr import NIVELES_PERMISO_QR, crear_admin_cliente

RUTA = "/qr/empresas/{id_empresa}/permiso-qr"


def test_admin_cliente_lee_permiso_de_su_empresa(cliente, fabrica, auth):
    """2.1: el `ADMIN_CLIENTE` lee `permiso_qr` de su propia empresa (200)."""
    empresa = fabrica.empresa()
    admin = crear_admin_cliente(fabrica, empresa=empresa)

    respuesta = cliente.get(
        RUTA.format(id_empresa=empresa.id_empresa),
        headers=auth(admin),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id_empresa"] == empresa.id_empresa
    # La BD aplica DEFAULT 1 al crear la empresa.
    assert cuerpo["permiso_qr"] == 1


@pytest.mark.parametrize("permiso", NIVELES_PERMISO_QR)
def test_admin_cliente_actualiza_y_relee_permiso(cliente, fabrica, auth, permiso):
    """2.2: el `ADMIN_CLIENTE` fija 1/2/3 (200) y la lectura devuelve el nuevo valor."""
    empresa = fabrica.empresa()
    admin = crear_admin_cliente(fabrica, empresa=empresa)
    ruta = RUTA.format(id_empresa=empresa.id_empresa)

    respuesta_put = cliente.put(ruta, json={"permiso_qr": permiso}, headers=auth(admin))

    assert respuesta_put.status_code == 200, respuesta_put.text
    assert respuesta_put.json() == {
        "id_empresa": empresa.id_empresa,
        "permiso_qr": permiso,
    }

    respuesta_get = cliente.get(ruta, headers=auth(admin))

    assert respuesta_get.status_code == 200, respuesta_get.text
    assert respuesta_get.json()["permiso_qr"] == permiso


def test_aislamiento_multiempresa_get(cliente, fabrica, auth):
    """2.5: un `ADMIN_CLIENTE` de la empresa A no puede leer el permiso de la B."""
    empresa_a = fabrica.empresa("Empresa A")
    empresa_b = fabrica.empresa("Empresa B")
    admin_a = crear_admin_cliente(fabrica, empresa=empresa_a)

    respuesta = cliente.get(
        RUTA.format(id_empresa=empresa_b.id_empresa),
        headers=auth(admin_a),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No autorizado para esta empresa"


def test_aislamiento_multiempresa_put(cliente, fabrica, auth):
    """2.5: un `ADMIN_CLIENTE` de la empresa A no puede modificar el permiso de la B."""
    empresa_a = fabrica.empresa("Empresa A")
    empresa_b = fabrica.empresa("Empresa B")
    admin_a = crear_admin_cliente(fabrica, empresa=empresa_a)

    respuesta = cliente.put(
        RUTA.format(id_empresa=empresa_b.id_empresa),
        json={"permiso_qr": 2},
        headers=auth(admin_a),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No autorizado para esta empresa"


@pytest.mark.parametrize("permiso_invalido", [0, 4])
def test_put_valor_invalido(cliente, fabrica, auth, permiso_invalido):
    """2.6: un nivel fuera de {1, 2, 3} responde 422 con el mensaje de dominio."""
    empresa = fabrica.empresa()
    admin = crear_admin_cliente(fabrica, empresa=empresa)

    respuesta = cliente.put(
        RUTA.format(id_empresa=empresa.id_empresa),
        json={"permiso_qr": permiso_invalido},
        headers=auth(admin),
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["detail"] == "permiso_qr debe ser 1, 2 o 3"


@pytest.mark.parametrize(
    "rol",
    ["TECNICO", "COMERCIAL_MANSILLAS", "EMPLEADO_CLIENTE"],
)
def test_rol_distinto_de_admin_cliente_rechazado(cliente, fabrica, auth, rol):
    """2.3/2.4: cualquier rol que no sea `ADMIN_CLIENTE` recibe 403 "Rol no autorizado".

    `TECNICO` y `COMERCIAL_MANSILLAS` no tienen empresa; `EMPLEADO_CLIENTE` sí.
    El control de rol (`require_role`) actúa antes que el de empresa, por lo que
    el mensaje es "Rol no autorizado" independientemente de la empresa objetivo.
    """
    empresa = fabrica.empresa()
    usuario = fabrica.usuario(
        rol=rol,
        empresa=empresa if rol == "EMPLEADO_CLIENTE" else None,
    )

    ruta = RUTA.format(id_empresa=empresa.id_empresa)

    respuesta_get = cliente.get(ruta, headers=auth(usuario))
    assert respuesta_get.status_code == 403
    assert respuesta_get.json()["detail"] == "Rol no autorizado"

    respuesta_put = cliente.put(
        ruta, json={"permiso_qr": 2}, headers=auth(usuario)
    )
    assert respuesta_put.status_code == 403
    assert respuesta_put.json()["detail"] == "Rol no autorizado"
