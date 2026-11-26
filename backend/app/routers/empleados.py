"""Router del listado de empleados por empresa (Fase 4, R9).

Solo traduce HTTP y aplica RBAC; la consulta parametrizada vive en
`empleados_service`. Ruta: `GET /empresas/{id_empresa}/empleados`.

Mismo RBAC y aislamiento que `routers/sedes.py`: los roles internos
(`COMERCIAL_MANSILLAS`, `TECNICO`) listan los empleados de cualquier empresa; el
`ADMIN_CLIENTE` solo los de su propia empresa; cualquier otro rol recibe 403.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import CurrentUser, require_role
from app.routers.sedes import autorizar_empresa
from app.schemas import EmpleadoOut
from app.services import empleados_service

router = APIRouter(prefix="/empresas", tags=["empleados"])

CatalogoUser = Annotated[
    CurrentUser,
    Depends(require_role("COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE")),
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
