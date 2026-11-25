from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Usuario, Visita
from app.security import decode_access_token, hash_token

Rol = Literal["COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE", "EMPLEADO_CLIENTE"]

ROLES: tuple[Rol, ...] = (
    "COMERCIAL_MANSILLAS",
    "TECNICO",
    "ADMIN_CLIENTE",
    "EMPLEADO_CLIENTE",
)

NO_AUTENTICADO = {"WWW-Authenticate": "Bearer"}


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated principal resolved for the current request."""

    id: int
    rol: str
    empresa_id: int | None


def _usuario_activo(db: Session, id_usuario: int) -> Usuario:
    usuario = db.get(Usuario, id_usuario)
    if usuario is None or not usuario.activo:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Usuario no encontrado",
            headers=NO_AUTENTICADO,
        )
    return usuario


def _token_bearer(authorization: str) -> str:
    partes = authorization.split(" ", 1)
    token = partes[1].strip() if len(partes) == 2 else ""
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token de acceso requerido",
            headers=NO_AUTENTICADO,
        )
    return token


def _cerrar_sesion(db: Session, id_sesion: int) -> None:
    db.execute(
        text("UPDATE sesion_usuario SET fecha_cierre = now() WHERE id_sesion = :id"),
        {"id": id_sesion},
    )
    db.commit()


def _resolver_sesion(db: Session, token: str) -> CurrentUser:
    """Validate a signed token against `sesion_usuario` (HU-21 + HU-25).

    Expiry and the inactivity window are evaluated in SQL so the comparison uses
    the same time zone conversion the row was written with.
    """
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sesión expirada",
            headers=NO_AUTENTICADO,
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido",
            headers=NO_AUTENTICADO,
        ) from None

    fila = db.execute(
        text(
            """
            SELECT id_sesion,
                   (fecha_expiracion <= now()) AS expirada,
                   (ultima_actividad <= now() - (:inactividad * interval '1 minute')) AS inactiva
            FROM sesion_usuario
            WHERE token_hash = :token_hash
              AND fecha_cierre IS NULL
            """
        ),
        {
            "token_hash": hash_token(token),
            "inactividad": settings.session_inactivity_minutes,
        },
    ).mappings().first()

    if fila is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sesión inválida o cerrada",
            headers=NO_AUTENTICADO,
        )

    if fila["expirada"] or fila["inactiva"]:
        _cerrar_sesion(db, fila["id_sesion"])
        motivo = (
            "Sesión expirada" if fila["expirada"] else "Sesión cerrada por inactividad"
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            motivo,
            headers=NO_AUTENTICADO,
        )

    db.execute(
        text("UPDATE sesion_usuario SET ultima_actividad = now() WHERE id_sesion = :id"),
        {"id": fila["id_sesion"]},
    )
    db.commit()

    try:
        id_usuario = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido",
            headers=NO_AUTENTICADO,
        ) from None

    usuario = _usuario_activo(db, id_usuario)
    return CurrentUser(
        id=usuario.id_usuario,
        rol=usuario.rol,
        empresa_id=usuario.id_empresa,
    )


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    x_dev_user_id: Annotated[int | None, Header(alias="X-Dev-User-Id")] = None,
) -> CurrentUser:
    """Resolve the current user from the session token (HU-21).

    `Authorization: Bearer <jwt>` is always honoured. Outside production a
    development stub is also accepted (`X-Dev-User-Id` header or `DEV_USER_ID`)
    so CLI scripts and tests can act as a user without logging in; the role and
    empresa always come from the `usuario` row, never from the request.
    """
    if authorization:
        return _resolver_sesion(db, _token_bearer(authorization))

    if settings.is_production:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token de acceso requerido",
            headers=NO_AUTENTICADO,
        )

    id_usuario = x_dev_user_id if x_dev_user_id is not None else settings.dev_user_id
    if id_usuario is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Falta Authorization: Bearer o el identificador de desarrollo X-Dev-User-Id",
            headers=NO_AUTENTICADO,
        )

    usuario = _usuario_activo(db, id_usuario)
    return CurrentUser(
        id=usuario.id_usuario,
        rol=usuario.rol,
        empresa_id=usuario.id_empresa,
    )


def require_role(*roles: str) -> Callable[..., CurrentUser]:
    """Build a dependency that only lets the given role literals through."""

    def dependency(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if user.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Rol no autorizado")
        return user

    return dependency


ComercialUser = Annotated[CurrentUser, Depends(require_role("COMERCIAL_MANSILLAS"))]


def require_tecnico_owns_visita(user: CurrentUser, visita: Visita) -> None:
    """Allow the technician only when the visit is assigned to them."""
    if visita.id_tecnico != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "No autorizado para esta visita",
        )
