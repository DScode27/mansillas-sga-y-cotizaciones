"""Lógica de negocio del listado de departamentos por sede (Fase 4, R9).

El router (`app/routers/departamentos.py`) solo traduce HTTP y aplica RBAC; aquí
viven las consultas parametrizadas con `text()` sobre el esquema configurado.

Un departamento cuelga de una sede (FK compuesta `(id_empresa, id_sede)`), así
que la ruta es `GET /sedes/{id_sede}/departamentos`. El aislamiento por empresa
necesita primero resolver la empresa dueña de la sede: `empresa_de_sede` la
devuelve para que el router decida (roles internos ven cualquier empresa; el
`ADMIN_CLIENTE` solo la suya). Luego `listar_departamentos` filtra por `id_sede`
con orden determinista.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings


class NombreDepartamentoEnUso(Exception):
    """Ya existe un departamento con ese nombre en la sede (→ 409).

    Corresponde a la restricción `UNIQUE (id_empresa, id_sede, nombre)` del SQL.
    """


def empresa_de_sede(db: Session, *, id_sede: int) -> int | None:
    """Devuelve el `id_empresa` dueño de la sede, o `None` si la sede no existe.

    Permite al router aplicar el aislamiento multiempresa antes de listar: una
    sede inexistente (`None`) la traduce el router a 404, coherente con el resto
    del backend.
    """
    schema = settings.db_schema

    fila = db.execute(
        text(
            f"SELECT id_empresa FROM {schema}.sede WHERE id_sede = :id_sede"
        ),
        {"id_sede": id_sede},
    ).mappings().first()

    return None if fila is None else int(fila["id_empresa"])


def listar_departamentos(db: Session, *, id_sede: int) -> list[dict]:
    """Devuelve los departamentos de `id_sede`, ordenados por `id_departamento`.

    Consulta parametrizada con `text()` filtrando por `id_sede`. Si la sede no
    tiene departamentos, devuelve una lista vacía.
    """
    schema = settings.db_schema

    filas = db.execute(
        text(
            f"""
            SELECT id_departamento, id_empresa, id_sede, nombre
            FROM {schema}.departamento
            WHERE id_sede = :id_sede
            ORDER BY id_departamento
            """
        ),
        {"id_sede": id_sede},
    ).mappings().all()

    return [dict(fila) for fila in filas]


def crear_departamento(
    db: Session,
    *,
    id_empresa: int,
    id_sede: int,
    nombre: str,
) -> dict:
    """Crea un departamento en una sede y devuelve sus columnas (`DepartamentoOut`).

    El `id_empresa` lo resuelve el router con `empresa_de_sede` (la sede ya se
    validó allí) y el `id_sede` viene de la ruta: el cliente no digita
    identificadores. Rechaza un nombre repetido en la misma sede
    (`NombreDepartamentoEnUso` → 409, por `UNIQUE (id_empresa, id_sede, nombre)`).
    Confirma con `db.commit()` porque `get_db` revierte al cerrar la petición.
    Raises NombreDepartamentoEnUso.
    """
    schema = settings.db_schema

    duplicado = db.execute(
        text(
            f"""
            SELECT 1 FROM {schema}.departamento
            WHERE id_empresa = :id_empresa
              AND id_sede = :id_sede
              AND nombre = :nombre
            """
        ),
        {"id_empresa": id_empresa, "id_sede": id_sede, "nombre": nombre},
    ).first()
    if duplicado is not None:
        raise NombreDepartamentoEnUso

    fila = db.execute(
        text(
            f"""
            INSERT INTO {schema}.departamento (id_empresa, id_sede, nombre)
            VALUES (:id_empresa, :id_sede, :nombre)
            RETURNING id_departamento, id_empresa, id_sede, nombre
            """
        ),
        {"id_empresa": id_empresa, "id_sede": id_sede, "nombre": nombre},
    ).mappings().first()
    db.commit()

    return dict(fila)
