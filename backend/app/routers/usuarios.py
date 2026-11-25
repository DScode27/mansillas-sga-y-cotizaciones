"""Endpoints de gestión de usuarios (HU-20, R5).

Capa HTTP delgada: valida la entrada, llama al service y arma la respuesta. El
RBAC se aplica aquí con `require_roles("COMERCIAL_MANSILLAS")`: solo ese rol
gestiona usuarios; cualquier otro recibe 403 (y 401 si no hay sesión). La lógica
(SQL, reglas de rol/empresa, hash) vive en services/usuarios_service.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.engine import Connection

from ..db import get_db
from ..dependencies import require_roles
from ..schemas import RolUpdate, UsuarioCreate, UsuarioDetalle
from ..services import usuarios_service

# Todos los endpoints exigen rol COMERCIAL_MANSILLAS (HU-20).
router = APIRouter(
    prefix="/usuarios",
    tags=["usuarios"],
    dependencies=[Depends(require_roles("COMERCIAL_MANSILLAS"))],
)


@router.get("", response_model=list[UsuarioDetalle])
def listar(db: Connection = Depends(get_db)) -> list[UsuarioDetalle]:
    """Lista los usuarios del sistema."""
    return [UsuarioDetalle(**u) for u in usuarios_service.listar_usuarios(db)]


@router.post("", response_model=UsuarioDetalle, status_code=status.HTTP_201_CREATED)
def crear(payload: UsuarioCreate, db: Connection = Depends(get_db)) -> UsuarioDetalle:
    """Crea un usuario con la contraseña hasheada (HU-20, R5)."""
    try:
        usuario = usuarios_service.crear_usuario(
            db,
            nombre=payload.nombre,
            correo=payload.correo,
            password=payload.password,
            rol=payload.rol,
            id_empresa=payload.id_empresa,
        )
    except usuarios_service.EmpresaRuleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except usuarios_service.CorreoEnUso:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese correo",
        )

    return UsuarioDetalle(**usuario)


@router.put("/{id_usuario}/rol", response_model=UsuarioDetalle)
def asignar_rol(
    id_usuario: int,
    payload: RolUpdate,
    db: Connection = Depends(get_db),
) -> UsuarioDetalle:
    """Asigna un rol (y su empresa, si aplica) a un usuario existente."""
    try:
        usuario = usuarios_service.asignar_rol(
            db,
            id_usuario=id_usuario,
            rol=payload.rol,
            id_empresa=payload.id_empresa,
        )
    except usuarios_service.EmpresaRuleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except usuarios_service.UsuarioNoEncontrado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado",
        )

    return UsuarioDetalle(**usuario)
