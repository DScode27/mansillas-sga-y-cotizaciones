"""HU-12 / HU-13 tests: survey consult and edit, pre-quotation create/list,
link send, and public proposal consult.

Integration cases use the shared `conftest.py` fixtures against the isolated,
disposable PostgreSQL (`TEST_DATABASE_URL`); never the shared Supabase DB. SMTP
is mocked (no real mail). Some pre-quotation rows are inserted directly through
the `db` fixture to set a specific `estado` for a scenario.
"""

from sqlalchemy import func, select

from app.models import Precotizacion


def _crear_silla(cliente, auth, datos, **extra):
    cuerpo = {"id_empleado": datos["empleado"].id_empleado, "cargo": datos["empleado"].cargo, **extra}
    respuesta = cliente.post(
        f"/visitas/{datos['visita'].id_visita}/sillas",
        json=cuerpo,
        headers=auth(datos["tecnico"]),
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _insertar_precotizacion(db, datos, estado):
    pre = Precotizacion(
        id_empresa=datos["empresa"].id_empresa,
        id_visita=datos["visita"].id_visita,
        estado=estado,
        creada_por=datos["comercial"].id_usuario,
    )
    db.add(pre)
    db.commit()
    db.refresh(pre)
    return pre


# --- GET /visitas/{id}/levantamiento (Requirement 1) ------------------------

def test_consultar_levantamiento_ok(cliente, fabrica, auth):
    datos = fabrica.escenario()
    _crear_silla(cliente, auth, datos)
    _crear_silla(cliente, auth, datos)

    respuesta = cliente.get(
        f"/visitas/{datos['visita'].id_visita}/levantamiento",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["visita"]["id_visita"] == datos["visita"].id_visita
    assert len(cuerpo["sillas"]) == 2
    assert cuerpo["tiene_precotizacion"] is False
    # deterministic order by id_silla
    ids = [s["id_silla"] for s in cuerpo["sillas"]]
    assert ids == sorted(ids)


def test_consultar_levantamiento_sin_sillas(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.get(
        f"/visitas/{datos['visita'].id_visita}/levantamiento",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["sillas"] == []
    assert respuesta.json()["tiene_precotizacion"] is False


def test_consultar_levantamiento_visita_inexistente(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.get(
        "/visitas/999999/levantamiento",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 404


def test_consultar_levantamiento_comercial_distinto(cliente, fabrica, auth):
    """Internal commercial may read any visit (existing policy)."""
    datos = fabrica.escenario()
    _crear_silla(cliente, auth, datos)
    otro_comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.get(
        f"/visitas/{datos['visita'].id_visita}/levantamiento",
        headers=auth(otro_comercial),
    )

    assert respuesta.status_code == 200
    assert len(respuesta.json()["sillas"]) == 1


def test_consultar_levantamiento_rol_no_autorizado(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.get(
        f"/visitas/{datos['visita'].id_visita}/levantamiento",
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 403


def test_consultar_levantamiento_sin_autenticacion(cliente, fabrica):
    datos = fabrica.escenario()

    respuesta = cliente.get(f"/visitas/{datos['visita'].id_visita}/levantamiento")

    assert respuesta.status_code == 401


def test_tiene_precotizacion_true_con_activa(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    _insertar_precotizacion(db, datos, "BORRADOR")

    respuesta = cliente.get(
        f"/visitas/{datos['visita'].id_visita}/levantamiento",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["tiene_precotizacion"] is True


def test_tiene_precotizacion_false_con_anulada(cliente, fabrica, auth, db):
    """ANULADA is not an active pre-quotation."""
    datos = fabrica.escenario()
    _insertar_precotizacion(db, datos, "ANULADA")

    respuesta = cliente.get(
        f"/visitas/{datos['visita'].id_visita}/levantamiento",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["tiene_precotizacion"] is False


# --- PUT /sillas/{id}/comercial (Requirement 2) -----------------------------

def test_editar_comercial_persiste(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos, serial_antiguo="OLD-1", observaciones="vieja")

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"cargo": "Gerente", "serial_antiguo": "NEW-9", "observaciones": "revisada"},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["cargo"] == "Gerente"
    assert cuerpo["serial_antiguo"] == "NEW-9"
    assert cuerpo["observaciones"] == "revisada"

    # a fresh consult reflects the changes
    lev = cliente.get(
        f"/visitas/{datos['visita'].id_visita}/levantamiento",
        headers=auth(datos["comercial"]),
    ).json()
    editada = next(s for s in lev["sillas"] if s["id_silla"] == silla["id_silla"])
    assert editada["cargo"] == "Gerente"
    assert editada["serial_antiguo"] == "NEW-9"


def test_editar_comercial_campos_omitidos_se_conservan(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos, serial_antiguo="KEEP", observaciones="keep-obs")

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"observaciones": "solo-obs"},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["observaciones"] == "solo-obs"
    assert cuerpo["serial_antiguo"] == "KEEP"  # omitted → unchanged
    assert cuerpo["cargo"] == datos["empleado"].cargo  # omitted → unchanged


def test_editar_comercial_no_cambia_inmutables(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"observaciones": "x"},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["id_silla"] == silla["id_silla"]
    assert cuerpo["codigo_qr"] == silla["codigo_qr"]
    assert cuerpo["token_publico"] == silla["token_publico"]
    assert cuerpo["id_empresa"] == silla["id_empresa"]
    assert cuerpo["id_visita"] == datos["visita"].id_visita


def test_editar_comercial_silla_inexistente(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.put(
        "/sillas/999999/comercial",
        json={"observaciones": "x"},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 404


def test_editar_comercial_rol_no_autorizado(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"observaciones": "x"},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 403


def test_editar_comercial_serial_duplicado(cliente, fabrica, auth):
    """Duplicate serial within the empresa → 409 (existing convention)."""
    datos = fabrica.escenario()
    _crear_silla(cliente, auth, datos, serial_antiguo="DUP")
    otra = _crear_silla(cliente, auth, datos, serial_antiguo="OTRA")

    respuesta = cliente.put(
        f"/sillas/{otra['id_silla']}/comercial",
        json={"serial_antiguo": "DUP"},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 409


def test_editar_comercial_permitido_en_borrador(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)
    _insertar_precotizacion(db, datos, "BORRADOR")

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"observaciones": "editable en borrador"},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text


def test_editar_comercial_rechazado_en_enviada(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)
    _insertar_precotizacion(db, datos, "ENVIADA")

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"observaciones": "no permitido"},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 409


def test_editar_comercial_rechazado_en_aceptada(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)
    _insertar_precotizacion(db, datos, "ACEPTADA")

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"observaciones": "no permitido"},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 409


def test_editar_comercial_no_afecta_put_tecnico(cliente, fabrica, auth):
    """The technician's own PUT keeps working and remains technician-only."""
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)

    # commercial cannot use the technician endpoint
    como_comercial = cliente.put(
        f"/sillas/{silla['id_silla']}",
        json={"observaciones": "x"},
        headers=auth(datos["comercial"]),
    )
    assert como_comercial.status_code == 403

    # technician still can
    como_tecnico = cliente.put(
        f"/sillas/{silla['id_silla']}",
        json={"observaciones": "tec"},
        headers=auth(datos["tecnico"]),
    )
    assert como_tecnico.status_code == 200


def test_editar_comercial_cargo_nulo_rechazado(cliente, fabrica, auth):
    """`cargo` is NOT NULL in the schema: null/empty is rejected (400)."""
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)

    nulo = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"cargo": None},
        headers=auth(datos["comercial"]),
    )
    vacio = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"cargo": "   "},
        headers=auth(datos["comercial"]),
    )

    assert nulo.status_code == 400
    assert vacio.status_code == 400


def test_editar_comercial_limpia_opcionales(cliente, fabrica, auth):
    """`serial_antiguo`/`observaciones` are nullable and can be cleared with null."""
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos, serial_antiguo="OLD-X", observaciones="algo")

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"serial_antiguo": None, "observaciones": None},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["serial_antiguo"] is None
    assert cuerpo["observaciones"] is None


def test_editar_comercial_ignora_inmutables_en_payload(cliente, fabrica, auth):
    """Unknown/immutable fields in the payload are ignored (model only accepts three)."""
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={
            "observaciones": "ok",
            "id_silla": 999999,
            "codigo_qr": "SIC-99999999",
            "token_publico": "00000000-0000-0000-0000-000000000000",
            "id_empresa": 999999,
        },
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id_silla"] == silla["id_silla"]
    assert cuerpo["codigo_qr"] == silla["codigo_qr"]
    assert cuerpo["token_publico"] == silla["token_publico"]
    assert cuerpo["id_empresa"] == silla["id_empresa"]
    assert cuerpo["observaciones"] == "ok"


# --- POST /precotizaciones (Requirements 3, 4) ------------------------------

def _crear_precotizacion(cliente, auth, usuario, id_visita, confirmar=True, observaciones=None):
    cuerpo = {"id_visita": id_visita, "confirmar_validacion": confirmar}
    if observaciones is not None:
        cuerpo["observaciones"] = observaciones
    return cliente.post("/precotizaciones", json=cuerpo, headers=auth(usuario))


def test_crear_precotizacion_ok(cliente, fabrica, auth):
    import uuid as _uuid

    datos = fabrica.escenario()

    respuesta = _crear_precotizacion(
        cliente, auth, datos["comercial"], datos["visita"].id_visita,
        observaciones="Revisado",
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "BORRADOR"
    assert cuerpo["id_empresa"] == datos["empresa"].id_empresa
    assert cuerpo["id_visita"] == datos["visita"].id_visita
    assert cuerpo["observaciones"] == "Revisado"
    # token generated by PostgreSQL (valid UUID), not by Python
    assert _uuid.UUID(cuerpo["token"])
    assert cuerpo["fecha_creacion"]


def test_crear_precotizacion_creada_por(cliente, fabrica, auth, db):
    datos = fabrica.escenario()

    respuesta = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita)

    assert respuesta.status_code == 201, respuesta.text
    db.expire_all()
    fila = db.get(Precotizacion, respuesta.json()["id_precotizacion"])
    assert fila.creada_por == datos["comercial"].id_usuario


def test_crear_precotizacion_sin_confirmacion(cliente, fabrica, auth, db):
    datos = fabrica.escenario()

    respuesta = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita, confirmar=False)

    assert respuesta.status_code == 422
    assert db.scalar(select(func.count()).select_from(Precotizacion)) == 0


