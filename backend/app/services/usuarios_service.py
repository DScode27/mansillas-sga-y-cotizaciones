"""Lógica de negocio de gestión de usuarios (HU-20, R5).

El router solo traduce HTTP; aquí viven las consultas SQL y las reglas de alta y
asignación de rol: hashear la contraseña, exigir `id_empresa` según el rol
(obligatoria para roles de cliente, nula para los internos — regla del SQL) y
respetar el correo único.

El RBAC (solo `COMERCIAL_MANSILLAS` entra) se impone en la capa de dependencias
(require_roles) del router, no aquí.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..security import hash_password

# Roles externos: pertenecen a una empresa cliente (id_empresa obligatorio).
CLIENT_ROLES = ("ADMIN_CLIENTE", "EMPLEADO_CLIENTE")
# Roles internos de Mansillas: sin empresa (id_empresa debe ser nulo).
INTERNAL_ROLES = ("COMERCIAL_MANSILLAS", "TECNICO")


class EmpresaRuleError(Exception):
    """La combinación rol/id_empresa viola la regla del SQL (→ 400).

    - Rol de cliente sin `id_empresa`.
    - Rol interno con `id_empresa`.
    """


class CorreoEnUso(Exception):
    """Ya existe un usuario con ese correo (correo es UNIQUE) (→ 409)."""


class UsuarioNoEncontrado(Exception):
    """No existe el usuario indicado (→ 404)."""


def _normalize_empresa(rol: str, id_empresa: int | None) -> int | None:
    """Valida y normaliza `id_empresa` según el rol (regla del SQL).

    Devuelve el `id_empresa` a guardar (int para clientes, None para internos).
    Lanza EmpresaRuleError si la combinación no es válida.
    """
    if rol in CLIENT_ROLES:
        if id_empresa is None:
            raise EmpresaRuleError(
                "Los roles de cliente requieren id_empresa"
            )
        return id_empresa
    # Rol interno: id_empresa debe ser nulo (lo forzamos aunque venga un valor).
    if id_empresa is not None:
        raise EmpresaRuleError(
            "Los roles internos no pueden tener id_empresa"
        )
    return None


def listar_usuarios(db: Connection) -> list[dict]:
    """Lista todos los usuarios (datos públicos, sin password_hash).

    Para `COMERCIAL_MANSILLAS` (interno), que administra todas las empresas; por
    eso no se filtra por empresa.
    """
    rows = db.execute(
        text(
            """
            SELECT id_usuario, nombre, correo, rol, id_empresa, activo
            FROM usuario
            ORDER BY id_usuario
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def crear_usuario(
    db: Connection,
    *,
    nombre: str,
    correo: str,
    password: str,
    rol: str,
    id_empresa: int | None,
) -> dict:
    """Crea un usuario con la contraseña hasheada y devuelve sus datos públicos.

    Aplica la regla rol/id_empresa y rechaza correos duplicados.
    Raises EmpresaRuleError, CorreoEnUso.
    """
    empresa = _normalize_empresa(rol, id_empresa)

    existe = db.execute(
        text("SELECT 1 FROM usuario WHERE correo = :correo"),
        {"correo": correo},
    ).first()
    if existe is not None:
        raise CorreoEnUso

    row = db.execute(
        text(
            """
            INSERT INTO usuario (id_empresa, nombre, correo, password_hash, rol, activo)
            VALUES (:id_empresa, :nombre, :correo, :password_hash, :rol, TRUE)
            RETURNING id_usuario, nombre, correo, rol, id_empresa, activo
            """
        ),
        {
            "id_empresa": empresa,
            "nombre": nombre,
            "correo": correo,
            "password_hash": hash_password(password),
            "rol": rol,
        },
    ).mappings().first()

    return dict(row)


def asignar_rol(
    db: Connection,
    *,
    id_usuario: int,
    rol: str,
    id_empresa: int | None,
) -> dict:
    """Cambia el rol (y la empresa asociada) de un usuario existente.

    Aplica la misma regla rol/id_empresa que el alta, porque cambiar a un rol de
    cliente exige empresa y cambiar a uno interno la anula.
    Raises UsuarioNoEncontrado, EmpresaRuleError.
    """
    empresa = _normalize_empresa(rol, id_empresa)

    row = db.execute(
        text(
            """
            UPDATE usuario
            SET rol = :rol, id_empresa = :id_empresa
            WHERE id_usuario = :id_usuario
            RETURNING id_usuario, nombre, correo, rol, id_empresa, activo
            """
        ),
        {"rol": rol, "id_empresa": empresa, "id_usuario": id_usuario},
    ).mappings().first()

    if row is None:
        raise UsuarioNoEncontrado

    return dict(row)
