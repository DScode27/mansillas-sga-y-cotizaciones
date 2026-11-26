"""HU-15 Block 2 tests: OTP request (`POST /propuesta/{token}/otp`).

Integration cases use the shared `conftest.py` fixtures against the isolated,
disposable PostgreSQL (`TEST_DATABASE_URL`); never the shared Supabase DB. SMTP
is mocked (no real mail). `ControlAbuso` state is reset between tests to avoid
order dependence. These tests are WRITTEN here but NOT executed until an
isolated PostgreSQL is available.
"""

import uuid

import pytest
from sqlalchemy import DateTime, cast, func, select


def _ahora_db(db):
    """Real server clock read as TIMESTAMP WITHOUT TIME ZONE (naive).

    Uses `clock_timestamp()` (the actual wall clock, which advances within a
    transaction) rather than `now()` (= transaction start, frozen for the whole
    test session). Cast to `DateTime` yields the same naive type as the schema's
    `fecha_expiracion`/`fecha_aceptacion` columns, so comparisons represent the
    same instant without inventing or stripping time zones. A fresh read is
    issued each call so it reflects writes already committed by the endpoint.
    """
    return db.scalar(select(cast(func.clock_timestamp(), DateTime)))

from app.config import settings
from app.models import CodigoVerificacion, Precotizacion
from app.services import otp as otp_service


@pytest.fixture(autouse=True)
def _otp_entorno(monkeypatch):
    """Secure OTP secret + a fresh in-memory abuse control per test."""
    monkeypatch.setattr(settings, "otp_secret", "s" * 48)
    monkeypatch.setattr(settings, "jwt_secret", "jwt-distinto-largo-xxxxxxxxxxxxxxxxxxxx")
    # Replace the process-wide singleton with a fresh instance for isolation.
    monkeypatch.setattr(otp_service, "control_abuso", otp_service.ControlAbuso())
    import app.routers.precotizaciones as pr
    monkeypatch.setattr(pr.otp_service, "control_abuso", otp_service.control_abuso, raising=False)


@pytest.fixture
def smtp_ok(monkeypatch):
    """Mock the email send to succeed and capture calls."""
    import app.routers.precotizaciones as pr
    enviados = []
    monkeypatch.setattr(
        pr.email_service, "enviar_correo",
        lambda dest, asunto, cuerpo, *, exigir_tls=False: enviados.append(
            {"dest": dest, "asunto": asunto, "cuerpo": cuerpo, "tls": exigir_tls}
        ),
    )
    return enviados


def _precotizacion(db, datos, estado="ENVIADA", correo="cliente@example.com"):
    pre = Precotizacion(
        id_empresa=datos["empresa"].id_empresa,
        id_visita=datos["visita"].id_visita,
        estado=estado,
        creada_por=datos["comercial"].id_usuario,
        correo_cliente=correo,
    )
    db.add(pre)
    db.commit()
    db.refresh(pre)
    return pre


def _solicitar(cliente, token):
    return cliente.post(f"/propuesta/{token}/otp")


# --- Success ----------------------------------------------------------------

