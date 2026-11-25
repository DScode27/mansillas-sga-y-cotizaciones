"""Endpoints de autenticación (HU-21, R1).

Capa HTTP delgada: valida la entrada, llama al service y arma la respuesta.
La lógica (SQL, reglas, creación de sesión) vive en services/auth_service.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import get_current_user
from ..schemas import LoginRequest, LoginResponse, LogoutResponse, UsuarioPublico
from ..services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

# Para /auth/logout necesitamos el token en claro (revocar por su hash), además
# de exigir que la sesión sea válida vía get_current_user.
_bearer = HTTPBearer(auto_error=False)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
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


@router.get("/me", response_model=UsuarioPublico)
def me(user: UsuarioPublico = Depends(get_current_user)) -> UsuarioPublico:
    """Devuelve el usuario de la sesión actual (útil para rehidratar el cliente)."""
    return user


@router.post("/logout", response_model=LogoutResponse)
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    _user: UsuarioPublico = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    """Revoca la sesión actual (marca `fecha_cierre`).

    Exige sesión válida (get_current_user responde 401 si no lo es). Tras esto,
    cualquier petición con el mismo token recibirá 401.
    """
    auth_service.logout(db, credentials.credentials)
    return LogoutResponse()
