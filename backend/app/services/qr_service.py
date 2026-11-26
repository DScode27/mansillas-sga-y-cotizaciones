"""Lógica de negocio del QR público, OTP y tickets (HU-17, HU-24).

El router (`app/routers/qr.py`) resuelve la silla por `token_publico` y traduce
HTTP; aquí viven las excepciones de dominio y las consultas SQL parametrizadas.

Reglas de negocio respetadas:

- RN-3/RN-4: la consulta pública NUNCA expone datos personales del empleado
  (nombre, documento ni correo); solo datos básicos de la silla y el
  `permiso_qr` de la empresa dueña.
- RN-6: el alcance siempre se restringe a `silla.id_empresa`; nunca se acepta un
  identificador de empresa del cliente público.

- RN-5: el OTP se guarda SIEMPRE hasheado (`security.hash_token`), nunca en
  claro; la expiración la calcula la BD con el TTL configurable.

El envío de ticket (`crear_ticket_por_qr`) aplica `empresa.permiso_qr`, valida
el OTP y crea el ticket marcando el código como utilizado en una sola
transacción.
"""

from __future__ import annotations

import secrets
import string

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..models.silla import Silla
from ..models.ticket import Ticket
from ..security import hash_token
from . import componentes_service
from .email_service import EmailSender

# Expresión SQL de la expiración del OTP: la calcula la BD (misma reloj que el
# resto de timestamps) con el TTL configurable. `solicitar_otp` (4.3) la usa en
# el INSERT pasando `settings.otp_ttl_minutes` como parámetro `:min`.
OTP_FECHA_EXPIRACION_SQL = "now() + :min * interval '1 minute'"


class QrError(Exception):
    """Base de las excepciones de dominio del flujo QR."""


class QrNoValido(QrError):
    """El token no resuelve a una silla registrada (→ 404 "QR no válido")."""


class EmpleadoNoEncontrado(QrError):
    """Correo/documento sin empleado en la empresa dueña (→ 404)."""


class PermisoInsuficiente(QrError):
    """`permiso_qr = 1`: el QR no permite crear tickets (→ 403)."""


class SoloAdminCliente(QrError):
    """`permiso_qr = 3`: solo el administrador del cliente crea tickets (→ 403)."""


class OtpInvalido(QrError):
    """El OTP no coincide con el hash almacenado (→ 400 "OTP inválido")."""


class OtpExpiradoOUsado(QrError):
    """El OTP está expirado o ya fue utilizado (→ 400)."""


def consultar_silla_publica(db: Session, silla: Silla) -> dict:
    """Datos de la silla para la ficha pública + `permiso_qr` de la empresa dueña.

    El `silla` ya viene resuelto por el router a partir de `token_publico`.
    Se consulta en una sola fila el nombre de la empresa dueña, el nombre de su
    sede y su `permiso_qr` (SQL parametrizado, restringido a `silla.id_empresa`
    y `silla.id_sede` — RN-6), y se adjunta el estado de los componentes reusando
    `componentes_service.obtener_checklist`.

    Devuelve un dict con `id_silla`, `codigo_qr`, `estado`, `cargo`,
    `serial_antiguo`, `empresa` (nombre), `sede` (nombre), `permiso_qr` y
    `componentes` ([{id_componente, nombre, estado, observacion}]). NUNCA incluye
    nombre, documento ni correo del empleado (RN-3/RN-4): la sede/empresa y los
    componentes son datos de la silla, no del empleado.
    """
    schema = settings.db_schema

    row = db.execute(
        text(
            f"""
            SELECT e.nombre AS empresa,
                   e.permiso_qr AS permiso_qr,
                   se.nombre AS sede
            FROM {schema}.empresa AS e
            LEFT JOIN {schema}.sede AS se
                ON se.id_empresa = e.id_empresa
               AND se.id_sede = :id_sede
            WHERE e.id_empresa = :id_empresa
            """
        ),
        {"id_empresa": silla.id_empresa, "id_sede": silla.id_sede},
    ).mappings().first()

    # La silla referencia siempre a una empresa existente (FK en el SQL); si la
    # fila faltara, el QR carece de empresa dueña y no es consultable.
    if row is None:
        raise QrNoValido

    componentes = componentes_service.obtener_checklist(db, silla.id_silla)

    return {
        "id_silla": silla.id_silla,
        "codigo_qr": silla.codigo_qr,
        "estado": silla.estado,
        "cargo": silla.cargo,
        "serial_antiguo": silla.serial_antiguo,
        "empresa": row["empresa"],
        "sede": row["sede"],
        "permiso_qr": int(row["permiso_qr"]),
        "componentes": componentes,
    }