def test_solicitar_otp_ok(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    r = _solicitar(cliente, pre.token)

    assert r.status_code == 202, r.text
    assert r.json() == {"mensaje": "Se ha solicitado el código de verificación."}
    assert r.headers.get("cache-control") == "no-store"
    assert len(smtp_ok) == 1
    assert smtp_ok[0]["dest"] == "cliente@example.com"   # stored recipient only
    assert smtp_ok[0]["tls"] is True                     # TLS required


def test_solicitar_otp_persiste_hash_no_codigo(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    _solicitar(cliente, pre.token)

    db.expire_all()
    cod = db.scalar(
        select(CodigoVerificacion).where(
            CodigoVerificacion.id_precotizacion == pre.id_precotizacion
        )
    )
    assert cod is not None
    assert cod.id_empleado is None
    assert cod.utilizado is False
    assert cod.correo_destino == "cliente@example.com"
    assert cod.codigo_hash.startswith("v1$")
    # the plain code emailed is not stored
    enviado = smtp_ok[0]["cuerpo"]
    import re
    m = re.search(r"\b(\d{6})\b", enviado)
    assert m and m.group(1) not in cod.codigo_hash


def test_solicitar_otp_expiracion_coherente(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    _solicitar(cliente, pre.token)

    db.expire_all()
    cod = db.scalar(
        select(CodigoVerificacion).where(
            CodigoVerificacion.id_precotizacion == pre.id_precotizacion
        )
    )
    # fecha_expiracion ~ now + 10 min on the DB clock (trigger-compatible)
    ahora = _ahora_db(db)
    delta = (cod.fecha_expiracion - ahora).total_seconds()
    assert 9 * 60 <= delta <= 10 * 60 + 5


# --- Token / state ----------------------------------------------------------

def test_solicitar_otp_token_malformado(cliente):
    r = _solicitar(cliente, "no-es-uuid")
    assert r.status_code == 404
    assert r.headers.get("cache-control") == "no-store"


def test_solicitar_otp_token_desconocido(cliente):
    r = _solicitar(cliente, uuid.uuid4())
    assert r.status_code == 404


@pytest.mark.parametrize("estado", ["BORRADOR", "ACEPTADA", "ANULADA"])
def test_solicitar_otp_estado_no_permitido(cliente, fabrica, db, smtp_ok, estado):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos, estado=estado)

    r = _solicitar(cliente, pre.token)

    assert r.status_code == 404
    assert db.scalar(select(func.count()).select_from(CodigoVerificacion)) == 0


# --- Stored email problems --------------------------------------------------

def test_solicitar_otp_sin_correo(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos, correo=None)

    r = _solicitar(cliente, pre.token)

    assert r.status_code == 503
    assert db.scalar(select(func.count()).select_from(CodigoVerificacion)) == 0


# --- Configuration ----------------------------------------------------------

def test_solicitar_otp_sin_otp_secret(cliente, fabrica, db, smtp_ok, monkeypatch):
    monkeypatch.setattr(settings, "otp_secret", "")
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    r = _solicitar(cliente, pre.token)

    assert r.status_code == 503
    assert db.scalar(select(func.count()).select_from(CodigoVerificacion)) == 0


def test_solicitar_otp_sin_smtp(cliente, fabrica, db, monkeypatch):
    import app.routers.precotizaciones as pr

    def _no_config(dest, asunto, cuerpo, *, exigir_tls=False):
        raise pr.email_service.EmailNoConfigurado("sin config")

    monkeypatch.setattr(pr.email_service, "enviar_correo", _no_config)
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    r = _solicitar(cliente, pre.token)

    assert r.status_code == 503
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(CodigoVerificacion)) == 0   # rolled back


# --- Request limits ---------------------------------------------------------

def test_solicitar_otp_intervalo(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    primera = _solicitar(cliente, pre.token)
    segunda = _solicitar(cliente, pre.token)   # immediately, within 60 s

    assert primera.status_code == 202
    assert segunda.status_code == 429
    assert segunda.headers.get("cache-control") == "no-store"


def test_solicitar_otp_limite_acumulado(cliente, fabrica, db, smtp_ok, monkeypatch):
    # Bypass the 60 s interval by advancing the injected clock each call.
    reloj = {"t": 1000.0}
    control = otp_service.ControlAbuso(reloj=lambda: reloj["t"])
    import app.routers.precotizaciones as pr
    monkeypatch.setattr(pr.otp_service, "control_abuso", control, raising=False)
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    for _ in range(otp_service.OTP_MAX_REQUESTS_WINDOW):
        assert _solicitar(cliente, pre.token).status_code == 202
        reloj["t"] += 61
    r = _solicitar(cliente, pre.token)
    assert r.status_code == 429


# --- Invalidation / isolation ----------------------------------------------

def test_solicitar_otp_invalida_anteriores(cliente, fabrica, db, smtp_ok, monkeypatch):
    reloj = {"t": 1000.0}
    control = otp_service.ControlAbuso(reloj=lambda: reloj["t"])
    import app.routers.precotizaciones as pr
    monkeypatch.setattr(pr.otp_service, "control_abuso", control, raising=False)
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    assert _solicitar(cliente, pre.token).status_code == 202
    reloj["t"] += 61
    assert _solicitar(cliente, pre.token).status_code == 202

    db.expire_all()
    codigos = db.scalars(
        select(CodigoVerificacion)
        .where(CodigoVerificacion.id_precotizacion == pre.id_precotizacion)
        .order_by(CodigoVerificacion.id_codigo)
    ).all()
    ahora = _ahora_db(db)
    vigentes = [c for c in codigos if c.fecha_expiracion >= ahora and not c.utilizado]
    assert len(codigos) == 2
    assert len(vigentes) == 1   # only the newest remains valid
    # the single valid code must be the most recent issuance (highest id_codigo)
    assert vigentes[0].id_codigo == max(c.id_codigo for c in codigos)
    # invalidation is not consumption
    assert all(not c.utilizado for c in codigos)


def test_solicitar_otp_no_afecta_otra_precotizacion(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    # a code of a DIFFERENT pre-quotation that must stay valid
    otra_sede = fabrica.sede(datos["empresa"])
    otra_visita = fabrica.visita(datos["empresa"], otra_sede, datos["comercial"], datos["tecnico"])
    otra_pre = _precotizacion(db, {**datos, "visita": otra_visita})
    ajeno = CodigoVerificacion(
        id_precotizacion=otra_pre.id_precotizacion, id_empleado=None,
        correo_destino="x@e.com", codigo_hash="v1$" + "a" * 32 + "$" + "b" * 64,
        fecha_expiracion=db.scalar(select(cast(func.now() + func.make_interval(0, 0, 0, 0, 0, 10), DateTime))),
        utilizado=False,
    )
    db.add(ajeno); db.commit(); db.refresh(ajeno)

    _solicitar(cliente, pre.token)

    db.expire_all()
    recargado = db.get(CodigoVerificacion, ajeno.id_codigo)
    ahora = _ahora_db(db)
    assert recargado.fecha_expiracion >= ahora   # untouched


def test_solicitar_otp_no_afecta_codigo_empleado(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    empleado_cod = CodigoVerificacion(
        id_precotizacion=None, id_empleado=datos["empleado"].id_empleado,
        correo_destino="emp@e.com", codigo_hash="v1$" + "c" * 32 + "$" + "d" * 64,
        fecha_expiracion=db.scalar(select(cast(func.now() + func.make_interval(0, 0, 0, 0, 0, 10), DateTime))),
        utilizado=False,
    )
    db.add(empleado_cod); db.commit(); db.refresh(empleado_cod)

    _solicitar(cliente, pre.token)

    db.expire_all()
    recargado = db.get(CodigoVerificacion, empleado_cod.id_codigo)
    ahora = _ahora_db(db)
    assert recargado.fecha_expiracion >= ahora   # employee code untouched


# --- SMTP failure / rollback ------------------------------------------------

def test_solicitar_otp_fallo_smtp_rollback(cliente, fabrica, db, monkeypatch):
    import app.routers.precotizaciones as pr

    def _falla(dest, asunto, cuerpo, *, exigir_tls=False):
        raise pr.email_service.EmailEnvioError("boom")

    monkeypatch.setattr(pr.email_service, "enviar_correo", _falla)
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    r = _solicitar(cliente, pre.token)

    assert r.status_code == 502
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(CodigoVerificacion)) == 0   # nothing persisted


def test_solicitar_otp_fallo_smtp_conserva_codigo_anterior(cliente, fabrica, db, monkeypatch):
    """A failed new send must not leave the previous valid code expired."""
    reloj = {"t": 1000.0}
    control = otp_service.ControlAbuso(reloj=lambda: reloj["t"])
    import app.routers.precotizaciones as pr
    monkeypatch.setattr(pr.otp_service, "control_abuso", control, raising=False)

    enviados = []
    monkeypatch.setattr(
        pr.email_service, "enviar_correo",
        lambda d, a, c, *, exigir_tls=False: enviados.append(d),
    )
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    assert _solicitar(cliente, pre.token).status_code == 202   # first code valid

    # second request: SMTP fails
    reloj["t"] += 61
    monkeypatch.setattr(
        pr.email_service, "enviar_correo",
        lambda d, a, c, *, exigir_tls=False: (_ for _ in ()).throw(pr.email_service.EmailEnvioError("x")),
    )
    assert _solicitar(cliente, pre.token).status_code == 502

    db.expire_all()
    ahora = _ahora_db(db)
    vigentes = db.scalars(
        select(CodigoVerificacion).where(
            CodigoVerificacion.id_precotizacion == pre.id_precotizacion,
            CodigoVerificacion.fecha_expiracion >= ahora,
            CodigoVerificacion.utilizado.is_(False),
        )
    ).all()
    assert len(vigentes) == 1   # the first code is still valid (rollback restored it)


def test_solicitar_otp_fallo_commit(cliente, fabrica, db, smtp_ok, monkeypatch):
    """SMTP ok but commit fails → 500 (incident logged, email not reverted)."""
    from app.db import get_db
    from app.main import app

    def _db_commit_falla():
        original = db.commit

        def _falla():
            raise RuntimeError("commit boom")

        db.commit = _falla
        try:
            yield db
        finally:
            db.commit = original

    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    previos = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _db_commit_falla
    try:
        r = _solicitar(cliente, pre.token)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previos)

    assert r.status_code == 500
    assert r.headers.get("cache-control") == "no-store"


# --- No secret leakage ------------------------------------------------------

def test_solicitar_otp_respuesta_sin_secretos(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    r = _solicitar(cliente, pre.token)
    cuerpo = r.json()

    assert set(cuerpo.keys()) == {"mensaje"}
    texto = r.text.lower()
    assert "v1$" not in r.text
    assert "correo" not in texto or "cliente@example.com" not in r.text
    assert str(pre.token) not in r.text


# ===========================================================================
# Block 3 — POST /propuesta/{token}/aceptar
# ===========================================================================

import re as _re


def _codigo_de(enviados):
    """Extract the 6-digit OTP from the last mocked email body."""
    m = _re.search(r"\b(\d{6})\b", enviados[-1]["cuerpo"])
    assert m, "no OTP in the email body"
    return m.group(1)


def _solicitar_y_codigo(cliente, pre, smtp_ok):
    r = _solicitar(cliente, pre.token)
    assert r.status_code == 202, r.text
    return _codigo_de(smtp_ok)


def _aceptar(cliente, token, nombre="Juan Perez", cargo="Gerente", codigo="000000"):
    return cliente.post(
        f"/propuesta/{token}/aceptar",
        json={"nombre_aceptante": nombre, "cargo_aceptante": cargo, "codigo": codigo},
    )


def test_aceptar_ok(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)

    r = _aceptar(cliente, pre.token, codigo=codigo)

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "ACEPTADA"
    assert cuerpo["fecha_aceptacion"]
    assert set(cuerpo.keys()) == {"estado", "fecha_aceptacion"}
    assert r.headers.get("cache-control") == "no-store"


def test_aceptar_ceros_iniciales(cliente, fabrica, db, smtp_ok, monkeypatch):
    # Force an OTP with leading zeros.
    monkeypatch.setattr(otp_service.secrets, "randbelow", lambda n: 42)
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)
    assert codigo == "000042"

    r = _aceptar(cliente, pre.token, codigo=codigo)
    assert r.status_code == 200, r.text


def test_aceptar_persiste_y_trigger(cliente, fabrica, db, smtp_ok):
    from app.models import AceptacionPrecotizacion
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)

    _aceptar(cliente, pre.token, nombre="  Ana  ", cargo="  Jefa  ", codigo=codigo)

    db.expire_all()
    rec = db.scalar(
        select(AceptacionPrecotizacion).where(
            AceptacionPrecotizacion.id_precotizacion == pre.id_precotizacion
        )
    )
    assert rec is not None
    assert rec.nombre_aceptante == "Ana"          # normalized
    assert rec.cargo_aceptante == "Jefa"
    assert rec.correo_aceptante == "cliente@example.com"   # from the proposal only
    assert rec.fecha_aceptacion is not None
    cod = db.get(CodigoVerificacion, rec.id_codigo)
    assert cod.utilizado is True                  # consumed
    recargada = db.get(Precotizacion, pre.id_precotizacion)
    assert recargada.estado == "ACEPTADA"         # trigger transition


def test_aceptar_codigo_incorrecto(cliente, fabrica, db, smtp_ok, monkeypatch):
    # Deterministic real code so the "wrong" code cannot coincide by chance.
    monkeypatch.setattr(otp_service, "generar_otp", lambda: "111111")
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    real = _solicitar_y_codigo(cliente, pre, smtp_ok)
    assert real == "111111"
    incorrecto = "222222"

    r = _aceptar(cliente, pre.token, codigo=incorrecto)

    assert r.status_code == 400
    db.expire_all()
    assert db.get(Precotizacion, pre.id_precotizacion).estado == "ENVIADA"
    cod = db.scalar(select(CodigoVerificacion).where(
        CodigoVerificacion.id_precotizacion == pre.id_precotizacion))
    assert cod.utilizado is False                 # not consumed


def test_aceptar_codigo_expirado(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)
    # expire the stored code in the past
    db.query(CodigoVerificacion).filter(
        CodigoVerificacion.id_precotizacion == pre.id_precotizacion
    ).update({CodigoVerificacion.fecha_expiracion: func.now() - func.make_interval(0, 0, 0, 0, 0, 1)},
             synchronize_session=False)
    db.commit()

    r = _aceptar(cliente, pre.token, codigo=codigo)
    assert r.status_code == 400


def test_aceptar_codigo_utilizado(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)
    assert _aceptar(cliente, pre.token, codigo=codigo).status_code == 200
    # a second attempt: the proposal is ACEPTADA now
    r = _aceptar(cliente, pre.token, codigo=codigo)
    assert r.status_code == 409


def test_aceptar_codigo_invalidado_por_nueva_emision(cliente, fabrica, db, smtp_ok, monkeypatch):
    reloj = {"t": 1000.0}
    import app.routers.precotizaciones as pr
    monkeypatch.setattr(pr.otp_service, "control_abuso",
                        otp_service.ControlAbuso(reloj=lambda: reloj["t"]), raising=False)
    # Guarantee two DIFFERENT issued codes via monkeypatch.
    emitidos = iter(["111111", "222222"])
    monkeypatch.setattr(otp_service, "generar_otp", lambda: next(emitidos))
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    viejo = _solicitar_y_codigo(cliente, pre, smtp_ok)
    reloj["t"] += 61
    nuevo = _solicitar_y_codigo(cliente, pre, smtp_ok)   # invalidates the old one
    assert viejo == "111111" and nuevo == "222222"

    r = _aceptar(cliente, pre.token, codigo=viejo)
    assert r.status_code == 400


def test_aceptar_codigo_de_otra_precotizacion(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    otra_sede = fabrica.sede(datos["empresa"])
    otra_visita = fabrica.visita(datos["empresa"], otra_sede, datos["comercial"], datos["tecnico"])
    otra = _precotizacion(db, {**datos, "visita": otra_visita})
    codigo_otra = _solicitar_y_codigo(cliente, otra, smtp_ok)

    # use otra's code on pre → no valid code for pre → 400
    r = _aceptar(cliente, pre.token, codigo=codigo_otra)
    assert r.status_code == 400


def test_aceptar_token_malformado(cliente):
    r = _aceptar(cliente, "no-es-uuid", codigo="123456")
    assert r.status_code == 404


def test_aceptar_token_desconocido(cliente):
    r = _aceptar(cliente, uuid.uuid4(), codigo="123456")
    assert r.status_code == 404


@pytest.mark.parametrize("estado", ["BORRADOR", "ANULADA"])
def test_aceptar_estado_no_apto(cliente, fabrica, db, estado):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos, estado=estado)
    r = _aceptar(cliente, pre.token, codigo="123456")
    assert r.status_code == 409


def test_aceptar_duplicada(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)
    assert _aceptar(cliente, pre.token, codigo=codigo).status_code == 200
    r = _aceptar(cliente, pre.token, codigo=codigo)
    assert r.status_code == 409


def test_aceptar_limite_por_emision(cliente, fabrica, db, smtp_ok, monkeypatch):
    monkeypatch.setattr(otp_service, "generar_otp", lambda: "111111")
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    _solicitar_y_codigo(cliente, pre, smtp_ok)
    incorrecto = "222222"
    for _ in range(otp_service.OTP_MAX_ATTEMPTS):
        assert _aceptar(cliente, pre.token, codigo=incorrecto).status_code == 400
    r = _aceptar(cliente, pre.token, codigo=incorrecto)
    assert r.status_code == 429


def test_aceptar_sin_otp_secret(cliente, fabrica, db, smtp_ok, monkeypatch):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    _solicitar_y_codigo(cliente, pre, smtp_ok)
    monkeypatch.setattr(settings, "otp_secret", "")
    r = _aceptar(cliente, pre.token, codigo="123456")
    assert r.status_code == 503


def test_aceptar_hash_malformado(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    _solicitar_y_codigo(cliente, pre, smtp_ok)
    db.query(CodigoVerificacion).filter(
        CodigoVerificacion.id_precotizacion == pre.id_precotizacion
    ).update({CodigoVerificacion.codigo_hash: "hash-malformado"}, synchronize_session=False)
    db.commit()

    r = _aceptar(cliente, pre.token, codigo="123456")
    assert r.status_code == 500          # internal inconsistency, not a client failure


def test_aceptar_rollback_si_falla_insercion(cliente, fabrica, db, smtp_ok, monkeypatch):
    """A failure inserting the acceptance must leave the code unconsumed."""
    import app.routers.precotizaciones as pr
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)

    original_flush = db.flush
    estado = {"n": 0}

    def _flush_falla(*a, **k):
        estado["n"] += 1
        if estado["n"] >= 2:   # second flush is the acceptance insert
            raise RuntimeError("insert boom")
        return original_flush(*a, **k)

    # Override the session via dependency so the endpoint uses our patched flush.
    def _db_override():
        db.flush = _flush_falla
        try:
            yield db
        finally:
            db.flush = original_flush

    from app.db import get_db
    from app.main import app
    previos = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _db_override
    try:
        r = _aceptar(cliente, pre.token, codigo=codigo)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previos)

    assert r.status_code == 500
    db.expire_all()
    cod = db.scalar(select(CodigoVerificacion).where(
        CodigoVerificacion.id_precotizacion == pre.id_precotizacion))
    assert cod.utilizado is False
    assert db.get(Precotizacion, pre.id_precotizacion).estado == "ENVIADA"


