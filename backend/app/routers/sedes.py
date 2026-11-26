"""Router del listado de sedes por empresa (Fase 4, R9).

Solo traduce HTTP y aplica RBAC; la consulta parametrizada vive en
`sedes_service`. Ruta: `GET /empresas/{id_empresa}/sedes`.

RBAC y aislamiento (coherentes con `routers/qr.py` y `inventario_export_service`):
los roles internos (`COMERCIAL_MANSILLAS`, `TECNICO`) listan las sedes de
cualquier empresa; el `ADMIN_CLIENTE` solo las de su propia empresa; cualquier
otro rol recibe 403.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import CurrentUser, require_role
from app.schemas import SedeOut
from app.services import sedes_service

router = APIRouter(prefix="/empresas", tags=["sedes"])

# Roles con visibilidad de catálogos; el alcance concreto lo decide el router
# (internos: cualquier empresa; ADMIN_CLIENTE: solo la suya).
CatalogoUser = Annotated[
    CurrentUser,
    Depends(require_role("COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE")),
]


def autorizar_empresa(user: CurrentUser, id_empresa: int) -> None:
    """Aislamiento multiempresa (coherente con `routers/qr.py`).

    Los roles internos ven cualquier empresa; el `ADMIN_CLIENTE` solo la suya:
    si `user.empresa_id` difiere de `id_empresa`, 403.
    """
    if user.rol == "ADMIN_CLIENTE" and user.empresa_id != id_empresa:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "No autorizado para esta empresa",
        )


@router.get("/{id_empresa}/sedes", response_model=list[SedeOut])
def listar_sedes(
    id_empresa: int,
    db: Annotated[Session, Depends(get_db)],
    user: CatalogoUser,
) -> list[dict]:
    """Lista las sedes de `id_empresa` dentro del alcance del rol.

    Internos ven cualquier empresa; el `ADMIN_CLIENTE` solo la propia (403 en
    otro caso). Una empresa sin sedes (o inexistente, para un rol interno)
    devuelve 200 con lista vacía.
    """
    autorizar_empresa(user, id_empresa)
    return sedes_service.listar_sedes(db, id_empresa=id_empresa)
