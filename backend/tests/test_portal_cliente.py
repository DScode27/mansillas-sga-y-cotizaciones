"""Pruebas del portal cliente (M7, R4): solo lectura, acotado por empresa.

Ejercitan `GET /portal-cliente/sillas` y `GET /portal-cliente/precotizaciones`
contra PostgreSQL real (fixtures `cliente`, `fabrica`, `auth`, `db` de
`conftest.py`). El ADMIN_CLIENTE solo ve datos de su propia empresa; cualquier
otro rol recibe 403 y sin sesión 401.
"""

from __future__ import annotations

from app.models import Precotizacion


def _registrar_silla(cliente, auth, datos):
    """Crea una silla de la visita del escenario (como técnico dueño)."""
    resp = cliente.post(
        f"/visitas/{datos['visita'].id_visita}/sillas",
        json={
            "id_empleado": datos["empleado"].id_empleado,
            "cargo": datos["empleado"].cargo,
        },
        headers=auth(datos["tecnico"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_sillas_admin_ve_solo_su_empresa(cliente, fabrica, auth):
    """El ADMIN_CLIENTE ve las sillas de su empresa y nunca las de otra (R4)."""
    propio = fabrica.escenario()
    ajeno = fabrica.escenario()
    _registrar_silla(cliente, auth, propio)
    _registrar_silla(cliente, auth, ajeno)

    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=propio["empresa"])
    respuesta = cliente.get("/portal-cliente/sillas", headers=auth(admin))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert len(cuerpo) == 1
    silla = cuerpo[0]
    assert silla["sede"] == propio["sede"].nombre
    assert silla["cargo"] == propio["empleado"].cargo
    assert "componentes" in silla
    assert "sugerir_cambio" in silla
    assert silla["fotos"] == []


def test_sillas_admin_sin_sillas_da_lista_vacia(cliente, fabrica, auth):
    """Un ADMIN_CLIENTE de una empresa sin sillas recibe 200 con lista vacía."""
    empresa = fabrica.empresa()
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)

    respuesta = cliente.get("/portal-cliente/sillas", headers=auth(admin))
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


def test_sillas_rol_no_admin_cliente_da_403(cliente, fabrica, auth):
    """Un rol distinto de ADMIN_CLIENTE no puede usar el portal cliente."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    respuesta = cliente.get("/portal-cliente/sillas", headers=auth(comercial))
    assert respuesta.status_code == 403


def test_sillas_sin_sesion_da_401(cliente):
    """Sin cabecera de sesión, el portal cliente responde 401."""
    assert cliente.get("/portal-cliente/sillas").status_code == 401


def test_precotizaciones_admin_ve_solo_su_empresa(cliente, fabrica, auth, db):
    """El ADMIN_CLIENTE ve las precotizaciones de su empresa, no las ajenas."""
    propio = fabrica.escenario()
    ajeno = fabrica.escenario()

    # Precotización de la empresa propia y otra de una empresa ajena.
    pre_propia = Precotizacion(
        id_empresa=propio["empresa"].id_empresa,
        id_visita=propio["visita"].id_visita,
        estado="BORRADOR",
        creada_por=propio["comercial"].id_usuario,
        observaciones="Propia",
    )
    pre_ajena = Precotizacion(
        id_empresa=ajeno["empresa"].id_empresa,
        id_visita=ajeno["visita"].id_visita,
        estado="BORRADOR",
        creada_por=ajeno["comercial"].id_usuario,
        observaciones="Ajena",
    )
    db.add_all([pre_propia, pre_ajena])
    db.commit()

    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=propio["empresa"])
    respuesta = cliente.get(
        "/portal-cliente/precotizaciones", headers=auth(admin)
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert len(cuerpo) == 1
    assert cuerpo[0]["observaciones"] == "Propia"


def test_precotizaciones_rol_no_admin_da_403(cliente, fabrica, auth):
    tecnico = fabrica.usuario("TECNICO")
    respuesta = cliente.get(
        "/portal-cliente/precotizaciones", headers=auth(tecnico)
    )
    assert respuesta.status_code == 403


# --- Acceso del ADMIN_CLIENTE a las fotos de sus sillas (R4) ---------------

from app.models import Fotografia  # noqa: E402
from app.services import fotos_storage  # noqa: E402

# PNG 1x1 válido para que `fotos_storage` lo acepte al guardar/servir.
_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f6f0000000049454e44ae426082"
)


def _foto_de(db, id_silla: int) -> Fotografia:
    nombre = fotos_storage.guardar(_PNG_1X1, ".png")
    foto = Fotografia(id_silla=id_silla, ruta_archivo=nombre)
    db.add(foto)
    db.commit()
    db.refresh(foto)
    return foto


def test_admin_ve_foto_de_su_empresa(cliente, fabrica, auth, db):
    """El ADMIN_CLIENTE puede bajar la foto de una silla de su empresa (R4)."""
    datos = fabrica.escenario()
    cuerpo = _registrar_silla(cliente, auth, datos)
    foto = _foto_de(db, cuerpo["id_silla"])
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=datos["empresa"])
    try:
        resp = cliente.get(
            f"/sillas/{cuerpo['id_silla']}/fotos/{foto.id_fotografia}",
            headers=auth(admin),
        )
        assert resp.status_code == 200, resp.text
        assert resp.content == _PNG_1X1
    finally:
        fotos_storage.eliminar(foto.ruta_archivo)


def test_admin_no_ve_foto_de_otra_empresa(cliente, fabrica, auth, db):
    """El ADMIN_CLIENTE no puede bajar fotos de sillas de otra empresa (403)."""
    ajeno = fabrica.escenario()
    cuerpo = _registrar_silla(cliente, auth, ajeno)
    foto = _foto_de(db, cuerpo["id_silla"])
    empresa_propia = fabrica.empresa()
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa_propia)
    try:
        resp = cliente.get(
            f"/sillas/{cuerpo['id_silla']}/fotos/{foto.id_fotografia}",
            headers=auth(admin),
        )
        assert resp.status_code == 403
    finally:
        fotos_storage.eliminar(foto.ruta_archivo)