def test_aceptar_datos_invalidos(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    _solicitar_y_codigo(cliente, pre, smtp_ok)

    # empty name
    assert cliente.post(f"/propuesta/{pre.token}/aceptar",
        json={"nombre_aceptante": "  ", "cargo_aceptante": "x", "codigo": "123456"}).status_code == 422
    # name too long
    assert cliente.post(f"/propuesta/{pre.token}/aceptar",
        json={"nombre_aceptante": "x" * 151, "cargo_aceptante": "x", "codigo": "123456"}).status_code == 422
    # cargo too long
    assert cliente.post(f"/propuesta/{pre.token}/aceptar",
        json={"nombre_aceptante": "x", "cargo_aceptante": "y" * 101, "codigo": "123456"}).status_code == 422


@pytest.mark.parametrize("codigo", [123456, None, ["1"], {"a": 1}, "12345", "12a456", "١٢٣٤٥٦"])
def test_aceptar_codigo_tipos_invalidos(cliente, fabrica, db, smtp_ok, codigo):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    _solicitar_y_codigo(cliente, pre, smtp_ok)

    r = cliente.post(
        f"/propuesta/{pre.token}/aceptar",
        json={"nombre_aceptante": "Ana", "cargo_aceptante": "Jefa", "codigo": codigo},
    )
    assert r.status_code == 422
    # the submitted code must not be echoed
    assert str(codigo) not in r.text or codigo in ("12345",)  # generic message only


def test_aceptar_json_invalido(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    _solicitar_y_codigo(cliente, pre, smtp_ok)

    r = cliente.post(
        f"/propuesta/{pre.token}/aceptar",
        content=b"{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422


def test_aceptar_campos_adicionales(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)

    r = cliente.post(
        f"/propuesta/{pre.token}/aceptar",
        json={
            "nombre_aceptante": "Ana", "cargo_aceptante": "Jefa", "codigo": codigo,
            "estado": "ACEPTADA", "correo_aceptante": "otro@x.com", "id_precotizacion": 999,
        },
    )
    assert r.status_code == 422          # extra fields forbidden


def test_aceptar_respuesta_sin_secretos(cliente, fabrica, db, smtp_ok):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)

    r = _aceptar(cliente, pre.token, codigo=codigo)

    assert codigo not in r.text
    assert "v1$" not in r.text
    assert str(pre.token) not in r.text
    assert "cliente@example.com" not in r.text


def test_aceptar_bloquea_edicion_comercial(cliente, fabrica, auth, db, smtp_ok):
    """After acceptance, the proposal is frozen: commercial survey edit → 409."""
    datos = fabrica.escenario()
    # a chair to edit
    silla = cliente.post(
        f"/visitas/{datos['visita'].id_visita}/sillas",
        json={"id_empleado": datos["empleado"].id_empleado, "cargo": datos["empleado"].cargo},
        headers=auth(datos["tecnico"]),
    ).json()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)
    assert _aceptar(cliente, pre.token, codigo=codigo).status_code == 200

    r = cliente.put(
        f"/sillas/{silla['id_silla']}/comercial",
        json={"observaciones": "cambio tardío"},
        headers=auth(datos["comercial"]),
    )
    assert r.status_code == 409


def test_aceptar_concurrencia_solo_una(cliente, fabrica, db, smtp_ok):
    """Two acceptances with the same code: at most one succeeds.

    Executed sequentially here (a TestClient-based true-concurrency test needs
    independent connections against the isolated PostgreSQL). Documented as NOT
    a transactional-concurrency proof.
    """
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)

    primera = _aceptar(cliente, pre.token, codigo=codigo)
    segunda = _aceptar(cliente, pre.token, codigo=codigo)

    assert primera.status_code == 200
    assert segunda.status_code == 409


