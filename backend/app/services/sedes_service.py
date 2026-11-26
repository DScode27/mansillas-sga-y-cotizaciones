"""Lógica de negocio del listado de sedes por empresa (Fase 4, R9).

El router (`app/routers/sedes.py`) solo traduce HTTP y aplica RBAC; aquí vive la
consulta parametrizada con `text()` sobre el esquema configurado.

El alcance multiempresa se decide por rol, igual que en el resto del backend
(`inventario_export_service`, `permisos_service`): los roles internos
(`COMERCIAL_MANSILLAS`, `TECNICO`) listan las sedes de cualquier empresa; el
`ADMIN_CLIENTE` solo las de su propia empresa. El router comprueba el
aislamiento del `ADMIN_CLIENTE` antes de llamar aquí; el service se limita a
filtrar por `id_empresa` con orden determinista.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings


class EmpresaNoEncontrada(Exception):
    """No existe la empresa indicada para colgar la sede (→ 404)."""


class NombreSedeEnUso(Exception):
    """Ya existe una sede con ese nombre en la empresa (→ 409).

    Corresponde a la restricción `UNIQUE (id_empresa, nombre)` del SQL.
    """


def listar_sedes(db: Session, *, id_empresa: int) -> list[dict]:
    """Devuelve las sedes de `id_empresa`, ordenadas por `id_sede`.

    Consulta parametrizada con `text()` filtrando por `id_empresa`. Si la empresa
    no existe (o no tiene sedes), devuelve una lista vacía.
    """
    schema = settings.db_schema

    filas = db.execute(
        text(
            f"""
            SELECT id_sede, id_empresa, nombre, direccion, ciudad
            FROM {schema}.sede
            WHERE id_empresa = :id_empresa
            ORDER BY id_sede
            """
        ),
        {"id_empresa": id_empresa},
    ).mappings().all()

    return [dict(fila) for fila in filas]


def crear_sede(
    db: Session,
    *,
    id_empresa: int,
    nombre: str,
    direccion: str | None,
    ciudad: str | None,
) -> dict:
    """Crea una sede en `id_empresa` y devuelve sus columnas (`SedeOut`).

    Valida primero que la empresa exista (`EmpresaNoEncontrada` → 404) y que el
    nombre no esté repetido en esa empresa (`NombreSedeEnUso` → 409, por la
    restricción `UNIQUE (id_empresa, nombre)`). El `id_empresa` viene de la ruta,
    nunca del cuerpo. Confirma con `db.commit()` porque `get_db` revierte al
    cerrar la petición.
    Raises EmpresaNoEncontrada, NombreSedeEnUso.
    """
    schema = settings.db_schema

    empresa = db.execute(
        text(f"SELECT 1 FROM {schema}.empresa WHERE id_empresa = :id_empresa"),
        {"id_empresa": id_empresa},
    ).first()
    if empresa is None:
        raise EmpresaNoEncontrada

    duplicada = db.execute(
        text(
            f"""
            SELECT 1 FROM {schema}.sede
            WHERE id_empresa = :id_empresa AND nombre = :nombre
            """
        ),
        {"id_empresa": id_empresa, "nombre": nombre},
    ).first()
    if duplicada is not None:
        raise NombreSedeEnUso

    fila = db.execute(
        text(
            f"""
            INSERT INTO {schema}.sede (id_empresa, nombre, direccion, ciudad)
            VALUES (:id_empresa, :nombre, :direccion, :ciudad)
            RETURNING id_sede, id_empresa, nombre, direccion, ciudad
            """
        ),
        {
            "id_empresa": id_empresa,
            "nombre": nombre,
            "direccion": direccion,
            "ciudad": ciudad,
        },
    ).mappings().first()
    db.commit()

    return dict(fila)
