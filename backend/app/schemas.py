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


# --- Catálogo organizacional: alta de empresa, sede y departamento ---------

class EmpresaCreate(BaseModel):
    """Datos para dar de alta una empresa cliente.

    `nombre` y `nit` son obligatorios (el `nit` es UNIQUE en el SQL; el service
    traduce su violación a un 409). `correo` y `telefono` son opcionales, igual
    que en la tabla `empresa`. `permiso_qr` y `activa` no se reciben: los fija el
    SQL con sus valores por defecto.
    """

    nombre: str = Field(min_length=1, max_length=150)
    nit: str = Field(min_length=1, max_length=30)
    correo: str | None = Field(default=None, max_length=150)
    telefono: str | None = Field(default=None, max_length=30)


class EmpresaOut(BaseModel):
    """Empresa cliente devuelta por el listado y el alta.

    Expone todas las columnas de la tabla `empresa`, incluidas `permiso_qr` y
    `activa` que fija el SQL por defecto, para que el frontend pueda mostrarlas.
    """

    id_empresa: int
    nombre: str
    nit: str
    correo: str | None = None
    telefono: str | None = None
    permiso_qr: int
    activa: bool


class SedeCreate(BaseModel):
    """Datos para registrar una sede dentro de una empresa.

    La empresa dueña llega por la ruta (`POST /empresas/{id_empresa}/sedes`), no
    en el cuerpo. `nombre` es obligatorio y único por empresa en el SQL
    (`UNIQUE (id_empresa, nombre)`; el service lo traduce a 409); `direccion` y
    `ciudad` son opcionales.
    """

    nombre: str = Field(min_length=1, max_length=150)
    direccion: str | None = Field(default=None, max_length=250)
    ciudad: str | None = Field(default=None, max_length=100)


class DepartamentoCreate(BaseModel):
    """Datos para registrar un departamento (área) dentro de una sede.

    La sede (y, a través de ella, la empresa) llega por la ruta
    (`POST /sedes/{id_sede}/departamentos`), no en el cuerpo: el cliente no
    digita identificadores. `nombre` es obligatorio y único por sede en el SQL
    (`UNIQUE (id_empresa, id_sede, nombre)`; el service lo traduce a 409).
    """

    nombre: str = Field(min_length=1, max_length=120)


# --- Catálogos de listado: sedes, departamentos, empleados (Fase 4, R9) -----

class SedeOut(BaseModel):
    """Sede de una empresa (listado de solo lectura).

    Campos directos de la tabla `sede`; `direccion` y `ciudad` son opcionales
    en el SQL, por eso se admiten nulos.
    """

    id_sede: int
    id_empresa: int
    nombre: str
    direccion: str | None = None
    ciudad: str | None = None


class DepartamentoOut(BaseModel):
    """Departamento (área) de una sede dentro de una empresa.

    El departamento cuelga de una sede (FK compuesta `(id_empresa, id_sede)`),
    por eso se devuelven ambos identificadores de contexto.
    """

    id_departamento: int
    id_empresa: int
    id_sede: int
    nombre: str


class EmpleadoOut(BaseModel):
    """Empleado del cliente (listado de solo lectura).

    No es una vista pública: el aislamiento por empresa (roles internos o el
    ADMIN_CLIENTE de la propia empresa) ya restringe quién ve `documento` y
    `correo`, que son opcionales en el SQL.
    """

    id_empleado: int
    id_empresa: int
    id_sede: int
    id_departamento: int
    nombre: str
    documento: str | None = None
    correo: str | None = None
    cargo: str
    activo: bool