def test_crear_precotizacion_confirmacion_ausente(cliente, fabrica, auth, db):
    datos = fabrica.escenario()

    respuesta = cliente.post(
        "/precotizaciones",
        json={"id_visita": datos["visita"].id_visita},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 422
    assert db.scalar(select(func.count()).select_from(Precotizacion)) == 0


def test_crear_precotizacion_confirmacion_tipo_invalido(cliente, fabrica, auth, db):
    datos = fabrica.escenario()

    respuesta = cliente.post(
        "/precotizaciones",
        json={"id_visita": datos["visita"].id_visita, "confirmar_validacion": "si"},
        headers=auth(datos["comercial"]),
    )

    # Pydantic coerces some values; a non-bool-ish string yields 422 validation error.
    assert respuesta.status_code == 422
    assert db.scalar(select(func.count()).select_from(Precotizacion)) == 0


def test_crear_precotizacion_visita_inexistente(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = _crear_precotizacion(cliente, auth, datos["comercial"], 999999)

    assert respuesta.status_code == 404


def test_crear_precotizacion_sin_autenticacion(cliente, fabrica):
    datos = fabrica.escenario()

    respuesta = cliente.post(
        "/precotizaciones",
        json={"id_visita": datos["visita"].id_visita, "confirmar_validacion": True},
    )

    assert respuesta.status_code == 401


def test_crear_precotizacion_rol_no_autorizado(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = _crear_precotizacion(cliente, auth, datos["tecnico"], datos["visita"].id_visita)

    assert respuesta.status_code == 403


def test_crear_precotizacion_comercial_distinto(cliente, fabrica, auth):
    """Internal commercial other than the assigned one may create (existing policy)."""
    datos = fabrica.escenario()
    otro_comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = _crear_precotizacion(cliente, auth, otro_comercial, datos["visita"].id_visita)

    assert respuesta.status_code == 201, respuesta.text


def test_crear_precotizacion_segunda_activa_rechazada(cliente, fabrica, auth):
    datos = fabrica.escenario()
    primera = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita)
    assert primera.status_code == 201

    segunda = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita)

    assert segunda.status_code == 409


def test_crear_precotizacion_bloqueada_por_enviada(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    _insertar_precotizacion(db, datos, "ENVIADA")

    respuesta = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita)

    assert respuesta.status_code == 409


def test_crear_precotizacion_bloqueada_por_aceptada(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    _insertar_precotizacion(db, datos, "ACEPTADA")

    respuesta = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita)

    assert respuesta.status_code == 409


def test_crear_precotizacion_permitida_tras_anulada(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    _insertar_precotizacion(db, datos, "ANULADA")

    respuesta = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita)

    assert respuesta.status_code == 201, respuesta.text


def test_crear_precotizacion_tras_editar_levantamiento(cliente, fabrica, auth):
    """Edit the survey, then create: the survey consult reflects the edit."""
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)
    cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"observaciones": "corregido"},
        headers=auth(datos["comercial"]),
    )

    creada = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita)
    assert creada.status_code == 201, creada.text

    lev = cliente.get(
        f"/visitas/{datos['visita'].id_visita}/levantamiento",
        headers=auth(datos["comercial"]),
    ).json()
    assert lev["tiene_precotizacion"] is True
    editada = next(s for s in lev["sillas"] if s["id_silla"] == silla["id_silla"])
    assert editada["observaciones"] == "corregido"


