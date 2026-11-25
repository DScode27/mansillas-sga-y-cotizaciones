from app.models import Precotizacion
from app.routers.accesos import registrar_acceso

UA_CHROME_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
UA_SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)


def _precotizacion(db, datos) -> Precotizacion:
    precotizacion = Precotizacion(
        id_empresa=datos["empresa"].id_empresa,
        id_visita=datos["visita"].id_visita,
        creada_por=datos["comercial"].id_usuario,
    )
    db.add(precotizacion)
    db.commit()
    db.refresh(precotizacion)
    return precotizacion


def test_parsea_user_agent(db, fabrica):
    datos = fabrica.escenario()
    precotizacion = _precotizacion(db, datos)

    acceso = registrar_acceso(db, precotizacion.id_precotizacion, UA_CHROME_WINDOWS)

    assert acceso.id_precotizacion == precotizacion.id_precotizacion
    assert acceso.navegador == "Chrome"
    assert acceso.sistema_operativo == "Windows"
    assert acceso.fecha_acceso is not None


def test_parsea_user_agent_movil(db, fabrica):
    datos = fabrica.escenario()
    precotizacion = _precotizacion(db, datos)

    acceso = registrar_acceso(db, precotizacion.id_precotizacion, UA_SAFARI_IPHONE)

    assert "Mobile" in acceso.navegador
    assert "iOS" in acceso.sistema_operativo


def test_log_vacio(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    precotizacion = _precotizacion(db, datos)

    respuesta = cliente.get(
        f"/precotizaciones/{precotizacion.id_precotizacion}/accesos",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"mensaje": "Sin accesos registrados"}


def test_log_con_accesos(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    precotizacion = _precotizacion(db, datos)
    registrar_acceso(db, precotizacion.id_precotizacion, UA_CHROME_WINDOWS)
    registrar_acceso(db, precotizacion.id_precotizacion, UA_SAFARI_IPHONE)

    respuesta = cliente.get(
        f"/precotizaciones/{precotizacion.id_precotizacion}/accesos",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    accesos = respuesta.json()
    assert len(accesos) == 2
    assert {acceso["navegador"] for acceso in accesos} == {"Chrome", "Mobile Safari"}


def test_log_requiere_comercial(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    precotizacion = _precotizacion(db, datos)
    registrar_acceso(db, precotizacion.id_precotizacion, UA_CHROME_WINDOWS)

    respuesta = cliente.get(
        f"/precotizaciones/{precotizacion.id_precotizacion}/accesos",
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "Rol no autorizado"


def test_log_precotizacion_inexistente(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.get(
        "/precotizaciones/999999/accesos",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 404


def test_acceso_requiere_usuario_valido(cliente, fabrica, db):
    datos = fabrica.escenario()
    precotizacion = _precotizacion(db, datos)

    respuesta = cliente.get(
        f"/precotizaciones/{precotizacion.id_precotizacion}/accesos",
        headers={"X-Dev-User-Id": "999999"},
    )

    assert respuesta.status_code == 401
