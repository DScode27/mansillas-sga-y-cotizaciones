"""HU-10 tests: multiple photographs per chair (upload, list, retrieve).

Integration cases use the shared fixtures from `conftest.py` and run against the
isolated, disposable PostgreSQL pointed at by `TEST_DATABASE_URL`. Photo files
are written under a per-test `tmp_path`, never a real storage folder.

The storage-helper consistency cases at the end run in true isolation (no DB).
"""

import io

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.config import settings
from app.db import get_db
from app.main import app
from app.models import Fotografia
from app.services import fotos_storage


@pytest.fixture(autouse=True)
def _almacenamiento_temporal(tmp_path, monkeypatch):
    """Point photo storage at a disposable tmp dir for every test."""
    monkeypatch.setattr(settings, "photo_storage_dir", str(tmp_path))
    return tmp_path


def _imagen(formato: str = "PNG", size=(24, 24)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (40, 80, 120)).save(buffer, formato)
    return buffer.getvalue()


def _subir(cliente, auth, usuario, id_silla, contenido=None, nombre="foto.png", tipo="image/png"):
    if contenido is None:
        contenido = _imagen()
    return cliente.post(
        f"/sillas/{id_silla}/fotos",
        files={"archivo": (nombre, contenido, tipo)},
        headers=auth(usuario),
    )


def _registrar_silla(cliente, fabrica, auth):
    datos = fabrica.escenario()
    respuesta = cliente.post(
        f"/visitas/{datos['visita'].id_visita}/sillas",
        json={"id_empleado": datos["empleado"].id_empleado, "cargo": datos["empleado"].cargo},
        headers=auth(datos["tecnico"]),
    )
    assert respuesta.status_code == 201, respuesta.text
    datos["silla"] = respuesta.json()
    return datos


def _contar_fotos(db) -> int:
    return db.scalar(select(func.count()).select_from(Fotografia))


# --- Upload (Requirement 3) -------------------------------------------------

def test_subir_una_foto(cliente, fabrica, auth, db, tmp_path):
    """Req 3.1: the photo is stored, the row exists linked to the chair, and the
    physical file is present."""
    datos = _registrar_silla(cliente, fabrica, auth)
    id_silla = datos["silla"]["id_silla"]

    respuesta = _subir(cliente, auth, datos["tecnico"], id_silla)

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id_silla"] == id_silla
    # nombre_archivo is derived from the stored UUID filename.
    assert cuerpo["nombre_archivo"] == cuerpo["ruta_archivo"]
    assert cuerpo["nombre_archivo"].endswith(".png")

    # Row exists in PostgreSQL and is linked to the chair.
    db.expire_all()
    foto = db.get(Fotografia, cuerpo["id_fotografia"])
    assert foto is not None
    assert foto.id_silla == id_silla
    assert foto.ruta_archivo == cuerpo["ruta_archivo"]

    # Physical file exists on disk.
    assert (tmp_path / cuerpo["ruta_archivo"]).is_file()


def test_subir_multiples_fotos(cliente, fabrica, auth, db):
    """Req 3.2: multiple photos per chair; distinct ids and paths; the listing
    contains exactly the registered photos."""
    datos = _registrar_silla(cliente, fabrica, auth)
    id_silla = datos["silla"]["id_silla"]

    primera = _subir(cliente, auth, datos["tecnico"], id_silla)
    segunda = _subir(cliente, auth, datos["tecnico"], id_silla, contenido=_imagen("JPEG"), tipo="image/jpeg")
    assert primera.status_code == 201, primera.text
    assert segunda.status_code == 201, segunda.text

    p, s = primera.json(), segunda.json()
    assert p["id_fotografia"] != s["id_fotografia"]
    assert p["ruta_archivo"] != s["ruta_archivo"]

    listado = cliente.get(f"/sillas/{id_silla}/fotos", headers=auth(datos["tecnico"]))
    assert listado.status_code == 200, listado.text
    ids = {f["id_fotografia"] for f in listado.json()}
    assert ids == {p["id_fotografia"], s["id_fotografia"]}
    assert _contar_fotos(db) == 2


