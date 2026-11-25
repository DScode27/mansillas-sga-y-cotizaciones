"""Utilidades de seguridad: hash de contraseñas, JWT y hash del token de sesión.

- Contraseñas: bcrypt (el paquete `bcrypt`), hash guardado en usuario.password_hash.
- Sesión: se emite un JWT y se guarda en `sesion_usuario` solo el SHA-256 del
  token (token_hash), para poder revocarlo sin almacenar el token en claro.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings


# --- Contraseñas -----------------------------------------------------------

def hash_password(plain: str) -> str:
    """Devuelve el hash bcrypt de una contraseña, listo para guardar como TEXT."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str | None) -> bool:
    """Comprueba la contraseña contra el hash guardado. Falso si no hay hash."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Hash con formato inválido (p. ej. texto plano heredado): no autentica.
        return False


# --- JWT y token de sesión -------------------------------------------------

def create_access_token(
    *,
    id_usuario: int,
    rol: str,
    expires_at: datetime,
) -> str:
    """Emite un JWT firmado con la expiración absoluta de la sesión.

    `jti` es aleatorio para que dos tokens del mismo usuario tengan hashes
    distintos en `sesion_usuario` (token_hash es UNIQUE).
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(id_usuario),
        "rol": rol,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": hashlib.sha256(f"{id_usuario}:{now.timestamp()}".encode()).hexdigest()[:32],
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decodifica y valida la firma y expiración del JWT. Lanza si es inválido."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def hash_token(token: str) -> str:
    """SHA-256 del token; es lo que se guarda/busca en sesion_usuario.token_hash."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(now: datetime | None = None) -> datetime:
    """Expiración absoluta de la sesión (vida máxima configurable, HU-25)."""
    settings = get_settings()
    base = now or datetime.now(timezone.utc)
    return base + timedelta(hours=settings.session_max_hours)
