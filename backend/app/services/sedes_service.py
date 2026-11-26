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
