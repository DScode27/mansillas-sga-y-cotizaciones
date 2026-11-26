"""Lógica de negocio del checklist de componentes de una silla (HU-08, HU-09).

El router (`app/routers/sillas.py`) solo traduce HTTP y aplica RBAC; aquí viven
las consultas SQL del checklist (upsert sobre `silla_componente`, lectura con
JOIN a `componente`) y la derivación de la sugerencia de cambio desde la vista
`vista_estado_mantenimiento`.

El estado de cada componente se valida como `str` contra `ESTADOS_COMPONENTE`
(no con `Literal` de Pydantic): un estado fuera del enum lanza `EstadoInvalido`,
que el router traduce a 400 — consistente con el CHECK de la base de datos como
última barrera. La `Sugerencia_Cambio` es un valor derivado: nunca se persiste.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings

# Estados válidos del CHECK de `silla_componente.estado` (RN-18). El estado se
# valida contra esta tupla dentro del service, no con `Literal` de Pydantic.
ESTADOS_COMPONENTE = ("BUENO", "MANTENIMIENTO", "DANADO", "NO_APLICA")


class ComponenteDesconocido(Exception):
    """El `id_componente` no existe en el catálogo `componente` (→ 404)."""


class EstadoInvalido(Exception):
    """El estado no pertenece a `ESTADOS_COMPONENTE` (→ 400)."""


class ChecklistIncompleto(Exception):
    """Falta `id_componente` o `estado` en un elemento del checklist (→ 400)."""


def _validar_estado(estado: str) -> str:
    """Valida un estado contra `ESTADOS_COMPONENTE` y lo devuelve sin cambios.

    Lanza `EstadoInvalido` si el estado no pertenece al enum permitido.
    """
    if estado not in ESTADOS_COMPONENTE:
        raise EstadoInvalido(f"Estado inválido: {estado!r}")
    return estado


def guardar_checklist(db: Session, id_silla: int, items: list[dict]) -> list[dict]:
    """Upsert del checklist de una silla; devuelve el checklist resultante.

    Valida todos los items antes de persistir nada (una sola transacción):
    - Falta `id_componente` o `estado` → `ChecklistIncompleto`.
    - Estado fuera de `ESTADOS_COMPONENTE` → `EstadoInvalido`.
    - `id_componente` fuera del catálogo `componente` → `ComponenteDesconocido`.

    Tras validar, hace `INSERT ... ON CONFLICT (id_silla, id_componente)
    DO UPDATE` sobre `silla_componente` (la restricción UNIQUE hace que reenviar
    el mismo componente actualice su fila en lugar de duplicarla) y confirma con
    `db.commit()` explícito solo cuando todos los items son válidos.
    Raises ChecklistIncompleto, EstadoInvalido, ComponenteDesconocido.
    """
    schema = settings.db_schema

    # 1. Validación completa antes de tocar la BD: ante cualquier error no se
    #    persiste nada (el upsert se confirma en una sola transacción al final).
    validados: list[dict] = []
    for item in items:
        id_componente = item.get("id_componente")
        estado = item.get("estado")
        if id_componente is None or estado is None:
            raise ChecklistIncompleto(
                "Cada componente requiere 'id_componente' y 'estado'"
            )
        _validar_estado(estado)

        existe = db.execute(
            text(
                f"SELECT 1 FROM {schema}.componente "
                "WHERE id_componente = :id_componente"
            ),
            {"id_componente": id_componente},
        ).first()
        if existe is None:
            raise ComponenteDesconocido(
                f"El componente {id_componente} no existe en el catálogo"
            )

        validados.append(
            {
                "id_componente": id_componente,
                "estado": estado,
                "observacion": item.get("observacion"),
            }
        )

    # 2. Upsert por componente: el ON CONFLICT sobre (id_silla, id_componente)
    #    actualiza la fila existente (Req 1.2) y guarda la observación (Req 1.3).
    for fila in validados:
        db.execute(
            text(
                f"""
                INSERT INTO {schema}.silla_componente
                    (id_silla, id_componente, estado, observacion)
                VALUES (:id_silla, :id_componente, :estado, :observacion)
                ON CONFLICT (id_silla, id_componente)
                DO UPDATE SET estado = EXCLUDED.estado,
                              observacion = EXCLUDED.observacion
                """
            ),
            {"id_silla": id_silla, **fila},
        )

    # `get_db` entrega una Session que revierte al cerrar la petición: el
    # guardado debe confirmarse explícitamente, solo tras validar todos los items.
    db.commit()

    return obtener_checklist(db, id_silla)


def obtener_checklist(db: Session, id_silla: int) -> list[dict]:
    """Lee el checklist de una silla (JOIN a `componente`, orden por id).

    Devuelve una lista de dicts con `id_componente`, `nombre`, `estado` y
    `observacion`, uniendo `silla_componente` con el catálogo `componente` y
    ordenando por `id_componente` para una salida estable (Req 4.1).
    """
    schema = settings.db_schema

    rows = db.execute(
        text(
            f"""
            SELECT c.id_componente, c.nombre, sc.estado, sc.observacion
            FROM {schema}.silla_componente AS sc
            JOIN {schema}.componente AS c
                ON c.id_componente = sc.id_componente
            WHERE sc.id_silla = :id_silla
            ORDER BY c.id_componente
            """
        ),
        {"id_silla": id_silla},
    ).mappings().all()

    return [dict(row) for row in rows]


def obtener_sugerencia(db: Session, id_silla: int) -> bool:
    """Deriva `sugerir_cambio` de `vista_estado_mantenimiento` para la silla.

    Lee el booleano directamente de la vista (valor derivado: nunca se persiste,
    Req 5.5). La vista calcula `componentes_danados / Componentes_Aplicables >
    0.70` y devuelve `FALSE` cuando no hay aplicables (Req 5.1–5.3). Si la silla
    no tiene fila en la vista, el service devuelve `False` (Req 5.4).
    """
    schema = settings.db_schema

    row = db.execute(
        text(
            f"""
            SELECT sugerir_cambio
            FROM {schema}.vista_estado_mantenimiento
            WHERE id_silla = :id_silla
            """
        ),
        {"id_silla": id_silla},
    ).mappings().first()

    if row is None:
        return False
    return bool(row["sugerir_cambio"])