# --- GET /precotizaciones?id_visita= (Requirement 8) ------------------------

def test_listar_precotizaciones_por_visita(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    _insertar_precotizacion(db, datos, "ANULADA")
    activa = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita)
    assert activa.status_code == 201

    respuesta = cliente.get(
        "/precotizaciones",
        params={"id_visita": datos["visita"].id_visita},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert len(cuerpo) == 2
    ids = [p["id_precotizacion"] for p in cuerpo]
    assert ids == sorted(ids)  # deterministic order


def test_listar_precotizaciones_aislamiento_por_visita(cliente, fabrica, auth):
    datos = fabrica.escenario()
    _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita)

    # A second visit (same empresa) with its own pre-quotation.
    otra_sede = fabrica.sede(datos["empresa"])
    otra_visita = fabrica.visita(datos["empresa"], otra_sede, datos["comercial"], datos["tecnico"])
    _crear_precotizacion(cliente, auth, datos["comercial"], otra_visita.id_visita)

    respuesta = cliente.get(
        "/precotizaciones",
        params={"id_visita": datos["visita"].id_visita},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo) == 1
    assert all(p["id_visita"] == datos["visita"].id_visita for p in cuerpo)


def test_listar_precotizaciones_sin_resultados(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.get(
        "/precotizaciones",
        params={"id_visita": datos["visita"].id_visita},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_listar_precotizaciones_rol_no_autorizado(cliente, fabrica, auth):
    datos = fabrica.escenario()

    respuesta = cliente.get(
        "/precotizaciones",
        params={"id_visita": datos["visita"].id_visita},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 403


def test_crear_precotizacion_confirmacion_no_booleana(cliente, fabrica, auth, db):
    """StrictBool: string/number values for confirmar_validacion → 422, no row."""
    datos = fabrica.escenario()
    for valor in ("true", "yes", 1, "1"):
        respuesta = cliente.post(
            "/precotizaciones",
            json={"id_visita": datos["visita"].id_visita, "confirmar_validacion": valor},
            headers=auth(datos["comercial"]),
        )
        assert respuesta.status_code == 422, (valor, respuesta.text)
    assert db.scalar(select(func.count()).select_from(Precotizacion)) == 0


def test_editar_comercial_cargo_demasiado_largo(cliente, fabrica, auth):
    """cargo over VARCHAR(100) → 422 before persisting."""
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)

    limite = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"cargo": "C" * 100},
        headers=auth(datos["comercial"]),
    )
    excede = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"cargo": "C" * 101},
        headers=auth(datos["comercial"]),
    )

    assert limite.status_code == 200, limite.text   # exactly 100 is allowed
    assert excede.status_code == 422


