"""Lógica de negocio del listado de empleados por empresa (Fase 4, R9).

El router (`app/routers/empleados.py`) solo traduce HTTP y aplica RBAC; aquí vive
la consulta parametrizada con `text()` sobre el esquema configurado.

El alcance multiempresa se decide por rol (como `inventario_export_service` y
`permisos_service`): los roles internos (`COMERCIAL_MANSILLAS`, `TECNICO`) listan
los empleados de cualquier empresa; el `ADMIN_CLIENTE` solo los de su propia
empresa. El router aplica el aislamiento antes de llamar aquí; el service filtra
por `id_empresa` con orden determinista.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings


def listar_empleados(db: Session, *, id_empresa: int) -> list[dict]:
    """Devuelve los empleados de `id_empresa`, ordenados por `id_empleado`.

    Consulta parametrizada con `text()` filtrando por `id_empresa`. Si la empresa
    no existe (o no tiene empleados), devuelve una lista vacía.
    """
    schema = settings.db_schema

    filas = db.execute(
        text(
            f"""
            SELECT id_empleado, id_empresa, id_sede, id_departamento,
                   nombre, documento, correo, cargo, activo
            FROM {schema}.empleado
            WHERE id_empresa = :id_empresa
            ORDER BY id_empleado
            """
        ),
        {"id_empresa": id_empresa},
    ).mappings().all()

    return [dict(fila) for fila in filas]
