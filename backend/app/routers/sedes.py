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
from app.schemas import SedeCreate, SedeOut
from app.services import sedes_service

router = APIRouter(prefix="/empresas", tags=["sedes"])

# Roles que pueden registrar sedes: el comercial (cualquier empresa) y el
# ADMIN_CLIENTE (solo la suya; lo acota `autorizar_empresa`).
AltaSedeUser = Annotated[
    CurrentUser,
    Depends(require_role("COMERCIAL_MANSILLAS", "ADMIN_CLIENTE")),
]

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


@router.post(
    "/{id_empresa}/sedes",
    response_model=SedeOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_sede(
    id_empresa: int,
    payload: SedeCreate,
    db: Annotated[Session, Depends(get_db)],
    user: AltaSedeUser,
) -> dict:
    """Registra una sede en `id_empresa` dentro del alcance del rol.

    El comercial crea en cualquier empresa; el `ADMIN_CLIENTE` solo en la suya
    (403 en otro caso). Una empresa inexistente responde 404 y un nombre ya
    usado en esa empresa, 409 (`UNIQUE (id_empresa, nombre)`).
    """
    autorizar_empresa(user, id_empresa)
    try:
        return sedes_service.crear_sede(
            db,
            id_empresa=id_empresa,
            nombre=payload.nombre,
            direccion=payload.direccion,
            ciudad=payload.ciudad,
        )
    except sedes_service.EmpresaNoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado") from None
    except sedes_service.NombreSedeEnUso:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ya existe una sede con ese nombre en la empresa",
        ) from None
