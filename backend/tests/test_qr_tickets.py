"""Pruebas de ejemplo de HU-24: OTP y creación de tickets por QR (tarea 8.4).

Ejercitan los endpoints públicos del router `app/routers/qr.py` contra
PostgreSQL real (fixtures `cliente`, `fabrica`, `db` de `conftest.py`):

- `POST /qr/silla/{token}/otp`   → solicitud de OTP (identifica por correo/documento).
- `POST /qr/silla/{token}/ticket` → creación de ticket con el OTP emitido.

El OTP en claro se recupera del `EmailSenderFalso` instalado por la fixture
`email_falso` (vía `app.dependency_overrides[get_email_sender]`), ya que en la
BD solo vive su hash. El nivel `empresa.permiso_qr` se fija con el ajustador
`con_permiso` (UPDATE directo), cubriendo los tres niveles.

Cubre la matriz de permiso (1 → 403 "Permiso insuficiente", 2 → ticket creado,
3 → 403 "Solo el administrador del cliente puede crear tickets"), el rechazo de
OTP inválido/expirado/usado, el empleado no identificado (404) y la asociación
del ticket a la silla y, vía `silla.id_empleado`, al empleado. Incluye edge
cases: `correo`/`documento` ambos nulos y `asunto`/`descripcion` vacíos.

Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10
"""

from sqlalchemy import text

from app.config import settings

# Las fixtures `email_falso` y `con_permiso` y los helpers viven en
# `tests/helpers_qr.py`; se importan aquí para que pytest las resuelva en este
# módulo (no están registradas como plugin global).
from helpers_qr import con_permiso, email_falso  # noqa: F401


# --- Utilidades locales -----------------------------------------------------


def _token(silla) -> str:
    """Token público de la silla, tal como viaja en la URL del QR."""
    return str(silla.token_publico)


def _preparar(fabrica):
    """Escenario base: devuelve `(datos, silla)` con silla ligada a un empleado.

    Reutiliza `Fabrica.escenario()` (empresa + sede + departamento + empleado +
    visita) y crea una silla asignada a ese empleado, de modo que
    `silla.id_empleado` apunte al empleado identificable por correo/documento.
    """
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    return datos, silla


def _emitir_otp(cliente, silla, sender, *, correo=None, documento=None) -> str:
    """Solicita un OTP y devuelve el código en claro capturado por el sender.

    El endpoint responde 204 y el OTP real se lee del `EmailSenderFalso`
    (`ultimo_codigo`), nunca de la BD (donde solo está su hash).
    """
    payload = {}
    if correo is not None:
        payload["correo"] = correo
    if documento is not None:
        payload["documento"] = documento

    respuesta = cliente.post(f"/qr/silla/{_token(silla)}/otp", json=payload)
    assert respuesta.status_code == 204, respuesta.text
    return sender.ultimo_codigo()


def _tickets_de_silla(db, id_silla: int) -> list[dict]:
    """Filas de `ticket` asociadas a la silla (fuente de verdad en la BD)."""
    db.expire_all()
    filas = db.execute(
        text(
            "SELECT id_ticket, id_silla, estado, fecha_creacion "
            f"FROM {settings.db_schema}.ticket WHERE id_silla = :id_silla"
        ),
        {"id_silla": id_silla},
    ).mappings().all()
    return [dict(fila) for fila in filas]


def _silla_id_empleado(db, id_silla: int) -> int:
    """`silla.id_empleado`: a través de él el ticket queda ligado al empleado."""
    db.expire_all()
    return int(
        db.execute(
            text(
                f"SELECT id_empleado FROM {settings.db_schema}.silla "
                "WHERE id_silla = :id_silla"
            ),
            {"id_silla": id_silla},
        ).scalar_one()
    )


# --- Matriz de permiso para tickets de empleado (Req 3.2, 3.3, 3.4) ---------