def test_editar_comercial_serial_demasiado_largo(cliente, fabrica, auth):
    """serial_antiguo over VARCHAR(100) → 422."""
    datos = fabrica.escenario()
    silla = _crear_silla(cliente, auth, datos)

    respuesta = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"serial_antiguo": "S" * 101},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 422


# --- POST /precotizaciones/{id}/enviar (Requirement 6) ----------------------

def _enviar(cliente, auth, usuario, id_pre, correo="cliente@example.com", confirmar=True):
    cuerpo = {"correo_cliente": correo}
    if confirmar is not None:
        cuerpo["confirmar_validacion"] = confirmar
    return cliente.post(f"/precotizaciones/{id_pre}/enviar", json=cuerpo, headers=auth(usuario))


def _mock_email_ok(monkeypatch):
    import app.routers.precotizaciones as mod
    enviados = []
    monkeypatch.setattr(
        mod.email_service, "enviar_correo",
        lambda dest, asunto, cuerpo: enviados.append((dest, asunto, cuerpo)),
    )
    return enviados


def test_enviar_primer_envio_ok(cliente, fabrica, auth, db, monkeypatch):
    enviados = _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    respuesta = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"])

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ENVIADA"
    assert cuerpo["correo_cliente"] == "cliente@example.com"
    assert cuerpo["fecha_envio"]
    assert cuerpo["token"] == pre["token"]            # token unchanged
    # the link in the sent email uses the token
    assert len(enviados) == 1
    assert pre["token"] in enviados[0][2]