# ===========================================================================
# HU-16 — GET /precotizaciones/{id}/habilitacion-cotizacion + enforcement guard
# ===========================================================================

from app.models import AceptacionPrecotizacion as _Aceptacion
from app.services import precotizacion_rules as _reglas


def _habilitacion(cliente, auth, usuario, id_pre):
    return cliente.get(
        f"/precotizaciones/{id_pre}/habilitacion-cotizacion", headers=auth(usuario)
    )


@pytest.mark.parametrize("estado", ["BORRADOR", "ENVIADA", "ANULADA"])
def test_habilitacion_estados_no_habilitados(cliente, fabrica, auth, db, estado):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos, estado=estado)

    r = _habilitacion(cliente, auth, datos["comercial"], pre.id_precotizacion)

    assert r.status_code == 200, r.text
    assert r.json() == {"habilitado": False, "estado": estado}


def test_habilitacion_aceptada_sin_registro(cliente, fabrica, auth, db):
    """ACEPTADA inserted directly (no acceptance record) → habilitado=false."""
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos, estado="ACEPTADA")

    r = _habilitacion(cliente, auth, datos["comercial"], pre.id_precotizacion)

    assert r.status_code == 200
    assert r.json() == {"habilitado": False, "estado": "ACEPTADA"}


def test_habilitacion_aceptada_con_registro_flujo_real(cliente, fabrica, auth, db, smtp_ok):
    """ACCEPT via the real OTP flow → habilitado=true."""
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)
    assert _aceptar(cliente, pre.token, codigo=codigo).status_code == 200

    r = _habilitacion(cliente, auth, datos["comercial"], pre.id_precotizacion)

    assert r.status_code == 200
    assert r.json() == {"habilitado": True, "estado": "ACEPTADA"}


