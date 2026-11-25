import jwt
from sqlalchemy import text

from app.config import settings
from app.security import hash_token

PASSWORD = "Secreta123"


def _login(cliente, correo: str, password: str = PASSWORD):
    return cliente.post("/auth/login", json={"correo": correo, "password": password})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_devuelve_token(cliente, fabrica):
    usuario = fabrica.usuario("COMERCIAL_MANSILLAS", password=PASSWORD)

    respuesta = _login(cliente, usuario.correo)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["access_token"]
    assert cuerpo["usuario"]["id_usuario"] == usuario.id_usuario
    assert cuerpo["usuario"]["rol"] == "COMERCIAL_MANSILLAS"
    assert "password_hash" not in cuerpo["usuario"]


def test_login_guarda_solo_el_hash_del_token(cliente, fabrica, db):
    usuario = fabrica.usuario("TECNICO", password=PASSWORD)
    token = _login(cliente, usuario.correo).json()["access_token"]

    guardado = db.execute(
        text("SELECT token_hash FROM sesion_usuario WHERE id_usuario = :id"),
        {"id": usuario.id_usuario},
    ).scalar()

    assert guardado == hash_token(token)
    assert guardado != token


def test_login_password_incorrecta(cliente, fabrica):
    usuario = fabrica.usuario("TECNICO", password=PASSWORD)
    assert _login(cliente, usuario.correo, "otra-clave").status_code == 401


def test_login_usuario_inexistente(cliente):
    assert _login(cliente, "nadie@test.local").status_code == 401


def test_login_usuario_inactivo(cliente, fabrica, db):
    usuario = fabrica.usuario("TECNICO", password=PASSWORD)
    db.execute(
        text("UPDATE usuario SET activo = false WHERE id_usuario = :id"),
        {"id": usuario.id_usuario},
    )
    db.commit()

    assert _login(cliente, usuario.correo).status_code == 401


def test_login_no_permite_empleado_cliente(cliente, fabrica):
    empresa = fabrica.empresa()
    usuario = fabrica.usuario("EMPLEADO_CLIENTE", empresa=empresa, password=PASSWORD)

    assert _login(cliente, usuario.correo).status_code == 401


def test_token_autentica_endpoint_protegido(cliente, fabrica):
    usuario = fabrica.usuario("COMERCIAL_MANSILLAS", password=PASSWORD)
    token = _login(cliente, usuario.correo).json()["access_token"]

    respuesta = cliente.get("/visitas", headers=_bearer(token))

    assert respuesta.status_code == 200, respuesta.text


def test_token_hereda_el_rol_de_la_base(cliente, fabrica):
    usuario = fabrica.usuario("TECNICO", password=PASSWORD)
    datos = fabrica.escenario(tecnico=usuario)
    token = _login(cliente, usuario.correo).json()["access_token"]

    respuesta = cliente.post(
        "/visitas",
        json={
            "id_empresa": datos["empresa"].id_empresa,
            "id_sede": datos["sede"].id_sede,
            "id_tecnico": usuario.id_usuario,
            "cantidad_estimada": 3,
        },
        headers=_bearer(token),
    )

    assert respuesta.status_code == 403, respuesta.text


def test_token_firmado_sin_sesion_es_rechazado(cliente, fabrica):
    usuario = fabrica.usuario("TECNICO")
    token = jwt.encode(
        {"sub": str(usuario.id_usuario), "rol": "TECNICO"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    assert cliente.get("/visitas", headers=_bearer(token)).status_code == 401


def test_token_basura_es_rechazado(cliente):
    assert cliente.get("/visitas", headers=_bearer("no-es-un-jwt")).status_code == 401


def test_bearer_vacio_es_rechazado(cliente):
    assert cliente.get("/visitas", headers={"Authorization": "Bearer "}).status_code == 401


def test_sesion_cerrada_es_rechazada(cliente, fabrica, db):
    usuario = fabrica.usuario("COMERCIAL_MANSILLAS", password=PASSWORD)
    token = _login(cliente, usuario.correo).json()["access_token"]

    db.execute(text("UPDATE sesion_usuario SET fecha_cierre = now()"))
    db.commit()

    respuesta = cliente.get("/visitas", headers=_bearer(token))

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "Sesión inválida o cerrada"


def test_sesion_expirada_es_rechazada(cliente, fabrica, db):
    usuario = fabrica.usuario("COMERCIAL_MANSILLAS", password=PASSWORD)
    token = _login(cliente, usuario.correo).json()["access_token"]

    db.execute(
        text(
            "UPDATE sesion_usuario SET fecha_inicio = now() - interval '2 hours', "
            "fecha_expiracion = now() - interval '1 minute'"
        )
    )
    db.commit()

    respuesta = cliente.get("/visitas", headers=_bearer(token))

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "Sesión expirada"


def test_inactividad_cierra_la_sesion(cliente, fabrica, db):
    usuario = fabrica.usuario("COMERCIAL_MANSILLAS", password=PASSWORD)
    token = _login(cliente, usuario.correo).json()["access_token"]

    db.execute(
        text(
            "UPDATE sesion_usuario "
            "SET ultima_actividad = now() - interval '2 hours'"
        )
    )
    db.commit()

    respuesta = cliente.get("/visitas", headers=_bearer(token))

    assert respuesta.status_code == 401
    assert respuesta.json()["detail"] == "Sesión cerrada por inactividad"

    cerrada = db.execute(text("SELECT fecha_cierre FROM sesion_usuario")).scalar()
    assert cerrada is not None


def test_actividad_se_actualiza_en_cada_uso(cliente, fabrica, db):
    usuario = fabrica.usuario("COMERCIAL_MANSILLAS", password=PASSWORD)
    token = _login(cliente, usuario.correo).json()["access_token"]

    db.execute(
        text("UPDATE sesion_usuario SET ultima_actividad = now() - interval '5 minutes'")
    )
    db.commit()

    assert cliente.get("/visitas", headers=_bearer(token)).status_code == 200

    reciente = db.execute(
        text("SELECT now() - ultima_actividad < interval '10 seconds' FROM sesion_usuario")
    ).scalar()
    assert reciente is True
