"""Endpoints de autenticación (HU-21, R1).

Capa HTTP delgada: valida la entrada, llama al service y arma la respuesta.
La lógica (SQL, reglas, creación de sesión) vive en services/auth_service.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.engine import Connection

from ..db import get_db
from ..schemas import LoginRequest, LoginResponse, UsuarioPublico
from ..services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Connection = Depends(get_db)) -> LoginResponse:
    try:
        result = auth_service.authenticate(db, payload.correo, payload.password)
    except auth_service.InvalidCredentials:
        # Mensaje único para cualquier fallo: no distingue correo/contraseña.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )

    return LoginResponse(
        access_token=result["access_token"],
        usuario=UsuarioPublico(
            id_usuario=result["id_usuario"],
            nombre=result["nombre"],
            correo=result["correo"],
            rol=result["rol"],
            id_empresa=result["id_empresa"],
        ),
    )