def test_enviar_sin_confirmacion(cliente, fabrica, auth, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    respuesta = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"], confirmar=None)

    assert respuesta.status_code == 422


def test_enviar_confirmacion_false(cliente, fabrica, auth, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    respuesta = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"], confirmar=False)

    assert respuesta.status_code == 422


def test_enviar_confirmacion_no_booleana(cliente, fabrica, auth, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    respuesta = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"], confirmar="true")

    assert respuesta.status_code == 422


def test_enviar_correo_invalido(cliente, fabrica, auth, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    respuesta = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"], correo="no-valido")

    assert respuesta.status_code == 422


def test_enviar_smtp_no_configurado(cliente, fabrica, auth, monkeypatch):
    import app.routers.precotizaciones as mod

    def _falla(dest, asunto, cuerpo):
        raise mod.email_service.EmailNoConfigurado("no config")

    monkeypatch.setattr(mod.email_service, "enviar_correo", _falla)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    respuesta = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"])

    assert respuesta.status_code == 503


def test_enviar_fallo_smtp_no_transiciona(cliente, fabrica, auth, db, monkeypatch):
    import app.routers.precotizaciones as mod

    def _falla(dest, asunto, cuerpo):
        raise mod.email_service.EmailEnvioError("boom")

    monkeypatch.setattr(mod.email_service, "enviar_correo", _falla)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    respuesta = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"])

    assert respuesta.status_code == 502
    db.expire_all()
    fila = db.get(Precotizacion, pre["id_precotizacion"])
    assert fila.estado == "BORRADOR"       # no transition
    assert fila.fecha_envio is None


def test_enviar_fallo_persistencia_tras_envio(cliente, fabrica, auth, db, monkeypatch):
    """Email sent, but the DB commit fails → 500; the email is not reverted."""
    import app.routers.precotizaciones as mod
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    def _db_commit_falla():
        original = db.commit

        def _falla():
            raise RuntimeError("commit boom")

        db.commit = _falla
        try:
            yield db
        finally:
            db.commit = original

    from app.db import get_db
    from app.main import app
    previos = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _db_commit_falla
    try:
        respuesta = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"])
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previos)

    assert respuesta.status_code == 500


def test_enviar_inexistente(cliente, fabrica, auth, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()

    respuesta = _enviar(cliente, auth, datos["comercial"], 999999)

    assert respuesta.status_code == 404


def test_enviar_sin_autenticacion(cliente, fabrica, auth, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    respuesta = cliente.post(
        f"/precotizaciones/{pre['id_precotizacion']}/enviar",
        json={"correo_cliente": "cliente@example.com", "confirmar_validacion": True},
    )

    assert respuesta.status_code == 401


def test_enviar_rol_no_autorizado(cliente, fabrica, auth, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()

    respuesta = _enviar(cliente, auth, datos["tecnico"], pre["id_precotizacion"])

    assert respuesta.status_code == 403


def test_reenvio_mismo_token_y_destinatario(cliente, fabrica, auth, monkeypatch):
    enviados = _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()
    primero = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"]).json()

    # resend without confirmation, same recipient
    reenvio = cliente.post(
        f"/precotizaciones/{pre['id_precotizacion']}/enviar",
        json={"correo_cliente": "cliente@example.com"},
        headers=auth(datos["comercial"]),
    )

    assert reenvio.status_code == 200, reenvio.text
    assert reenvio.json()["token"] == primero["token"]   # same token
    assert reenvio.json()["correo_cliente"] == "cliente@example.com"
    assert len(enviados) == 2


def test_reenvio_rechaza_cambio_destinatario(cliente, fabrica, auth, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()
    _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"])

    reenvio = cliente.post(
        f"/precotizaciones/{pre['id_precotizacion']}/enviar",
        json={"correo_cliente": "otro@example.com"},
        headers=auth(datos["comercial"]),
    )

    assert reenvio.status_code == 409


def test_enviar_aceptada_rechazada(cliente, fabrica, auth, db, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _insertar_precotizacion(db, datos, "ACEPTADA")

    respuesta = _enviar(cliente, auth, datos["comercial"], pre.id_precotizacion)

    assert respuesta.status_code == 409


def test_enviar_anulada_rechazada(cliente, fabrica, auth, db, monkeypatch):
    _mock_email_ok(monkeypatch)
    datos = fabrica.escenario()
    pre = _insertar_precotizacion(db, datos, "ANULADA")

    respuesta = _enviar(cliente, auth, datos["comercial"], pre.id_precotizacion)

    assert respuesta.status_code == 409


# --- GET /propuesta/{token} (Requirement 7) ---------------------------------

def _enviar_y_token(cliente, auth, datos, monkeypatch):
    _mock_email_ok(monkeypatch)
    _crear_silla(cliente, auth, datos)
    pre = _crear_precotizacion(cliente, auth, datos["comercial"], datos["visita"].id_visita).json()
    enviada = _enviar(cliente, auth, datos["comercial"], pre["id_precotizacion"]).json()
    return enviada["token"]


def test_propuesta_publica_enviada(cliente, fabrica, auth, monkeypatch):
    datos = fabrica.escenario()
    token = _enviar_y_token(cliente, auth, datos, monkeypatch)

    respuesta = cliente.get(f"/propuesta/{token}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ENVIADA"
    assert cuerpo["empresa_nombre"]
    assert len(cuerpo["sillas"]) == 1
    assert respuesta.headers.get("cache-control") == "no-store"


def test_propuesta_publica_sin_campos_privados(cliente, fabrica, auth, monkeypatch):
    datos = fabrica.escenario()
    token = _enviar_y_token(cliente, auth, datos, monkeypatch)

    cuerpo = cliente.get(f"/propuesta/{token}").json()

    # no internal/private fields leak
    assert set(cuerpo.keys()) == {"token", "estado", "fecha_envio", "empresa_nombre", "sillas"}
    silla = cuerpo["sillas"][0]
    assert set(silla.keys()) == {"codigo_qr", "cargo", "estado"}
    assert "token_publico" not in silla
    assert "correo_cliente" not in cuerpo


def test_propuesta_publica_aceptada(cliente, fabrica, auth, db):
    """An ACEPTADA proposal is publicly consultable (SQL-compatible data)."""
    datos = fabrica.escenario()
    _crear_silla(cliente, auth, datos)
    pre = _insertar_precotizacion(db, datos, "ACEPTADA")

    respuesta = cliente.get(f"/propuesta/{pre.token}")

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ACEPTADA"
    assert cuerpo["empresa_nombre"]
    assert len(cuerpo["sillas"]) == 1
    assert respuesta.headers.get("cache-control") == "no-store"


def test_propuesta_publica_error_tiene_no_store(cliente):
    """Public error (404) responses also carry Cache-Control: no-store."""
    import uuid as _uuid
    respuesta = cliente.get(f"/propuesta/{_uuid.uuid4()}")
    assert respuesta.status_code == 404
    assert respuesta.headers.get("cache-control") == "no-store"


def test_propuesta_publica_borrador_404(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    pre = _insertar_precotizacion(db, datos, "BORRADOR")

    respuesta = cliente.get(f"/propuesta/{pre.token}")

    assert respuesta.status_code == 404


def test_propuesta_publica_anulada_404(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    pre = _insertar_precotizacion(db, datos, "ANULADA")

    respuesta = cliente.get(f"/propuesta/{pre.token}")

    assert respuesta.status_code == 404


def test_propuesta_publica_token_malformado_404(cliente):
    assert cliente.get("/propuesta/no-es-uuid").status_code == 404


def test_propuesta_publica_token_desconocido_404(cliente):
    import uuid as _uuid
    assert cliente.get(f"/propuesta/{_uuid.uuid4()}").status_code == 404


def test_propuesta_publica_aislamiento_empresa(cliente, fabrica, auth, monkeypatch):
    """The proposal only shows chairs of its own visit/empresa."""
    datos = fabrica.escenario()
    token = _enviar_y_token(cliente, auth, datos, monkeypatch)

    # Another empresa with its own chair that must not appear.
    otra_empresa = fabrica.empresa()
    otra_sede = fabrica.sede(otra_empresa)
    otro_dep = fabrica.departamento(otra_empresa, otra_sede)
    otro_emp = fabrica.empleado(otra_empresa, otra_sede, otro_dep)
    otra_visita = fabrica.visita(otra_empresa, otra_sede, datos["comercial"], datos["tecnico"])
    cliente.post(
        f"/visitas/{otra_visita.id_visita}/sillas",
        json={"id_empleado": otro_emp.id_empleado, "cargo": otro_emp.cargo},
        headers=auth(datos["tecnico"]),
    )

    cuerpo = cliente.get(f"/propuesta/{token}").json()
    assert len(cuerpo["sillas"]) == 1   # only the own visit's chair


def test_propuesta_publica_registra_acceso(cliente, fabrica, auth, db, monkeypatch):
    from app.models import AccesoPrecotizacion

    datos = fabrica.escenario()
    token = _enviar_y_token(cliente, auth, datos, monkeypatch)

    assert cliente.get(f"/propuesta/{token}").status_code == 200

    db.expire_all()
    pre = db.scalar(select(Precotizacion).where(Precotizacion.token == token))
    accesos = db.scalars(
        select(AccesoPrecotizacion).where(
            AccesoPrecotizacion.id_precotizacion == pre.id_precotizacion
        )
    ).all()
    assert len(accesos) >= 1


def test_propuesta_publica_fallo_registro_acceso(cliente, fabrica, auth, monkeypatch):
    """If access logging fails, the consult still succeeds (no false 'logged')."""
    import app.routers.precotizaciones as mod
    datos = fabrica.escenario()
    token = _enviar_y_token(cliente, auth, datos, monkeypatch)

    def _falla(db, id_pre, ua):
        raise RuntimeError("log boom")

    monkeypatch.setattr(mod, "registrar_acceso", _falla)
    respuesta = cliente.get(f"/propuesta/{token}")

    assert respuesta.status_code == 200
