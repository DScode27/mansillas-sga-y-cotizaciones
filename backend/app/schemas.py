"""Modelos Pydantic de entrada/salida de la API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Sin EmailStr para no depender de email-validator; el login compara contra
    # el correo guardado tal cual, así que basta con un string no vacío.
    correo: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=1)


class UsuarioPublico(BaseModel):
    """Datos del usuario que es seguro devolver al cliente (sin password_hash)."""

    id_usuario: int
    nombre: str
    correo: str
    rol: str
    id_empresa: int | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioPublico


class LogoutResponse(BaseModel):
    """Confirmación simple del cierre de sesión."""

    detail: str = "Sesión cerrada"