def test_habilitacion_registro_de_otra_precotizacion_no_habilita(cliente, fabrica, auth, db, smtp_ok):
    """An acceptance record of a different pre-quotation does not enable this one."""
    datos = fabrica.escenario()
    # accepted pre-quotation A
    pre_a = _precotizacion(db, datos)
    codigo = _solicitar_y_codigo(cliente, pre_a, smtp_ok)
    assert _aceptar(cliente, pre_a.token, codigo=codigo).status_code == 200

    # pre-quotation B of another visit, forced to ACEPTADA WITHOUT its own record
    otra_sede = fabrica.sede(datos["empresa"])
    otra_visita = fabrica.visita(datos["empresa"], otra_sede, datos["comercial"], datos["tecnico"])
    pre_b = _precotizacion(db, {**datos, "visita": otra_visita}, estado="ACEPTADA")

    r = _habilitacion(cliente, auth, datos["comercial"], pre_b.id_precotizacion)
    assert r.json() == {"habilitado": False, "estado": "ACEPTADA"}


def test_habilitacion_inexistente(cliente, fabrica, auth):
    datos = fabrica.escenario()
    r = _habilitacion(cliente, auth, datos["comercial"], 999999)
    assert r.status_code == 404


def test_habilitacion_sin_autenticacion(cliente, fabrica, db):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    r = cliente.get(f"/precotizaciones/{pre.id_precotizacion}/habilitacion-cotizacion")
    assert r.status_code == 401


