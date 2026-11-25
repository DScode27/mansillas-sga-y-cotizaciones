"""Dependencias transversales de FastAPI para autenticación y autorización.

DEUDA TÉCNICA (unificar con el compañero): existe un segundo módulo de RBAC,
`app/deps.py`, que resuelve la sesión y los roles de forma independiente para los
routers de negocio (visitas, sillas, qr, accesos). Este módulo (`dependencies.py`)
lo usan los routers de seguridad (auth, usuarios). Ambos validan lo mismo (JWT,
sesión abierta, expiración, inactividad) pero con contratos distintos
(`UsuarioPublico` Pydantic aquí vs. `CurrentUser` dataclass en `deps.py`) y con
diferencias de comportamiento (p. ej. `deps.py` cierra la sesión en BD al detectar
expiración). Unificar en un solo módulo exige reescribir las firmas de los 6
routers y acordar el comportamiento; debe hacerse junto al dueño de `deps.py`.

- `get_current_user` (HU-25, R2): resuelve la sesión del header `Authorization:
  Bearer <token>`, valida el JWT, comprueba que la sesión no esté cerrada ni
  expirada por inactividad y refresca `ultima_actividad`. Devuelve el usuario.
- `require_roles(...)` (HU-22, R3): control de acceso por rol. Exige que el
  usuario autenticado tenga uno de los roles permitidos; si no, responde 403.
- `ensure_same_empresa(...)` (HU-23, R4): aislamiento por empresa. Verifica que
  el usuario externo (`ADMIN_CLIENTE`/`EMPLEADO_CLIENTE`) solo acceda a recursos
  de su propia empresa; el personal interno de Mansillas no tiene esa frontera.

Viven aparte de routers y services porque las consumen varios routers.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .schemas import UsuarioPublico
from .services import auth_service

# Roles internos de Mansillas: no están atados a una empresa cliente
# (id_empresa IS NULL en el SQL), así que ven todas las empresas.
INTERNAL_ROLES = ("COMERCIAL_MANSILLAS", "TECNICO")

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
    db: Session = Depends(get_db),
) -> UsuarioPublico:
    """Usuario autenticado de la petición. Responde 401 si la sesión no vale."""
    if credentials is None or not credentials.credentials:
        raise _UNAUTHORIZED

    try:
        user = auth_service.resolve_session(db, credentials.credentials)
    except auth_service.InvalidSession:
        raise _UNAUTHORIZED

    return UsuarioPublico(**user)


def require_roles(*roles: str) -> Callable[..., UsuarioPublico]:
    """Fábrica de dependencias que exige uno de `roles` (RBAC, HU-22, R3).

    Construye sobre `get_current_user`: primero asegura sesión válida (401 si no)
    y luego comprueba el rol (403 si el usuario está autenticado pero su rol no
    está permitido para el endpoint). Devuelve el usuario para que el endpoint lo
    reutilice sin volver a resolverlo.

    Uso:
        @router.get("/usuarios")
        def listar(user = Depends(require_roles("COMERCIAL_MANSILLAS"))):
            ...
    """
    allowed = frozenset(roles)

    def _dependency(
        user: UsuarioPublico = Depends(get_current_user),
    ) -> UsuarioPublico:
        if user.rol not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu rol no tiene permiso para esta acción",
            )
        return user

    return _dependency


def ensure_same_empresa(user: UsuarioPublico, id_empresa_recurso: int) -> None:
    """Aislamiento por empresa (HU-23, R4): el externo solo accede a lo suyo.

    El personal interno de Mansillas (`COMERCIAL_MANSILLAS`, `TECNICO`) no está
    atado a una empresa y puede operar sobre cualquiera. Un usuario externo
    (`ADMIN_CLIENTE`, `EMPLEADO_CLIENTE`) solo puede tocar recursos de su propia
    empresa; en otro caso se responde 403.

    Los endpoints llaman a esto tras cargar el `id_empresa` del recurso que se va
    a leer o modificar. Es la barrera a nivel de aplicación; las FK compuestas
    del SQL impiden además cruces de datos entre empresas.
    """
    if user.rol in INTERNAL_ROLES:
        return
    if user.id_empresa is None or user.id_empresa != id_empresa_recurso:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes acceder a recursos de otra empresa",
        )
