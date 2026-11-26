"""Lógica de negocio del catálogo de empresas cliente.

El router (`app/routers/empresas.py`) solo traduce HTTP y aplica RBAC; aquí viven
las consultas parametrizadas con `text()` sobre el esquema configurado, igual que
`sedes_service`/`empleados_service`.

El listado devuelve todas las empresas ordenadas; el alta inserta una empresa
nueva respetando el `nit` único del SQL (`UNIQUE (nit)`): se precomprueba y, si
ya existe, se lanza `NitEnUso` para que el router responda 409 (mismo patrón que
`usuarios_service.CorreoEnUso`).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings


class NitEnUso(Exception):
    """Ya existe una empresa con ese NIT (`nit` es UNIQUE) (→ 409)."""


def listar_empresas(db: Session) -> list[dict]:
    """Devuelve todas las empresas, ordenadas por `id_empresa`.

    El alcance por rol (los internos ven todas; el `ADMIN_CLIENTE` solo la suya)
    lo decide el router; el service solo lista con orden determinista.
    """
    schema = settings.db_schema

    filas = db.execute(
        text(
            f"""
            SELECT id_empresa, nombre, nit, correo, telefono, permiso_qr, activa
            FROM {schema}.empresa
            ORDER BY id_empresa
            """
        )
    ).mappings().all()

    return [dict(fila) for fila in filas]


def obtener_empresa(db: Session, *, id_empresa: int) -> dict | None:
    """Devuelve una empresa por su id, o `None` si no existe.

    Permite al router materializar la empresa de un `ADMIN_CLIENTE` (que solo ve
    la suya) sin exponer un listado completo.
    """
    schema = settings.db_schema

    fila = db.execute(
        text(
            f"""
            SELECT id_empresa, nombre, nit, correo, telefono, permiso_qr, activa
            FROM {schema}.empresa
            WHERE id_empresa = :id_empresa
            """
        ),
        {"id_empresa": id_empresa},
    ).mappings().first()

    return None if fila is None else dict(fila)


def crear_empresa(
    db: Session,
    *,
    nombre: str,
    nit: str,
    correo: str | None,
    telefono: str | None,
) -> dict:
    """Crea una empresa y devuelve todas sus columnas.

    Precomprueba el `nit` único (como `usuarios_service` con el correo) y lanza
    `NitEnUso` si ya existe. `permiso_qr` y `activa` no se insertan: los fija el
    SQL con sus valores por defecto y el `RETURNING` los devuelve.
    Raises NitEnUso.
    """
    schema = settings.db_schema

    existe = db.execute(
        text(f"SELECT 1 FROM {schema}.empresa WHERE nit = :nit"),
        {"nit": nit},
    ).first()
    if existe is not None:
        raise NitEnUso

    fila = db.execute(
        text(
            f"""
            INSERT INTO {schema}.empresa (nombre, nit, correo, telefono)
            VALUES (:nombre, :nit, :correo, :telefono)
            RETURNING id_empresa, nombre, nit, correo, telefono, permiso_qr, activa
            """
        ),
        {
            "nombre": nombre,
            "nit": nit,
            "correo": correo,
            "telefono": telefono,
        },
    ).mappings().first()
    # `get_db` revierte al cerrar la petición: el alta debe confirmarse aquí.
    db.commit()

    return dict(fila)
