from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Usuario, Visita

Rol = Literal["COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE", "EMPLEADO_CLIENTE"]

ROLES: tuple[Rol, ...] = (
    "COMERCIAL_MANSILLAS",
    "TECNICO",
    "ADMIN_CLIENTE",
    "EMPLEADO_CLIENTE",
)


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated principal resolved for the current request."""

    id: int
    rol: str
    empresa_id: int | None


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    x_dev_user_id: Annotated[int | None, Header(alias="X-Dev-User-Id")] = None,
) -> CurrentUser:
    """Resolve the current user.

    Authentication itself belongs to another teammate, so this module ships a
    development stub: the caller supplies a user identifier (`X-Dev-User-Id`
    header or `DEV_USER_ID`) and the role/empresa are always read from the
    `usuario` row, never from the request. In production the stub refuses to
    guess until the real resolver is wired in.
    """
    if settings.is_production:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            "La autenticación real aún no está integrada",
        )

    user_id = x_dev_user_id if x_dev_user_id is not None else settings.dev_user_id
    if user_id is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Falta el identificador de usuario de desarrollo (X-Dev-User-Id)",
        )

    usuario = db.get(Usuario, user_id)
    if usuario is None or not usuario.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no encontrado")

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