# Permiso 1 → el QR no habilita tickets: 403 "Permiso insuficiente".
# Validates: Requirements 3.2
def test_permiso_1_rechaza_ticket(cliente, fabrica, db, email_falso, con_permiso):
    datos, silla = _preparar(fabrica)
    # El OTP se emite antes de bajar el permiso: la validación del permiso es lo
    # primero que hace el endpoint de ticket, así que debe cortar aun con OTP válido.
    con_permiso(datos["empresa"], 2)
    codigo = _emitir_otp(cliente, silla, email_falso, correo=datos["empleado"].correo)
    con_permiso(datos["empresa"], 1)

    respuesta = cliente.post(
        f"/qr/silla/{_token(silla)}/ticket",
        json={
            "asunto": "Rueda rota",
            "descripcion": "La silla no gira",
            "correo": datos["empleado"].correo,
            "codigo": codigo,
        },
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "Permiso insuficiente"
    # No se creó ningún ticket.
    assert _tickets_de_silla(db, silla.id_silla) == []


# Permiso 3 → solo el ADMIN_CLIENTE crea tickets: 403 con el mensaje específico.
# Validates: Requirements 3.3
def test_permiso_3_rechaza_ticket_empleado(
    cliente, fabrica, db, email_falso, con_permiso
):
    datos, silla = _preparar(fabrica)
    con_permiso(datos["empresa"], 2)
    codigo = _emitir_otp(cliente, silla, email_falso, correo=datos["empleado"].correo)
    con_permiso(datos["empresa"], 3)

    respuesta = cliente.post(
        f"/qr/silla/{_token(silla)}/ticket",
        json={
            "asunto": "Rueda rota",
            "descripcion": "La silla no gira",
            "correo": datos["empleado"].correo,
            "codigo": codigo,
        },
    )

    assert respuesta.status_code == 403
    assert (
        respuesta.json()["detail"]
        == "Solo el administrador del cliente puede crear tickets"
    )
    assert _tickets_de_silla(db, silla.id_silla) == []


# Permiso 2 con OTP válido → ticket creado (201); asociación a silla y empleado.
# Validates: Requirements 3.4, 3.7, 3.10
def test_permiso_2_crea_ticket_asociado_a_silla_y_empleado(
    cliente, fabrica, db, email_falso, con_permiso
):
    datos, silla = _preparar(fabrica)
    con_permiso(datos["empresa"], 2)
    codigo = _emitir_otp(cliente, silla, email_falso, correo=datos["empleado"].correo)

    respuesta = cliente.post(
        f"/qr/silla/{_token(silla)}/ticket",
        json={
            "asunto": "Rueda rota",
            "descripcion": "La silla no gira al sentarse",
            "correo": datos["empleado"].correo,
            "codigo": codigo,
        },
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id_silla"] == silla.id_silla
    assert cuerpo["estado"] == "ABIERTO"
    assert cuerpo["fecha_creacion"]  # definida por la BD
    assert cuerpo["asunto"] == "Rueda rota"
    # La respuesta pública no expone datos personales del empleado.
    assert datos["empleado"].nombre not in respuesta.text
    assert datos["empleado"].documento not in respuesta.text
    assert datos["empleado"].correo not in respuesta.text

    # El ticket existe en la BD, ligado a la silla...
    filas = _tickets_de_silla(db, silla.id_silla)
    assert len(filas) == 1
    assert filas[0]["id_ticket"] == cuerpo["id_ticket"]
    assert filas[0]["estado"] == "ABIERTO"
    assert filas[0]["fecha_creacion"] is not None
    # ...y, vía silla.id_empleado, a la persona asignada a esa silla.
    assert _silla_id_empleado(db, silla.id_silla) == datos["empleado"].id_empleado


# El flujo también funciona identificando al empleado por documento.
# Validates: Requirements 3.4, 3.5, 3.7
def test_permiso_2_crea_ticket_identificando_por_documento(
    cliente, fabrica, db, email_falso, con_permiso
):
    datos, silla = _preparar(fabrica)
    con_permiso(datos["empresa"], 2)
    codigo = _emitir_otp(
        cliente, silla, email_falso, documento=datos["empleado"].documento
    )

    respuesta = cliente.post(
        f"/qr/silla/{_token(silla)}/ticket",
        json={
            "asunto": "Apoyabrazos suelto",
            "descripcion": "El apoyabrazos izquierdo se mueve",
            "documento": datos["empleado"].documento,
            "codigo": codigo,
        },
    )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["id_silla"] == silla.id_silla
    assert len(_tickets_de_silla(db, silla.id_silla)) == 1


# --- Rechazo de OTP inválido / expirado / usado (Req 3.8, 3.9) --------------


# OTP cuyo hash no coincide con ninguno almacenado → 400 "OTP inválido".
# Validates: Requirements 3.8
def test_otp_invalido(cliente, fabrica, db, email_falso, con_permiso):
    datos, silla = _preparar(fabrica)
    con_permiso(datos["empresa"], 2)
    # Se emite un OTP real pero se envía uno distinto al crear el ticket.
    _emitir_otp(cliente, silla, email_falso, correo=datos["empleado"].correo)

    respuesta = cliente.post(
        f"/qr/silla/{_token(silla)}/ticket",
        json={
            "asunto": "Rueda rota",
            "descripcion": "La silla no gira",
            "correo": datos["empleado"].correo,
            "codigo": "000000-no-coincide",
        },
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["detail"] == "OTP inválido"
    assert _tickets_de_silla(db, silla.id_silla) == []


# OTP cuya fila existe (hash coincide) pero ya expiró → 400 "OTP expirado o ya utilizado".
# Validates: Requirements 3.9
def test_otp_expirado(cliente, fabrica, db, email_falso, con_permiso):
    datos, silla = _preparar(fabrica)
    con_permiso(datos["empresa"], 2)
    codigo = _emitir_otp(cliente, silla, email_falso, correo=datos["empleado"].correo)

    # Forzar la expiración de la fila recién emitida (fecha_expiracion al pasado).
    db.execute(
        text(
            f"UPDATE {settings.db_schema}.codigo_verificacion "
            "SET fecha_expiracion = now() - interval '1 minute' "
            "WHERE id_empleado = :id_empleado"
        ),
        {"id_empleado": datos["empleado"].id_empleado},
    )
    db.commit()

    respuesta = cliente.post(
        f"/qr/silla/{_token(silla)}/ticket",
        json={
            "asunto": "Rueda rota",
            "descripcion": "La silla no gira",
            "correo": datos["empleado"].correo,
            "codigo": codigo,
        },
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["detail"] == "OTP expirado o ya utilizado"
    assert _tickets_de_silla(db, silla.id_silla) == []


# Reusar un OTP ya consumido por un ticket exitoso → 400 "OTP expirado o ya utilizado".
# Validates: Requirements 3.7, 3.9
def test_otp_reusado_tras_ticket(cliente, fabrica, db, email_falso, con_permiso):
    datos, silla = _preparar(fabrica)
    con_permiso(datos["empresa"], 2)
    codigo = _emitir_otp(cliente, silla, email_falso, correo=datos["empleado"].correo)

    primera = cliente.post(
        f"/qr/silla/{_token(silla)}/ticket",
        json={
            "asunto": "Rueda rota",
            "descripcion": "La silla no gira",
            "correo": datos["empleado"].correo,
            "codigo": codigo,
        },
    )
    assert primera.status_code == 201, primera.text

    # El mismo OTP, ya marcado utilizado=true, no vuelve a validar.
    segunda = cliente.post(
        f"/qr/silla/{_token(silla)}/ticket",
        json={
            "asunto": "Otro problema",
            "descripcion": "Reintento con el mismo código",
            "correo": datos["empleado"].correo,
            "codigo": codigo,
        },
    )

    assert segunda.status_code == 400
    assert segunda.json()["detail"] == "OTP expirado o ya utilizado"
    # Solo el primer ticket quedó creado.
    assert len(_tickets_de_silla(db, silla.id_silla)) == 1


# --- Empleado no identificado (Req 3.6) -------------------------------------


# Solicitud de OTP con correo/documento que no corresponden a ningún empleado
# de la empresa dueña → 404 "Empleado no encontrado".
# Validates: Requirements 3.6
def test_otp_empleado_no_encontrado(cliente, fabrica, email_falso, con_permiso):
    datos, silla = _preparar(fabrica)
    con_permiso(datos["empresa"], 2)

    respuesta = cliente.post(
        f"/qr/silla/{_token(silla)}/otp",
        json={"correo": "desconocido@test.local"},
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Empleado no encontrado"
    # No se capturó ningún OTP: no hubo empleado al que enviarlo.
    assert email_falso.enviados == []


# --- Edge cases (Req 3.5, 3.6, 3.7) -----------------------------------------


# Edge: OTP con `correo` y `documento` ambos nulos → ningún empleado casa → 404.
# Validates: Requirements 3.6
def test_otp_correo_y_documento_nulos(cliente, fabrica, email_falso, con_permiso):
    datos, silla = _preparar(fabrica)
    con_permiso(datos["empresa"], 2)

    respuesta = cliente.post(f"/qr/silla/{_token(silla)}/otp", json={})

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Empleado no encontrado"
    assert email_falso.enviados == []


# Edge: crear ticket con `asunto`/`descripcion` vacíos. Los schemas los definen
# como `str` obligatorios (no validan longitud mínima) y `ticket.asunto` admite
# hasta 150 chars sin NOT-NULL-ish extra, por lo que el comportamiento esperado
# es aceptar el ticket con cadenas vacías (201). Se documenta esa expectativa.
# Validates: Requirements 3.7
def test_ticket_asunto_y_descripcion_vacios(
    cliente, fabrica, db, email_falso, con_permiso
):
    datos, silla = _preparar(fabrica)
    con_permiso(datos["empresa"], 2)
    codigo = _emitir_otp(cliente, silla, email_falso, correo=datos["empleado"].correo)

    respuesta = cliente.post(
        f"/qr/silla/{_token(silla)}/ticket",
        json={
            "asunto": "",
            "descripcion": "",
            "correo": datos["empleado"].correo,
            "codigo": codigo,
        },
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["asunto"] == ""
    assert cuerpo["descripcion"] == ""
    assert cuerpo["estado"] == "ABIERTO"
    assert len(_tickets_de_silla(db, silla.id_silla)) == 1
