import time

from app.config import settings
from app.routers.qr import url_publica_silla


def _sillas(fabrica, datos, cantidad=5):
    return [fabrica.silla(datos["visita"], datos["empleado"]) for _ in range(cantidad)]


def test_pdf_ok(cliente, fabrica, auth):
    datos = fabrica.escenario()
    sillas = _sillas(fabrica, datos, 5)

    respuesta = cliente.post(
        "/qr/pdf",
        json={"ids": [silla.id_silla for silla in sillas]},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.content.startswith(b"%PDF")
    assert len(respuesta.content) > 1000


def test_pdf_codifica_url_publica(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])

    assert url_publica_silla(silla) == (
        f"{settings.frontend_url.rstrip('/')}/qr/{silla.token_publico}"
    )


def test_pdf_tecnico_propio(cliente, fabrica, auth):
    datos = fabrica.escenario()
    sillas = _sillas(fabrica, datos, 2)

    respuesta = cliente.post(
        "/qr/pdf",
        json={"ids": [silla.id_silla for silla in sillas]},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.content.startswith(b"%PDF")


def test_pdf_tecnico_ajeno_da_403(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla_ajena = fabrica.silla(datos["visita"], datos["empleado"])
    otro_tecnico = fabrica.usuario("TECNICO")

    respuesta = cliente.post(
        "/qr/pdf",
        json={"ids": [silla_ajena.id_silla]},
        headers=auth(otro_tecnico),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No autorizado para esta visita"


def test_pdf_comercial_cualquier_empresa(cliente, fabrica, auth):
    datos = fabrica.escenario()
    empresa_b = fabrica.empresa()
    sede_b = fabrica.sede(empresa_b)
    departamento_b = fabrica.departamento(empresa_b, sede_b)
    empleado_b = fabrica.empleado(empresa_b, sede_b, departamento_b)
    otro_tecnico = fabrica.usuario("TECNICO")
    visita_b = fabrica.visita(empresa_b, sede_b, datos["comercial"], otro_tecnico)

    ids = [
        fabrica.silla(datos["visita"], datos["empleado"]).id_silla,
        fabrica.silla(visita_b, empleado_b).id_silla,
    ]

    respuesta = cliente.post(
        "/qr/pdf",
        json={"ids": ids},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text


def test_pdf_sin_ids(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.post(
        "/qr/pdf",
        json={"ids": []},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 400


def test_pdf_id_inexistente(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.post(
        "/qr/pdf",
        json={"ids": [999999]},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 404


def test_pdf_50_sillas_en_menos_de_20s(cliente, fabrica, auth):
    datos = fabrica.escenario()
    sillas = _sillas(fabrica, datos, 50)

    inicio = time.perf_counter()
    respuesta = cliente.post(
        "/qr/pdf",
        json={"ids": [silla.id_silla for silla in sillas]},
        headers=auth(datos["comercial"]),
    )
    transcurrido = time.perf_counter() - inicio

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.content.startswith(b"%PDF")
    assert transcurrido < 20