def test_subir_sin_archivo(cliente, fabrica, auth, db):
    """Contract: a missing multipart field is a 422 and creates no row."""
    datos = _registrar_silla(cliente, fabrica, auth)

    respuesta = cliente.post(
        f"/sillas/{datos['silla']['id_silla']}/fotos",
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 422
    assert _contar_fotos(db) == 0


def test_subir_contenido_no_imagen(cliente, fabrica, auth, db, tmp_path):
    """Req 3.3: non-image content → 400, no row and no file."""
    datos = _registrar_silla(cliente, fabrica, auth)
    id_silla = datos["silla"]["id_silla"]

    respuesta = _subir(cliente, auth, datos["tecnico"], id_silla, contenido=b"esto no es imagen")

    assert respuesta.status_code == 400
    assert _contar_fotos(db) == 0
    assert list(tmp_path.glob("*")) == []


def test_subir_extension_valida_contenido_invalido(cliente, fabrica, auth, db, tmp_path):
    """Req 3.3: a .png name with non-image bytes is rejected (content check)."""
    datos = _registrar_silla(cliente, fabrica, auth)

    respuesta = _subir(
        cliente, auth, datos["tecnico"], datos["silla"]["id_silla"],
        contenido=b"\x89PNG\r\n not really a png", nombre="falsa.png", tipo="image/png",
    )

    assert respuesta.status_code == 400
    assert _contar_fotos(db) == 0
    assert list(tmp_path.glob("*")) == []


def test_subir_imagen_truncada(cliente, fabrica, auth, db, tmp_path):
    """Req 3.3: a truncated image is rejected with 400, no row and no file."""
    datos = _registrar_silla(cliente, fabrica, auth)
    completa = _imagen("PNG", (64, 64))

    respuesta = _subir(
        cliente, auth, datos["tecnico"], datos["silla"]["id_silla"],
        contenido=completa[: len(completa) // 2],
    )

    assert respuesta.status_code == 400
    assert _contar_fotos(db) == 0
    assert list(tmp_path.glob("*")) == []


def test_subir_formato_no_permitido(cliente, fabrica, auth, db, tmp_path):
    """Req 3.3: a valid image in a disallowed format (GIF) is rejected with 400."""
    datos = _registrar_silla(cliente, fabrica, auth)
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (1, 2, 3)).save(buffer, "GIF")

    respuesta = _subir(
        cliente, auth, datos["tecnico"], datos["silla"]["id_silla"],
        contenido=buffer.getvalue(), nombre="a.gif", tipo="image/gif",
    )

    assert respuesta.status_code == 400
    assert _contar_fotos(db) == 0
    assert list(tmp_path.glob("*")) == []


def test_subir_archivo_demasiado_grande(cliente, fabrica, auth, db, tmp_path, monkeypatch):
    """A file over the limit → 413, no row and no file."""
    datos = _registrar_silla(cliente, fabrica, auth)
    monkeypatch.setattr(settings, "photo_max_bytes", 100)

    respuesta = _subir(
        cliente, auth, datos["tecnico"], datos["silla"]["id_silla"],
        contenido=_imagen(size=(300, 300)),
    )

    assert respuesta.status_code == 413
    assert _contar_fotos(db) == 0
    assert list(tmp_path.glob("*")) == []


def test_subir_silla_inexistente(cliente, fabrica, auth, db):
    """Req 3.4: uploading to an unknown chair returns 404 and creates no row."""
    fabrica.escenario()
    tecnico = fabrica.usuario("TECNICO")

    respuesta = _subir(cliente, auth, tecnico, 999999)

    assert respuesta.status_code == 404
    assert _contar_fotos(db) == 0


def test_subir_tecnico_ajeno(cliente, fabrica, auth, db, tmp_path):
    """Req 3.5: a technician who does not own the chair's visit → 403, no row/file."""
    datos = _registrar_silla(cliente, fabrica, auth)
    otro_tecnico = fabrica.usuario("TECNICO")

    respuesta = _subir(cliente, auth, otro_tecnico, datos["silla"]["id_silla"])

    assert respuesta.status_code == 403
    assert _contar_fotos(db) == 0
    assert list(tmp_path.glob("*")) == []


def test_subir_rol_no_autorizado(cliente, fabrica, auth, db, tmp_path):
    """Req 3.5: a commercial (non-technician) cannot upload."""
    datos = _registrar_silla(cliente, fabrica, auth)

    respuesta = _subir(cliente, auth, datos["comercial"], datos["silla"]["id_silla"])

    assert respuesta.status_code == 403
    assert _contar_fotos(db) == 0
    assert list(tmp_path.glob("*")) == []


# --- List and retrieve (Requirement 4) --------------------------------------

def test_listar_fotos_vacio(cliente, fabrica, auth):
    """Req 4.3: a chair with no photos returns an empty list."""
    datos = _registrar_silla(cliente, fabrica, auth)

    respuesta = cliente.get(
        f"/sillas/{datos['silla']['id_silla']}/fotos",
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_listar_y_recuperar_comercial_distinto(cliente, fabrica, auth):
    """Req 4.1/4.2/4.4: a commercial other than the one assigned to the visit can
    list and retrieve the photos of any chair."""
    datos = _registrar_silla(cliente, fabrica, auth)
    subida = _subir(cliente, auth, datos["tecnico"], datos["silla"]["id_silla"])
    assert subida.status_code == 201, subida.text
    otro_comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    listado = cliente.get(
        f"/sillas/{datos['silla']['id_silla']}/fotos",
        headers=auth(otro_comercial),
    )
    assert listado.status_code == 200
    assert len(listado.json()) == 1

    imagen = cliente.get(
        f"/sillas/{datos['silla']['id_silla']}/fotos/{subida.json()['id_fotografia']}",
        headers=auth(otro_comercial),
    )
    assert imagen.status_code == 200


def test_recuperar_imagen_bytes_identicos(cliente, fabrica, auth):
    """Req 4.2: retrieval streams exactly the uploaded bytes."""
    datos = _registrar_silla(cliente, fabrica, auth)
    original = _imagen()
    subida = _subir(cliente, auth, datos["tecnico"], datos["silla"]["id_silla"], contenido=original)
    assert subida.status_code == 201, subida.text

    respuesta = cliente.get(
        f"/sillas/{datos['silla']['id_silla']}/fotos/{subida.json()['id_fotografia']}",
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "image/png"
    assert respuesta.content == original


def test_recuperar_foto_de_otra_silla(cliente, fabrica, auth):
    """A photo id that belongs to a different chair than the URL → 404."""
    datos = _registrar_silla(cliente, fabrica, auth)
    subida_a = _subir(cliente, auth, datos["tecnico"], datos["silla"]["id_silla"])
    assert subida_a.status_code == 201, subida_a.text

    otra = cliente.post(
        f"/visitas/{datos['visita'].id_visita}/sillas",
        json={"id_empleado": datos["empleado"].id_empleado, "cargo": datos["empleado"].cargo},
        headers=auth(datos["tecnico"]),
    )
    assert otra.status_code == 201, otra.text

    respuesta = cliente.get(
        f"/sillas/{otra.json()['id_silla']}/fotos/{subida_a.json()['id_fotografia']}",
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 404


def test_recuperar_archivo_fisico_faltante(cliente, fabrica, auth, tmp_path):
    """A row whose physical file is missing on disk → 404."""
    datos = _registrar_silla(cliente, fabrica, auth)
    subida = _subir(cliente, auth, datos["tecnico"], datos["silla"]["id_silla"])
    assert subida.status_code == 201, subida.text

    (tmp_path / subida.json()["ruta_archivo"]).unlink()

    respuesta = cliente.get(
        f"/sillas/{datos['silla']['id_silla']}/fotos/{subida.json()['id_fotografia']}",
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 404


def test_recuperar_tecnico_ajeno(cliente, fabrica, auth):
    """Req 4.5: a technician who does not own the chair cannot retrieve the image."""
    datos = _registrar_silla(cliente, fabrica, auth)
    subida = _subir(cliente, auth, datos["tecnico"], datos["silla"]["id_silla"])
    assert subida.status_code == 201, subida.text
    otro_tecnico = fabrica.usuario("TECNICO")

    respuesta = cliente.get(
        f"/sillas/{datos['silla']['id_silla']}/fotos/{subida.json()['id_fotografia']}",
        headers=auth(otro_tecnico),
    )

    assert respuesta.status_code == 403


def test_recuperar_rol_no_autorizado(cliente, fabrica, auth):
    """Req 4.5: a role other than tecnico/comercial cannot retrieve the image."""
    datos = _registrar_silla(cliente, fabrica, auth)
    subida = _subir(cliente, auth, datos["tecnico"], datos["silla"]["id_silla"])
    assert subida.status_code == 201, subida.text
    admin_cliente = fabrica.usuario("ADMIN_CLIENTE", empresa=datos["empresa"])

    respuesta = cliente.get(
        f"/sillas/{datos['silla']['id_silla']}/fotos/{subida.json()['id_fotografia']}",
        headers=auth(admin_cliente),
    )

    assert respuesta.status_code == 403


def test_recuperar_sin_autenticacion(cliente, fabrica, auth):
    """Req 4.5: retrieval without an identity is rejected (401)."""
    datos = _registrar_silla(cliente, fabrica, auth)
    subida = _subir(cliente, auth, datos["tecnico"], datos["silla"]["id_silla"])
    assert subida.status_code == 201, subida.text

    respuesta = cliente.get(
        f"/sillas/{datos['silla']['id_silla']}/fotos/{subida.json()['id_fotografia']}",
    )

    assert respuesta.status_code == 401


def test_consulta_no_autorizada(cliente, fabrica, auth):
    """Req 4.5: a technician who does not own the chair cannot list photos."""
    datos = _registrar_silla(cliente, fabrica, auth)
    otro_tecnico = fabrica.usuario("TECNICO")

    respuesta = cliente.get(
        f"/sillas/{datos['silla']['id_silla']}/fotos",
        headers=auth(otro_tecnico),
    )

    assert respuesta.status_code == 403


def test_consulta_sin_autenticacion(cliente, fabrica, auth):
    """Req 4.5: listing without an identity is rejected (401)."""
    datos = _registrar_silla(cliente, fabrica, auth)

    respuesta = cliente.get(f"/sillas/{datos['silla']['id_silla']}/fotos")

    assert respuesta.status_code == 401


def test_consulta_silla_inexistente(cliente, fabrica, auth):
    """Req 4.6: listing photos of an unknown chair returns 404."""
    datos = fabrica.escenario()

    respuesta = cliente.get("/sillas/999999/fotos", headers=auth(datos["tecnico"]))

    assert respuesta.status_code == 404


def test_fotos_no_expuestas_por_token_publico(cliente, fabrica, auth):
    """Req 4.7: the public token endpoint does not expose photographs, even when
    a photo has been uploaded successfully."""
    datos = _registrar_silla(cliente, fabrica, auth)
    subida = _subir(cliente, auth, datos["tecnico"], datos["silla"]["id_silla"])
    assert subida.status_code == 201, subida.text

    publica = cliente.get(f"/sillas/token/{datos['silla']['token_publico']}")

    assert publica.status_code == 200
    assert "fotos" not in publica.json()
    assert "fotografias" not in publica.json()


# --- Router-level compensation (Requirements 3.6, 3.7) ----------------------
# These drive the endpoint with a failing / succeeding commit, verifying the
# router's own compensation behaviour (not just the storage helper).

def _override_db(db, **attrs):
    """Build a `get_db` override yielding `db` with patched attributes.

    Returns a generator function suitable for `app.dependency_overrides`.
    """

    def _gen():
        originales = {name: getattr(db, name) for name in attrs}
        for name, value in attrs.items():
            setattr(db, name, value)
        try:
            yield db
        finally:
            for name, original in originales.items():
                setattr(db, name, original)

    return _gen


def test_router_compensa_al_fallar_commit(cliente, fabrica, auth, db, tmp_path):
    """Req 3.6: a confirmed pre-commit failure removes the stored file and leaves
    no row (router-level, via a dependency override)."""
    datos = _registrar_silla(cliente, fabrica, auth)
    id_silla = datos["silla"]["id_silla"]

    def _commit_falla():
        raise RuntimeError("commit boom")  # non-DBAPI → confirmed pre-commit

    previos = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _override_db(db, commit=_commit_falla)
    try:
        respuesta = _subir(cliente, auth, datos["tecnico"], id_silla)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previos)

    assert respuesta.status_code == 500
    db.rollback()
    assert _contar_fotos(db) == 0
    # The compensating delete removed the just-stored file.
    assert list(tmp_path.glob("*")) == []


def test_router_commit_incierto_conserva_archivo(cliente, fabrica, auth, db, tmp_path):
    """Req 3.6 (residual): when the commit outcome is uncertain (connection
    invalidated during COMMIT), the file is KEPT, to avoid orphaning a possibly
    committed row."""
    from sqlalchemy.exc import DBAPIError

    datos = _registrar_silla(cliente, fabrica, auth)
    id_silla = datos["silla"]["id_silla"]

    def _commit_incierto():
        error = DBAPIError("COMMIT", {}, Exception("connection lost"))
        error.connection_invalidated = True
        raise error

    previos = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _override_db(db, commit=_commit_incierto)
    try:
        respuesta = _subir(cliente, auth, datos["tecnico"], id_silla)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previos)

    assert respuesta.status_code == 500
    # The file is kept despite the error (uncertain commit, not compensated).
    db.rollback()
    assert len(list(tmp_path.glob("*"))) == 1


def test_router_no_borra_tras_commit_exitoso(cliente, fabrica, auth, db, tmp_path, monkeypatch):
    """A failure AFTER a successful commit must not delete the stored file.

    The router does not catch a post-commit error, so TestClient (with its
    default `raise_server_exceptions=True`) re-raises it; the assertion uses
    `pytest.raises`. The committed row and the stored file must remain.
    """
    import app.routers.fotos as fotos_router

    datos = _registrar_silla(cliente, fabrica, auth)
    id_silla = datos["silla"]["id_silla"]

    eliminaciones = []
    monkeypatch.setattr(
        fotos_router.fotos_storage, "eliminar", lambda n: eliminaciones.append(n)
    )

    def _refresh_falla(obj, *a, **k):
        raise RuntimeError("refresh boom")  # raised AFTER a successful commit

    previos = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _override_db(db, refresh=_refresh_falla)
    try:
        with pytest.raises(RuntimeError, match="refresh boom"):
            _subir(cliente, auth, datos["tecnico"], id_silla)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previos)

    # Row committed and file kept; compensation must NOT have been called.
    assert eliminaciones == []
    db.rollback()
    assert _contar_fotos(db) == 1
    fila = db.scalars(select(Fotografia)).first()
    assert (tmp_path / fila.ruta_archivo).is_file()


# --- Storage helper consistency in isolation (Requirements 3.6, 3.7, 3.8) ---
# These exercise the storage helper directly (no DB, no HTTP).

def test_helper_fallo_escritura_no_deja_archivo(tmp_path, monkeypatch):
    """Req 3.8 (helper): a write failure leaves no partial file and raises."""
    monkeypatch.setattr(settings, "photo_storage_dir", str(tmp_path))

    import pathlib

    def _falla(self, _data):  # noqa: ANN001
        raise OSError("disk full")

    monkeypatch.setattr(pathlib.Path, "write_bytes", _falla)
    with pytest.raises(fotos_storage.FotoAlmacenamientoError):
        fotos_storage.guardar(b"datos", ".png")
    assert list(tmp_path.glob("*")) == []


def test_helper_eliminar_borra_archivo(tmp_path, monkeypatch):
    """Req 3.6 (helper): eliminar removes a stored file."""
    monkeypatch.setattr(settings, "photo_storage_dir", str(tmp_path))
    nombre = fotos_storage.guardar(_imagen(), ".png")
    assert (tmp_path / nombre).exists()

    fotos_storage.eliminar(nombre)
    assert not (tmp_path / nombre).exists()


def test_helper_fallo_borrado_se_registra(tmp_path, monkeypatch, caplog):
    """Req 3.7 (helper): a failing compensating delete is logged, not raised."""
    monkeypatch.setattr(settings, "photo_storage_dir", str(tmp_path))
    nombre = fotos_storage.guardar(_imagen(), ".png")

    import pathlib

    def _falla_unlink(self, missing_ok=False):  # noqa: ANN001
        raise OSError("permiso denegado")

    monkeypatch.setattr(pathlib.Path, "unlink", _falla_unlink)
    with caplog.at_level("ERROR"):
        fotos_storage.eliminar(nombre)  # must not raise
    assert any("huérfana" in m or "orphan" in m.lower() for m in caplog.messages)