def generar_otp() -> str:
    """Genera un OTP numérico aleatorio de `settings.otp_length` dígitos.

    Usa `secrets.choice` (CSPRNG) sobre `string.digits`, así que admite ceros a
    la izquierda (el OTP es una cadena, no un entero). Se devuelve en claro solo
    para enviarlo por correo; nunca se persiste así (ver `hashear_otp`).
    """
    return "".join(secrets.choice(string.digits) for _ in range(settings.otp_length))


def hashear_otp(otp: str) -> str:
    """Hash del OTP (SHA-256 vía `security.hash_token`) para guardar en BD.

    Es lo único que se escribe en `codigo_verificacion.codigo_hash`; el OTP en
    claro nunca se almacena (RN-5).
    """
    return hash_token(otp)


def solicitar_otp(
    db: Session,
    *,
    silla: Silla,
    correo: str | None,
    documento: str | None,
    sender: EmailSender,
) -> None:
    """Emite un OTP para el empleado de la silla y lo envía a su correo (HU-24).

    Identifica al empleado por `correo` o `documento`, restringido SIEMPRE a
    `silla.id_empresa` (RN-6): nunca se acepta un identificador de empresa del
    cliente público. Si ningún empleado activo coincide, lanza
    `EmpleadoNoEncontrado` (el router lo traduce a 404).

    Para el empleado hallado inserta una fila en `codigo_verificacion` con su
    `id_empleado`, `correo_destino` igual al correo del empleado, el OTP
    hasheado (nunca en claro — RN-5), `fecha_expiracion` futura calculada por la
    BD (`OTP_FECHA_EXPIRACION_SQL` con `settings.otp_ttl_minutes`) y
    `utilizado = false`; confirma con `db.commit()` explícito (`get_db` revierte
    al cerrar la petición). Finalmente envía el OTP en claro al correo del
    empleado mediante el `EmailSender` recibido.

    Raises EmpleadoNoEncontrado.
    """
    schema = settings.db_schema

    # El empleado se busca por correo O documento, pero siempre acotado a la
    # empresa dueña de la silla (RN-6). Si ambos vienen nulos, ninguna condición
    # casa y se obtiene `EmpleadoNoEncontrado`, coherente con "no identificado".
    empleado = db.execute(
        text(
            f"SELECT id_empleado, correo FROM {schema}.empleado "
            "WHERE id_empresa = :id_empresa "
            "AND ("
            "  (:correo IS NOT NULL AND correo = :correo) "
            "  OR (:documento IS NOT NULL AND documento = :documento)"
            ")"
        ),
        {
            "id_empresa": silla.id_empresa,
            "correo": correo,
            "documento": documento,
        },
    ).mappings().first()

    if empleado is None:
        raise EmpleadoNoEncontrado

    correo_destino = empleado["correo"]
    otp = generar_otp()

    db.execute(
        text(
            f"INSERT INTO {schema}.codigo_verificacion "
            "(id_empleado, correo_destino, codigo_hash, fecha_expiracion, utilizado) "
            f"VALUES (:id_empleado, :correo_destino, :codigo_hash, {OTP_FECHA_EXPIRACION_SQL}, false)"
        ),
        {
            "id_empleado": empleado["id_empleado"],
            "correo_destino": correo_destino,
            "codigo_hash": hashear_otp(otp),
            "min": settings.otp_ttl_minutes,
        },
    )
    # `get_db` entrega una Session que revierte al cerrar la petición: la
    # inserción del código debe confirmarse explícitamente antes de enviarlo.
    db.commit()

    sender.enviar_codigo(correo_destino, otp)


