"""Router del listado de departamentos por sede (Fase 4, R9).

Solo traduce HTTP y aplica RBAC; las consultas parametrizadas viven en
`departamentos_service`. Ruta: `GET /sedes/{id_sede}/departamentos`.

Un departamento cuelga de una sede, así que la lista se pide por `id_sede`. El
service resuelve primero la empresa dueña de la sede: si la sede no existe, 404;
si existe, se aplica el mismo aislamiento que en sedes/empleados (los roles
internos ven cualquier empresa; el `ADMIN_CLIENTE` solo la suya).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import CurrentUser, require_role
from app.routers.sedes import autorizar_empresa
from app.schemas import DepartamentoCreate, DepartamentoOut
from app.services import departamentos_service

router = APIRouter(prefix="/sedes", tags=["departamentos"])

CatalogoUser = Annotated[
    CurrentUser,
    Depends(require_role("COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE")),
]

# Roles que pueden registrar departamentos: el comercial (cualquier empresa) y
# el ADMIN_CLIENTE (solo la suya; lo acota `autorizar_empresa`).
AltaDepartamentoUser = Annotated[
    CurrentUser,
    Depends(require_role("COMERCIAL_MANSILLAS", "ADMIN_CLIENTE")),
]


@router.get("/{id_sede}/departamentos", response_model=list[DepartamentoOut])
def listar_departamentos(
    id_sede: int,
    db: Annotated[Session, Depends(get_db)],
    user: CatalogoUser,
) -> list[dict]:
    """Lista los departamentos de `id_sede` dentro del alcance del rol.

    Resuelve la empresa dueña de la sede: una sede inexistente responde 404.
    Sobre esa empresa aplica el aislamiento (internos: cualquier empresa;
    `ADMIN_CLIENTE`: solo la suya, 403 en otro caso). Una sede sin departamentos
    devuelve 200 con lista vacía.
    """
    id_empresa = departamentos_service.empresa_de_sede(db, id_sede=id_sede)
    if id_empresa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")

    autorizar_empresa(user, id_empresa)
    return departamentos_service.listar_departamentos(db, id_sede=id_sede)


@router.post(
    "/{id_sede}/departamentos",
    response_model=DepartamentoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_departamento(
    id_sede: int,
    payload: DepartamentoCreate,
    db: Annotated[Session, Depends(get_db)],
    user: AltaDepartamentoUser,
) -> dict:
    """Registra un departamento en `id_sede` dentro del alcance del rol.

    Resuelve la empresa dueña de la sede (404 si la sede no existe) y aplica el
    aislamiento (el comercial crea en cualquier empresa; el `ADMIN_CLIENTE` solo
    en la suya, 403 en otro caso). El `id_empresa` e `id_sede` se derivan del
    path, no del cuerpo. Un nombre repetido en la sede responde 409
    (`UNIQUE (id_empresa, id_sede, nombre)`).
    """
    id_empresa = departamentos_service.empresa_de_sede(db, id_sede=id_sede)
    if id_empresa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")

    autorizar_empresa(user, id_empresa)
    try:
        return departamentos_service.crear_departamento(
            db,
            id_empresa=id_empresa,
            id_sede=id_sede,
            nombre=payload.nombre,
        )
    except departamentos_service.NombreDepartamentoEnUso:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ya existe un departamento con ese nombre en la sede",
        ) from None
