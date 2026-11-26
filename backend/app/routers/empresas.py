"""Router del catálogo de empresas cliente: listado y alta.

Solo traduce HTTP y aplica RBAC; la lógica vive en `empresas_service`. Rutas:
`GET /empresas` y `POST /empresas`.

RBAC (coherente con `routers/sedes.py` y la matriz RBAC del ERS):
- `GET /empresas`: roles internos (`COMERCIAL_MANSILLAS`, `TECNICO`) ven todas;
  el `ADMIN_CLIENTE` solo la suya; otros roles, 403.
- `POST /empresas`: solo `COMERCIAL_MANSILLAS` (gestión de empresas cliente).

El prefijo `/empresas` lo comparte con `routers/sedes.py` y `routers/empleados.py`
(que exponen las subrutas anidadas); FastAPI resuelve cada ruta por separado.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ComercialUser, CurrentUser, require_role
from app.schemas import EmpresaCreate, EmpresaOut
from app.services import empresas_service

router = APIRouter(prefix="/empresas", tags=["empresas"])

# Roles con visibilidad del catálogo de empresas; el alcance (internos: todas;
# ADMIN_CLIENTE: solo la suya) lo decide el endpoint.
CatalogoUser = Annotated[
    CurrentUser,
    Depends(require_role("COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE")),
]


@router.get("", response_model=list[EmpresaOut])
def listar_empresas(
    db: Annotated[Session, Depends(get_db)],
    user: CatalogoUser,
) -> list[dict]:
    """Lista las empresas dentro del alcance del rol.

    Roles internos ven todas; el `ADMIN_CLIENTE` recibe únicamente la suya (una
    lista con su empresa, o vacía si no se puede resolver), nunca las de otras.
    """
    if user.rol == "ADMIN_CLIENTE":
        if user.empresa_id is None:
            return []
        empresa = empresas_service.obtener_empresa(db, id_empresa=user.empresa_id)
        return [empresa] if empresa is not None else []

    return empresas_service.listar_empresas(db)


@router.post("", response_model=EmpresaOut, status_code=status.HTTP_201_CREATED)
def crear_empresa(
    payload: EmpresaCreate,
    db: Annotated[Session, Depends(get_db)],
    user: ComercialUser,
) -> dict:
    """Crea una empresa cliente (solo `COMERCIAL_MANSILLAS`).

    Un `nit` ya existente responde 409 (restricción `UNIQUE (nit)` del SQL).
    """
    try:
        return empresas_service.crear_empresa(
            db,
            nombre=payload.nombre,
            nit=payload.nit,
            correo=payload.correo,
            telefono=payload.telefono,
        )
    except empresas_service.NitEnUso:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ya existe una empresa con ese NIT",
        ) from None