def crear_ticket_por_qr(
    db: Session,
    *,
    silla: Silla,
    correo: str | None,
    documento: str | None,
    codigo: str,
    asunto: str,
    descripcion: str,
) -> Ticket:
    """Crea un ticket para la silla tras validar permiso y OTP (HU-24).

    Aplica `empresa.permiso_qr` de la empresa dueña de la silla
    (`silla.id_empresa`, RN-6): nivel 1 ⇒ `PermisoInsuficiente`; nivel 3 ⇒
    `SoloAdminCliente`; nivel 2 habilita el flujo de empleado.

    Identifica al empleado por `correo` o `documento` dentro de
    `silla.id_empresa` (mismo patrón que `solicitar_otp`) y valida su OTP más
    reciente: el hash debe coincidir, no estar `utilizado` y no haber expirado
    (`fecha_expiracion >= now()`). Un hash que no casa lanza `OtpInvalido`; un
    OTP válido en hash pero expirado o ya usado lanza `OtpExpiradoOUsado`.

    Con el OTP válido, en la MISMA transacción inserta el `ticket`
    (`id_silla` de la silla consultada, `asunto`, `descripcion`, `estado`
    'ABIERTO'; `fecha_creacion` la asigna la BD) y marca
    `codigo_verificacion.utilizado = true`, con un único `db.commit()`
    (`get_db` revierte ambos si algo falla). Devuelve el `Ticket` refrescado
    con `id_ticket` y `fecha_creacion`.

    Raises PermisoInsuficiente, SoloAdminCliente, EmpleadoNoEncontrado,
    OtpInvalido, OtpExpiradoOUsado.
    """
    schema = settings.db_schema

    # Permiso de la empresa dueña (RN-5), restringido a silla.id_empresa (RN-6).
    permiso_row = db.execute(
        text(
            f"SELECT permiso_qr FROM {schema}.empresa "
            "WHERE id_empresa = :id_empresa"
        ),
        {"id_empresa": silla.id_empresa},
    ).mappings().first()

    # La FK garantiza la empresa dueña; su ausencia deja el QR sin dueño válido.
    if permiso_row is None:
        raise QrNoValido

    permiso = int(permiso_row["permiso_qr"])
    if permiso == 1:
        raise PermisoInsuficiente
    if permiso == 3:
        raise SoloAdminCliente
    # permiso == 2 (u otro valor habilitado): continúa el flujo de empleado.

    # Empleado objetivo por correo O documento, acotado a la empresa dueña
    # (RN-6). Con ambos nulos ninguna condición casa → EmpleadoNoEncontrado.
    empleado = db.execute(
        text(
            f"SELECT id_empleado FROM {schema}.empleado "
            "WHERE id_empresa = :id_empresa "
            "AND ("
            "  (:correo IS NOT NULL AND correo = :correo) "
            "  OR (:documento IS NOT NULL AND documento = :documento)"
            ")"
        ),
        {
            "id_empresa": silla.id_empresa,
            "correo": correo,
            "documento": documento,
        },
    ).mappings().first()

    if empleado is None:
        raise EmpleadoNoEncontrado

    # OTP más reciente del empleado. Se compara el hash en SQL para no traer el
    # código en claro; `fecha_expiracion`/`utilizado` deciden entre OtpInvalido
    # (hash no casa) y OtpExpiradoOUsado (casa pero caducado/usado).
    codigo_row = db.execute(
        text(
            f"SELECT id_codigo, utilizado, fecha_expiracion >= now() AS vigente "
            f"FROM {schema}.codigo_verificacion "
            "WHERE id_empleado = :id_empleado AND codigo_hash = :codigo_hash "
            "ORDER BY id_codigo DESC LIMIT 1"
        ),
        {
            "id_empleado": empleado["id_empleado"],
            "codigo_hash": hashear_otp(codigo),
        },
    ).mappings().first()

    if codigo_row is None:
        raise OtpInvalido

    if codigo_row["utilizado"] or not codigo_row["vigente"]:
        raise OtpExpiradoOUsado

    # Misma transacción: crear el ticket y marcar el OTP como utilizado. El
    # ticket se inserta vía ORM para refrescar `id_ticket`/`fecha_creacion`
    # (asignados por la BD). Un único commit confirma ambas operaciones.
    ticket = Ticket(
        id_silla=silla.id_silla,
        asunto=asunto,
        descripcion=descripcion,
        estado="ABIERTO",
    )
    db.add(ticket)

    db.execute(
        text(
            f"UPDATE {schema}.codigo_verificacion "
            "SET utilizado = true WHERE id_codigo = :id_codigo"
        ),
        {"id_codigo": codigo_row["id_codigo"]},
    )

    db.commit()
    db.refresh(ticket)

    return ticket
