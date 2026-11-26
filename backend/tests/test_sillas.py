import re
import uuid

from sqlalchemy import func, select

from app.models import Silla, Visita

PATRON_QR = re.compile(r"^SIC-\d{8}$")
SERIAL_DUPLICADO = "serial_antiguo duplicado para la empresa"


def _registrar(cliente, auth, tecnico, visita, empleado, **extra):
    cuerpo = {"id_empleado": empleado.id_empleado, "cargo": empleado.cargo, **extra}
    return cliente.post(
        f"/visitas/{visita.id_visita}/sillas",
        json=cuerpo,
        headers=auth(tecnico),
    )


def test_registrar_silla_ok(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = _registrar(
        cliente,
        auth,
        datos["tecnico"],
        datos["visita"],
        datos["empleado"],
        serial_antiguo="OLD-001",
        observaciones="Asiento rasgado",
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id_empresa"] == datos["empleado"].id_empresa
    assert cuerpo["id_sede"] == datos["empleado"].id_sede
    assert cuerpo["id_departamento"] == datos["empleado"].id_departamento
    assert cuerpo["id_empleado"] == datos["empleado"].id_empleado
    assert cuerpo["cargo"] == datos["empleado"].cargo
    assert PATRON_QR.match(cuerpo["codigo_qr"]), cuerpo["codigo_qr"]
    assert uuid.UUID(cuerpo["token_publico"])


def test_registrar_silla_campos_faltantes(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.post(
        f"/visitas/{datos['visita'].id_visita}/sillas",
        json={"id_empleado": datos["empleado"].id_empleado},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 400, respuesta.text
    assert "cargo" in respuesta.json()["detail"]


def test_registrar_silla_visita_ajena(cliente, fabrica, auth):
    datos = fabrica.escenario()
    otro_tecnico = fabrica.usuario("TECNICO")

    respuesta = _registrar(
        cliente,
        auth,
        otro_tecnico,
        datos["visita"],
        datos["empleado"],
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No autorizado para esta visita"


def test_registrar_silla_requiere_tecnico(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = _registrar(
        cliente,
        auth,
        datos["comercial"],
        datos["visita"],
        datos["empleado"],
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "Rol no autorizado"


def test_registrar_silla_empleado_de_otra_sede(cliente, fabrica, auth):
    datos = fabrica.escenario()
    otra_sede = fabrica.sede(datos["empresa"])
    otro_departamento = fabrica.departamento(datos["empresa"], otra_sede)
    empleado_ajeno = fabrica.empleado(datos["empresa"], otra_sede, otro_departamento)

    respuesta = _registrar(
        cliente,
        auth,
        datos["tecnico"],
        datos["visita"],
        empleado_ajeno,
    )

    assert respuesta.status_code == 400
    assert "no pertenece" in respuesta.json()["detail"]


def test_sillas_no_se_limitan_por_cantidad_estimada(cliente, fabrica, auth):
    datos = fabrica.escenario()
    cantidad = datos["visita"].cantidad_estimada

    for _ in range(cantidad + 3):
        respuesta = _registrar(
            cliente,
            auth,
            datos["tecnico"],
            datos["visita"],
            datos["empleado"],
        )
        assert respuesta.status_code == 201, respuesta.text


def test_registrar_adicionales_no_cambia_cantidad_estimada(cliente, fabrica, auth, db):
    """HU-02 Req 1.2: the visit's cantidad_estimada is preserved after extra chairs."""
    datos = fabrica.escenario()
    visita = datos["visita"]
    estimada = visita.cantidad_estimada

    for _ in range(estimada + 2):
        assert _registrar(
            cliente, auth, datos["tecnico"], visita, datos["empleado"]
        ).status_code == 201

    db.expire_all()
    recargada = db.get(Visita, visita.id_visita)
    assert recargada.cantidad_estimada == estimada


def test_listar_sillas_de_visita(cliente, fabrica, auth):
    """HU-02 Req 2.1/2.2: the real count is the number of listed chairs, and
    chairs of a different visit are not included."""
    datos = fabrica.escenario()
    estimada = datos["visita"].cantidad_estimada
    total = estimada + 3
    for _ in range(total):
        assert _registrar(
            cliente, auth, datos["tecnico"], datos["visita"], datos["empleado"]
        ).status_code == 201

    # A second visit of the same empresa/technician with its own chairs. These
    # must not leak into the first visit's listing.
    otra_sede = fabrica.sede(datos["empresa"])
    otro_departamento = fabrica.departamento(datos["empresa"], otra_sede)
    otro_empleado = fabrica.empleado(datos["empresa"], otra_sede, otro_departamento)
    otra_visita = fabrica.visita(
        datos["empresa"], otra_sede, datos["comercial"], datos["tecnico"]
    )
    for _ in range(2):
        assert _registrar(
            cliente, auth, datos["tecnico"], otra_visita, otro_empleado
        ).status_code == 201

    respuesta = cliente.get(
        "/sillas",
        params={"id_visita": datos["visita"].id_visita},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert len(cuerpo) == total
    assert total > estimada
    assert all(silla["id_visita"] == datos["visita"].id_visita for silla in cuerpo)


def test_listar_sillas_visita_sin_sillas(cliente, fabrica, auth):
    """HU-02 Req 2.3: an existing visit with no chairs returns an empty list."""
    datos = fabrica.escenario()

    respuesta = cliente.get(
        "/sillas",
        params={"id_visita": datos["visita"].id_visita},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


def test_listar_sillas_visita_inexistente(cliente, fabrica, auth):
    """HU-02 Req 2.4: an unknown visit returns 404."""
    datos = fabrica.escenario()

    respuesta = cliente.get(
        "/sillas",
        params={"id_visita": 999999},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 404


def test_listar_sillas_requiere_id_visita(cliente, fabrica, auth):
    """HU-02: the id_visita query parameter is required (422 when missing)."""
    datos = fabrica.escenario()

    respuesta = cliente.get("/sillas", headers=auth(datos["tecnico"]))

    assert respuesta.status_code == 422


def test_listar_sillas_tecnico_ajeno(cliente, fabrica, auth):
    """HU-02 Req 2.5: a technician cannot list chairs of a visit that is not theirs."""
    datos = fabrica.escenario()
    otro_tecnico = fabrica.usuario("TECNICO")

    respuesta = cliente.get(
        "/sillas",
        params={"id_visita": datos["visita"].id_visita},
        headers=auth(otro_tecnico),
    )

    assert respuesta.status_code == 403


def test_listar_sillas_comercial_cualquier_visita(cliente, fabrica, auth):
    """HU-02 Req 2.6: a commercial may list chairs of a visit assigned to a
    different commercial (access to any visit, not only their own)."""
    datos = fabrica.escenario()
    assert _registrar(
        cliente, auth, datos["tecnico"], datos["visita"], datos["empleado"]
    ).status_code == 201
    otro_comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.get(
        "/sillas",
        params={"id_visita": datos["visita"].id_visita},
        headers=auth(otro_comercial),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert len(respuesta.json()) == 1


def test_listar_sillas_rol_no_autorizado(cliente, fabrica, auth):
    """HU-02 Req 2.7: a role other than tecnico/comercial is rejected."""
    datos = fabrica.escenario()
    admin_cliente = fabrica.usuario("ADMIN_CLIENTE", empresa=datos["empresa"])

    respuesta = cliente.get(
        "/sillas",
        params={"id_visita": datos["visita"].id_visita},
        headers=auth(admin_cliente),
    )

    assert respuesta.status_code == 403


def test_listar_sillas_sin_autenticacion(cliente, fabrica):
    """HU-02: without a bearer token and without the dev stub header
    (`X-Dev-User-Id`), the request is rejected by the existing
    `get_current_user` dependency. In the test environment `DEV_USER_ID` is
    unset, so no identity can be resolved and the response is 401."""
    datos = fabrica.escenario()

    respuesta = cliente.get(
        "/sillas",
        params={"id_visita": datos["visita"].id_visita},
    )

    assert respuesta.status_code == 401


def test_consulta_silla_y_token(cliente, fabrica, auth):
    datos = fabrica.escenario()
    creada = _registrar(
        cliente,
        auth,
        datos["tecnico"],
        datos["visita"],
        datos["empleado"],
        serial_antiguo="OLD-XYZ",
        observaciones="Sin ruedas",
    ).json()

    como_comercial = cliente.get(
        f"/sillas/{creada['id_silla']}",
        headers=auth(datos["comercial"]),
    )
    assert como_comercial.status_code == 200, como_comercial.text
    cuerpo = como_comercial.json()
    assert cuerpo["serial_antiguo"] == "OLD-XYZ"
    assert cuerpo["observaciones"] == "Sin ruedas"
    assert cuerpo["codigo_qr"] == creada["codigo_qr"]
    assert cuerpo["token_publico"] == creada["token_publico"]

    publica = cliente.get(f"/sillas/token/{creada['token_publico']}")
    assert publica.status_code == 200, publica.text
    assert publica.json()["codigo_qr"] == creada["codigo_qr"]
    assert publica.json()["id_silla"] == creada["id_silla"]


def test_token_desconocido_da_404(cliente):
    respuesta = cliente.get(f"/sillas/token/{uuid.uuid4()}")
    assert respuesta.status_code == 404
    assert cliente.get("/sillas/token/no-es-uuid").status_code == 404


def test_tecnico_ajeno_no_lee_silla(cliente, fabrica, auth):
    datos = fabrica.escenario()
    creada = _registrar(
        cliente,
        auth,
        datos["tecnico"],
        datos["visita"],
        datos["empleado"],
    ).json()
    otro_tecnico = fabrica.usuario("TECNICO")

    respuesta = cliente.get(
        f"/sillas/{creada['id_silla']}",
        headers=auth(otro_tecnico),
    )

    assert respuesta.status_code == 403


def test_actualizar_observaciones(cliente, fabrica, auth):
    datos = fabrica.escenario()
    creada = _registrar(
        cliente,
        auth,
        datos["tecnico"],
        datos["visita"],
        datos["empleado"],
    ).json()

    respuesta = cliente.put(
        f"/sillas/{creada['id_silla']}",
        json={"observaciones": "Revisar cilindro", "serial_antiguo": "SER-NEW"},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["observaciones"] == "Revisar cilindro"
    assert respuesta.json()["serial_antiguo"] == "SER-NEW"


def test_codigos_qr_nunca_se_reutilizan(cliente, fabrica, auth, db):
    """Property 1: QR codes are never reused, even after chairs are deleted."""
    datos = fabrica.escenario()
    empresa = datos["empresa"]
    comercial = datos["comercial"]
    tecnico = datos["tecnico"]

    segunda = fabrica.sede(empresa)
    segundo_departamento = fabrica.departamento(empresa, segunda)
    segundo_empleado = fabrica.empleado(empresa, segunda, segundo_departamento)
    visita = fabrica.visita(empresa, segunda, comercial, tecnico)

    for _ in range(60):
        assert _registrar(cliente, auth, tecnico, visita, segundo_empleado).status_code == 201

    borradas = db.scalars(select(Silla).order_by(Silla.id_silla).limit(10)).all()
    numeros_borrados = {silla.numero_qr for silla in borradas}
    for silla in borradas:
        db.delete(silla)
    db.commit()

    for _ in range(40):
        assert _registrar(cliente, auth, tecnico, visita, segundo_empleado).status_code == 201

    restantes = db.scalars(select(Silla).order_by(Silla.id_silla)).all()
    numeros = [silla.numero_qr for silla in restantes]
    codigos = [silla.codigo_qr for silla in restantes]

    assert len(numeros) == 90
    assert numeros == sorted(numeros)
    assert len(set(numeros)) == len(numeros)
    assert len(set(codigos)) == len(codigos)
    assert min(numeros) > max(numeros_borrados)
    for silla in restantes:
        assert silla.codigo_qr == f"SIC-{silla.numero_qr:08d}"


def test_serial_antiguo_duplicado_por_empresa(cliente, fabrica, auth, db):
    """Property 2: duplicate legacy serials are rejected inside one empresa."""
    datos = fabrica.escenario()
    empresa_b = fabrica.empresa()
    sede_b = fabrica.sede(empresa_b)
    departamento_b = fabrica.departamento(empresa_b, sede_b)
    empleado_b = fabrica.empleado(empresa_b, sede_b, departamento_b)
    visita_b = fabrica.visita(
        empresa_b,
        sede_b,
        datos["comercial"],
        datos["tecnico"],
    )

    for indice in range(100):
        serial = f"SER-{indice:03d}"

        primera = _registrar(
            cliente,
            auth,
            datos["tecnico"],
            datos["visita"],
            datos["empleado"],
            serial_antiguo=serial,
        )
        assert primera.status_code == 201, primera.text

        sillas_antes = db.scalar(select(func.count()).select_from(Silla))

        duplicada = _registrar(
            cliente,
            auth,
            datos["tecnico"],
            datos["visita"],
            datos["empleado"],
            serial_antiguo=serial,
        )
        assert duplicada.status_code == 409, duplicada.text
        assert duplicada.json()["detail"] == SERIAL_DUPLICADO

        db.expire_all()
        assert db.scalar(select(func.count()).select_from(Silla)) == sillas_antes

        otra_empresa = _registrar(
            cliente,
            auth,
            datos["tecnico"],
            visita_b,
            empleado_b,
            serial_antiguo=serial,
        )
        assert otra_empresa.status_code == 201, otra_empresa.text

    assert db.scalar(select(func.count()).select_from(Silla)) == 200
