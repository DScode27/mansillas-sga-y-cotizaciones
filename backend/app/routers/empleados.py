"""Router del listado de empleados por empresa (Fase 4, R9).

Solo traduce HTTP y aplica RBAC; la consulta parametrizada vive en
`empleados_service`. Ruta: `GET /empresas/{id_empresa}/empleados`.

Mismo RBAC y aislamiento que `routers/sedes.py`: los roles internos
(`COMERCIAL_MANSILLAS`, `TECNICO`) listan los empleados de cualquier empresa; el
`ADMIN_CLIENTE` solo los de su propia empresa; cualquier otro rol recibe 403.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import CurrentUser, require_role
from app.routers.sedes import autorizar_empresa
from app.schemas import EmpleadoCreate, EmpleadoOut
from app.services import empleados_service

router = APIRouter(prefix="/empresas", tags=["empleados"])

CatalogoUser = Annotated[
    CurrentUser,
    Depends(require_role("COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE")),
]

# Roles que pueden dar de alta empleados: el comercial (cualquier empresa) y el
# ADMIN_CLIENTE (solo la suya; lo acota `autorizar_empresa`), igual que el alta
# de sedes y departamentos.
AltaEmpleadoUser = Annotated[
    CurrentUser,
    Depends(require_role("COMERCIAL_MANSILLAS", "ADMIN_CLIENTE")),
]


@router.get("/{id_empresa}/empleados", response_model=list[EmpleadoOut])
def listar_empleados(
    id_empresa: int,
    db: Annotated[Session, Depends(get_db)],
    user: CatalogoUser,
) -> list[dict]:
    """Lista los empleados de `id_empresa` dentro del alcance del rol.

    Internos ven cualquier empresa; el `ADMIN_CLIENTE` solo la propia (403 en
    otro caso). Una empresa sin empleados (o inexistente, para un rol interno)
    devuelve 200 con lista vacía.
    """
    autorizar_empresa(user, id_empresa)
    return empleados_service.listar_empleados(db, id_empresa=id_empresa)


@router.post(
    "/{id_empresa}/empleados",
    response_model=EmpleadoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_empleado(
    id_empresa: int,
    payload: EmpleadoCreate,
    db: Annotated[Session, Depends(get_db)],
    user: AltaEmpleadoUser,
) -> dict:
    """Registra un empleado en `id_empresa` dentro del alcance del rol.

    El comercial crea en cualquier empresa; el `ADMIN_CLIENTE` solo en la suya
    (403 en otro caso). El `id_empresa` se deriva del path, no del cuerpo. La
    sede y el departamento deben existir en la empresa y ser coherentes entre sí
    (400 si no), y un documento repetido en la empresa responde 409
    (`UNIQUE (id_empresa, documento)`).
    """
    autorizar_empresa(user, id_empresa)
    try:
        return empleados_service.crear_empleado(
            db,
            id_empresa=id_empresa,
            id_sede=payload.id_sede,
            id_departamento=payload.id_departamento,
            nombre=payload.nombre,
            cargo=payload.cargo,
            documento=payload.documento,
            correo=payload.correo,
        )
    except empleados_service.SedeNoEncontrada:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "La sede no existe en esta empresa",
        ) from None
    except empleados_service.DepartamentoNoEncontrado:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El departamento no existe en esta empresa o no pertenece a la sede",
        ) from None
    except empleados_service.DocumentoEnUso:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ya existe un empleado con ese documento en la empresa",
        ) from None
