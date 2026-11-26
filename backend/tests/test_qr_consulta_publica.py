"""Pruebas de ejemplo de HU-17: consulta pública de silla por QR.

Cubren el endpoint público `GET /qr/silla/{token}` (el router `qr.py` lleva el
prefijo `/qr`): la consulta válida devuelve los datos básicos de la silla más el
`permiso_qr` de la empresa dueña; un token inexistente o con formato no-UUID se
rechaza con 404 "QR no válido"; la respuesta nunca expone nombre, documento ni
correo del empleado (RN-3/RN-4), y la ruta no exige `get_current_user`.

_Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
"""

import uuid


def test_consulta_valida_devuelve_datos_basicos_y_permiso(cliente, fabrica):
    """Token válido → 200 con datos básicos de la silla y `permiso_qr`.

    _Requirements: 1.1_
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
    # La empresa arranca con el DEFAULT 1 de la BD (CHECK IN (1,2,3)).
    assert cuerpo["permiso_qr"] == 1


def test_token_inexistente_da_404(cliente, fabrica):
    """UUID bien formado pero sin silla → 404 "QR no válido".

    _Requirements: 1.3_
    """
    # Escenario creado para asegurar que hay sillas en la BD, pero este UUID no
    # pertenece a ninguna de ellas.
    fabrica.escenario()
    token_ausente = uuid.uuid4()

    respuesta = cliente.get(f"/qr/silla/{token_ausente}")

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "QR no válido"


def test_token_no_uuid_da_404(cliente, fabrica):
    """Valor sin formato UUID → 404 "QR no válido".

    _Requirements: 1.4_
    """
    fabrica.escenario()

    respuesta = cliente.get("/qr/silla/no-es-un-uuid")

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "QR no válido"


def test_respuesta_no_expone_datos_personales(cliente, fabrica):
    """La respuesta pública nunca incluye nombre, documento ni correo.

    _Requirements: 1.5_
    """
    datos = fabrica.escenario()
    empleado = datos["empleado"]
    silla = fabrica.silla(datos["visita"], empleado)

    respuesta = cliente.get(f"/qr/silla/{silla.token_publico}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert empleado.nombre not in cuerpo.values()
    assert empleado.documento not in cuerpo.values()
    assert empleado.correo not in cuerpo.values()
    # Comprobación sobre el texto crudo: ni siquiera como subcadena del cuerpo.
    crudo = respuesta.text
    assert empleado.nombre not in crudo
    assert empleado.documento not in crudo
    assert empleado.correo not in crudo


def test_consulta_publica_no_exige_autenticacion(cliente, fabrica):
    """La ruta responde 200 sin cabecera de auth (sin `X-Dev-User-Id`).

    _Requirements: 1.2_
    """
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])

    # Sin pasar `headers=auth(...)`: la ruta pública no usa `get_current_user`.
    respuesta = cliente.get(f"/qr/silla/{silla.token_publico}")

    assert respuesta.status_code == 200, respuesta.text
