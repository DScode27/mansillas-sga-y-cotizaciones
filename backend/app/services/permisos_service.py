"""Lógica de negocio de permisos de QR por empresa (HU-18, RN-5).

El router (`app/routers/qr.py`) solo traduce HTTP y aplica el RBAC
(`require_role("ADMIN_CLIENTE")` + `user.empresa_id == id_empresa`); aquí viven
la lectura y la actualización de `empresa.permiso_qr`.

`permiso_qr` solo admite los valores 1, 2 o 3 (RN-5): se valida contra
`PERMISOS_VALIDOS` dentro del service, no con `Literal` de Pydantic. Un valor
fuera del conjunto lanza `PermisoInvalido`, que el router traduce a 422 —
consistente con el CHECK de la base de datos como última barrera.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings

# Valores permitidos del CHECK de `empresa.permiso_qr` (RN-5).
PERMISOS_VALIDOS = (1, 2, 3)


class PermisoInvalido(Exception):
    """El permiso no pertenece a `PERMISOS_VALIDOS` (→ 422)."""


def obtener_permiso_qr(db: Session, *, id_empresa: int) -> int:
    """Devuelve `empresa.permiso_qr` para la empresa indicada.

    Lee el entero con un SELECT parametrizado sobre el esquema configurado.
    """
    schema = settings.db_schema

    row = db.execute(
        text(
            f"SELECT permiso_qr FROM {schema}.empresa "
            "WHERE id_empresa = :id_empresa"
        ),
        {"id_empresa": id_empresa},
    ).mappings().first()

    return int(row["permiso_qr"])


def actualizar_permiso_qr(db: Session, *, id_empresa: int, permiso: int) -> int:
    """Valida el permiso (1/2/3), lo persiste y devuelve el valor guardado.

    Un `permiso` fuera de `PERMISOS_VALIDOS` lanza `PermisoInvalido` sin tocar la
    BD. En caso válido hace `UPDATE empresa SET permiso_qr` filtrando por
    `id_empresa` y confirma con `db.commit()` explícito (`get_db` revierte al
    cerrar la petición).
    Raises PermisoInvalido.
    """
    if permiso not in PERMISOS_VALIDOS:
        raise PermisoInvalido("permiso_qr debe ser 1, 2 o 3")

    schema = settings.db_schema

    db.execute(
        text(
            f"UPDATE {schema}.empresa SET permiso_qr = :permiso "
            "WHERE id_empresa = :id_empresa"
        ),
        {"permiso": permiso, "id_empresa": id_empresa},
    )
    # `get_db` entrega una Session que revierte al cerrar la petición: la
    # actualización debe confirmarse explícitamente.
    db.commit()

    return permiso
