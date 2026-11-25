"""Lógica de negocio de autenticación (HU-21, R1).

El router solo traduce HTTP; aquí viven las consultas SQL y las reglas de login
(verificar contraseña, usuario activo, rol habilitado y crear la sesión).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..security import (
    create_access_token,
    decode_access_token,
    hash_token,
    session_expiry,
    verify_password,
)

# Roles que pueden iniciar sesión por correo/contraseña (EMPLEADO_CLIENTE usa OTP).
LOGIN_ROLES = ("COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE")


class InvalidCredentials(Exception):
    """Credenciales inválidas, usuario inactivo o rol no habilitado para login.

    Un único error para todos los casos: el router responde 401 sin revelar la
    causa concreta.
    """


class InvalidSession(Exception):
    """Token/sesión no válido: ausente, mal firmado, cerrado, expirado o inactivo.

    El router lo traduce a 401. No distingue la causa concreta hacia el cliente.
    """


def authenticate(db: Session, correo: str, password: str) -> dict:
    """Valida credenciales, crea la sesión y devuelve usuario + token.

    Returns un dict con: access_token, id_usuario, nombre, correo, rol, id_empresa.
    Raises InvalidCredentials si el login no procede.
    """
    row = db.execute(
        text(
            """
            SELECT id_usuario, nombre, correo, password_hash, rol, activo, id_empresa
            FROM usuario
            WHERE correo = :correo
            """
        ),
        {"correo": correo},
    ).mappings().first()

    # Verificamos la contraseña aunque el usuario no exista, para no dar pistas
    # por diferencia de tiempos (correo inexistente vs. contraseña errónea).
    stored_hash = row["password_hash"] if row else None
    password_ok = verify_password(password, stored_hash)

    if row is None or not password_ok:
        raise InvalidCredentials
    if not row["activo"]:
        raise InvalidCredentials
    if row["rol"] not in LOGIN_ROLES:
        raise InvalidCredentials

    now = datetime.now(timezone.utc)
    expires_at = session_expiry(now)
    token = create_access_token(
        id_usuario=row["id_usuario"],
        rol=row["rol"],
        expires_at=expires_at,
    )

    _create_session(db, row["id_usuario"], token, now, expires_at)

    # The session row must survive the request: `get_db` yields an ORM Session
    # that is closed (and rolled back) when the request ends.
    db.commit()

    return {
        "access_token": token,
        "id_usuario": row["id_usuario"],
        "nombre": row["nombre"],
        "correo": row["correo"],
        "rol": row["rol"],
        "id_empresa": row["id_empresa"],
    }


def resolve_session(db: Session, token: str) -> dict:
    """Valida el token y la sesión asociada; refresca `ultima_actividad`.

    Comprobaciones (en orden): firma/expiración del JWT, que exista una sesión
    con ese `token_hash`, que no esté cerrada (`fecha_cierre`), que no haya
    pasado su expiración absoluta y que no lleve más de los minutos de
    inactividad configurados sin actividad. Si todo pasa, actualiza
    `ultima_actividad` y devuelve el usuario.

    Returns un dict con: id_usuario, nombre, correo, rol, id_empresa.
    Raises InvalidSession en cualquier fallo.
    """
    if not token:
        raise InvalidSession

    # 1. Firma y expiración del propio JWT.
    try:
        decode_access_token(token)
    except Exception as exc:  # jwt.PyJWTError y variantes
        raise InvalidSession from exc

    now = datetime.now(timezone.utc)

    # 2. La sesión debe existir (por hash), unida al usuario para devolverlo.
    row = db.execute(
        text(
            """
            SELECT s.id_sesion, s.ultima_actividad, s.fecha_expiracion, s.fecha_cierre,
                   u.id_usuario, u.nombre, u.correo, u.rol, u.activo, u.id_empresa
            FROM sesion_usuario s
            JOIN usuario u ON u.id_usuario = s.id_usuario
            WHERE s.token_hash = :token_hash
            """
        ),
        {"token_hash": hash_token(token)},
    ).mappings().first()

    if row is None:
        raise InvalidSession
    # 3. Logout previo: sesión revocada.
    if row["fecha_cierre"] is not None:
        raise InvalidSession
    # 4. Usuario desactivado tras iniciar sesión.
    if not row["activo"]:
        raise InvalidSession

    # 5. Expiración absoluta de la sesión.
    if _is_past(row["fecha_expiracion"], now):
        raise InvalidSession

    # 6. Inactividad: minutos configurables desde la última actividad.
    settings = get_settings()
    inactivity_limit = timedelta(minutes=settings.session_inactivity_minutes)
    last_activity = _as_utc(row["ultima_actividad"])
    if now - last_activity > inactivity_limit:
        raise InvalidSession

    # Sesión válida: registramos la actividad de esta petición.
    db.execute(
        text(
            """
            UPDATE sesion_usuario
            SET ultima_actividad = :now
            WHERE id_sesion = :id_sesion
            """
        ),
        {"now": now, "id_sesion": row["id_sesion"]},
    )
    # `get_db` entrega una Session ORM que hace rollback al cerrar la petición:
    # el refresco de actividad debe confirmarse explícitamente.
    db.commit()

    return {
        "id_usuario": row["id_usuario"],
        "nombre": row["nombre"],
        "correo": row["correo"],
        "rol": row["rol"],
        "id_empresa": row["id_empresa"],
    }


def logout(db: Session, token: str) -> None:
    """Revoca la sesión del token marcando `fecha_cierre` (idempotente).

    No lanza si el token no corresponde a ninguna sesión abierta: el efecto
    deseado (no poder volver a usarlo) ya se cumple. Solo cierra sesiones aún
    abiertas (`fecha_cierre IS NULL`).
    """
    db.execute(
        text(
            """
            UPDATE sesion_usuario
            SET fecha_cierre = :now
            WHERE token_hash = :token_hash
              AND fecha_cierre IS NULL
            """
        ),
        {"now": datetime.now(timezone.utc), "token_hash": hash_token(token)},
    )
    db.commit()


def _as_utc(value: datetime | str) -> datetime:
    """Normaliza un timestamp de la BD a datetime UTC *aware* para compararlo.

    Postgres (psycopg) devuelve `datetime`; en las pruebas con SQLite llega como
    texto ISO. Los timestamps se guardan en UTC (ver login), así que a los
    naive les asignamos UTC.
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_past(value: datetime | str, now: datetime) -> bool:
    """True si el timestamp de la BD ya quedó atrás respecto a `now` (UTC aware)."""
    return _as_utc(value) < now


def _create_session(
    db: Session,
    id_usuario: int,
    token: str,
    now: datetime,
    expires_at: datetime,
) -> None:
    """Guarda solo el hash del token en sesion_usuario (nunca el token en claro)."""
    db.execute(
        text(
            """
            INSERT INTO sesion_usuario
                (id_usuario, token_hash, fecha_inicio, ultima_actividad, fecha_expiracion)
            VALUES
                (:id_usuario, :token_hash, :fecha_inicio, :ultima_actividad, :fecha_expiracion)
            """
        ),
        {
            "id_usuario": id_usuario,
            "token_hash": hash_token(token),
            "fecha_inicio": now,
            "ultima_actividad": now,
            "fecha_expiracion": expires_at,
        },
    )
