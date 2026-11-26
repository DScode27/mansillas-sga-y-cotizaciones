"""Modelos Pydantic de entrada/salida de la API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Los 4 roles del SQL. Se usan para validar la entrada de gestión de usuarios.
Rol = Literal["COMERCIAL_MANSILLAS", "TECNICO", "ADMIN_CLIENTE", "EMPLEADO_CLIENTE"]


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


class UsuarioDetalle(UsuarioPublico):
    """Usuario para las pantallas de gestión: añade `activo` al dato público."""

    activo: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioPublico


class LogoutResponse(BaseModel):
    """Confirmación simple del cierre de sesión."""

    detail: str = "Sesión cerrada"


# --- Gestión de usuarios (HU-20, R5) ---------------------------------------

class UsuarioCreate(BaseModel):
    """Datos para dar de alta un usuario.

    La regla de `id_empresa` según el rol (obligatoria para roles de cliente,
    nula para los internos) se valida en el service, que es quien conoce la
    regla del SQL y traduce su violación a un 400.
    """

    nombre: str = Field(min_length=1, max_length=150)
    correo: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=6, max_length=128)
    rol: Rol
    id_empresa: int | None = None


class RolUpdate(BaseModel):
    """Nuevo rol a asignar a un usuario existente."""

    rol: Rol
    # Igual que en el alta: necesario si el nuevo rol es de cliente, nulo si es
    # interno. El service valida la combinación.
    id_empresa: int | None = None

# --- Carga masiva de empleados (HU-19, R3) ---------------------------------

class ErrorFila(BaseModel):
    """Fila rechazada de una carga masiva: número de fila y motivo (R3.2).

    `fila` es 1-based sobre las filas de datos del archivo, coherente con el
    `ErrorFila` que arma el service (`carga_excel_service`). `from_attributes`
    permite adaptarlo desde el dataclass del service, también cuando viaja
    anidado dentro de `ReporteCargaOut`.
    """

    model_config = ConfigDict(from_attributes=True)

    fila: int
    motivo: str


class ReporteCargaOut(BaseModel):
    """Reporte_Resultado de una carga masiva (R3.4).

    Adapta el `ReporteResultado` (dataclass) que devuelve el service: el router
    hace `ReporteCargaOut.model_validate(resultado)` gracias a `from_attributes`,
    ya que los nombres de campo coinciden con los del dataclass.
    """

    model_config = ConfigDict(from_attributes=True)

    nombre_archivo: str
    total_procesadas: int
    total_aplicadas: int
    errores: list[ErrorFila]


# --- Inventario de sillas (HU-11, R6) --------------------------------------

class InventarioItemOut(BaseModel):
    """Ítem del Inventario: una silla con sus datos de contexto (R6.1).

    Columnas devueltas por `inventario_export_service.consultar_inventario`
    (silla unida a empresa/sede/departamento/empleado).
    """

    id_silla: int
    empresa: str
    sede: str
    departamento: str
    empleado: str
    cargo: str
    codigo_qr: str
    estado: str
