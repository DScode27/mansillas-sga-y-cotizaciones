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
