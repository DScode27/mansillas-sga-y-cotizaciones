"""Dependencias transversales de FastAPI para autenticación (HU-25, base de RBAC).

`get_current_user` resuelve la sesión a partir del header `Authorization:
Bearer <token>`: valida el JWT, comprueba que la sesión no esté cerrada ni
expirada por inactividad y refresca `ultima_actividad` (R2). Devuelve el usuario
autenticado para que los endpoints protegidos lo usen.

Vive aparte de los routers y services porque la consumen varios routers; la
autorización por rol (RBAC, HU-22) se construirá sobre esta dependencia en la
tarea 5.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Connection

from .db import get_db
from .schemas import UsuarioPublico
from .services import auth_service

# auto_error=False: devolvemos nuestro propio 401 uniforme cuando falta el token,
# en vez del 403 por defecto de HTTPBearer.
_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sesión inválida o expirada",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Connection = Depends(get_db),
) -> UsuarioPublico:
    """Usuario autenticado de la petición. Responde 401 si la sesión no vale."""
    if credentials is None or not credentials.credentials:
        raise _UNAUTHORIZED

    try:
        user = auth_service.resolve_session(db, credentials.credentials)
    except auth_service.InvalidSession:
        raise _UNAUTHORIZED

    return UsuarioPublico(**user)