@pytest.mark.parametrize("rol", ["TECNICO", "ADMIN_CLIENTE", "EMPLEADO_CLIENTE"])
def test_habilitacion_rol_no_autorizado(cliente, fabrica, auth, db, rol):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    kwargs = {"empresa": datos["empresa"]} if rol in ("ADMIN_CLIENTE", "EMPLEADO_CLIENTE") else {}
    usuario = fabrica.usuario(rol, **kwargs)

    r = _habilitacion(cliente, auth, usuario, pre.id_precotizacion)
    assert r.status_code == 403


def test_habilitacion_comercial_autorizado(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)
    r = _habilitacion(cliente, auth, datos["comercial"], pre.id_precotizacion)
    assert r.status_code == 200


def test_habilitacion_no_crea_ni_modifica(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos, estado="ACEPTADA")
    antes_estado = pre.estado
    antes_aceptaciones = db.scalar(select(func.count()).select_from(_Aceptacion))

    _habilitacion(cliente, auth, datos["comercial"], pre.id_precotizacion)

    db.expire_all()
    assert db.get(Precotizacion, pre.id_precotizacion).estado == antes_estado
    assert db.scalar(select(func.count()).select_from(_Aceptacion)) == antes_aceptaciones


def test_enforcement_guard_rechaza_sin_aceptacion(db, fabrica):
    """exigir_cotizacion_habilitada raises when there is no acceptance."""
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos, estado="ENVIADA")
    with pytest.raises(_reglas.CotizacionNoHabilitada):
        _reglas.exigir_cotizacion_habilitada(db, pre.id_precotizacion)


def test_flujo_completo_habilitacion(cliente, fabrica, auth, db, smtp_ok):
    """ENVIADA→false, request OTP, accept, ACEPTADA→true."""
    datos = fabrica.escenario()
    pre = _precotizacion(db, datos)

    antes = _habilitacion(cliente, auth, datos["comercial"], pre.id_precotizacion)
    assert antes.json() == {"habilitado": False, "estado": "ENVIADA"}

    codigo = _solicitar_y_codigo(cliente, pre, smtp_ok)
    assert _aceptar(cliente, pre.token, codigo=codigo).status_code == 200

    despues = _habilitacion(cliente, auth, datos["comercial"], pre.id_precotizacion)
    assert despues.json() == {"habilitado": True, "estado": "ACEPTADA"}
