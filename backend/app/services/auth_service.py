"""Lógica de negocio de autenticación (HU-21, R1).

El router solo traduce HTTP; aquí viven las consultas SQL y las reglas de login
(verificar contraseña, usuario activo, rol habilitado y crear la sesión).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..security import (
    create_access_token,
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
