"""Shared pre-quotation consistency rules (HU-12/HU-13).

Kept in a service module so both the `sillas` and `precotizaciones` routers can
reuse the Visit-row lock and the "proposal editable" guard without importing
each other (no circular imports).

The coordinating lock is taken on the existing `visita` row (`SELECT ... FOR
UPDATE`): locking `precotizacion` rows before any exists would lock nothing, so
it could not prevent concurrent duplicate creation. Callers must run these
helpers inside the request's existing session transaction and acquire the Visit
lock first (consistent lock order).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AceptacionPrecotizacion, Precotizacion, Visita

# States that mean "an active proposal exists for the visit".
ESTADOS_ACTIVOS = ("BORRADOR", "ENVIADA", "ACEPTADA")
# States in which the proposal data is frozen (survey edits forbidden).
ESTADOS_CONGELADOS = ("ENVIADA", "ACEPTADA")


def lock_visita(db: Session, id_visita: int) -> Visita | None:
    """Lock and return the `visita` row, or None if it does not exist.

    Uses `SELECT ... FOR UPDATE` on the Visit row as the single coordination
    point for create / commercial-edit / send.
    """
    return db.scalar(
        select(Visita).where(Visita.id_visita == id_visita).with_for_update()
    )


def precotizacion_activa(db: Session, id_visita: int) -> Precotizacion | None:
    """Return the visit's active pre-quotation (BORRADOR/ENVIADA/ACEPTADA), if any."""
    return db.scalar(
        select(Precotizacion)
        .where(
            Precotizacion.id_visita == id_visita,
            Precotizacion.estado.in_(ESTADOS_ACTIVOS),
        )
        .order_by(Precotizacion.id_precotizacion)
    )


def propuesta_congelada(db: Session, id_visita: int) -> bool:
    """True when the visit has a proposal whose data must not change (ENVIADA/ACEPTADA)."""
    fila = db.scalar(
        select(Precotizacion.id_precotizacion).where(
            Precotizacion.id_visita == id_visita,
            Precotizacion.estado.in_(ESTADOS_CONGELADOS),
        )
    )
    return fila is not None


class CotizacionNoHabilitada(Exception):
    """Quotation operations are not enabled for the pre-quotation (HU-16)."""


def estado_habilitacion_cotizacion(db: Session, id_precotizacion: int) -> tuple[str | None, bool]:
    """Single source of truth for HU-16 enablement.

    Returns `(estado, habilitado)`:
      * `estado` is the pre-quotation's real state, or None if it does not exist.
      * `habilitado` is True only when the pre-quotation exists, its state is
        exactly `ACEPTADA`, and an `aceptacion_precotizacion` row exists for it.
    One query for the state, one for the acceptance; no duplication of the rule.
    """
    estado = db.scalar(
        select(Precotizacion.estado).where(
            Precotizacion.id_precotizacion == id_precotizacion
        )
    )
    if estado is None:
        return None, False
    if estado != "ACEPTADA":
        return estado, False
    tiene_aceptacion = db.scalar(
        select(AceptacionPrecotizacion.id_aceptacion).where(
            AceptacionPrecotizacion.id_precotizacion == id_precotizacion
        )
    )
    return estado, tiene_aceptacion is not None


def cotizacion_habilitada(db: Session, id_precotizacion: int) -> bool:
    """True iff quotation operations are enabled for the pre-quotation (HU-16)."""
    return estado_habilitacion_cotizacion(db, id_precotizacion)[1]


def exigir_cotizacion_habilitada(db: Session, id_precotizacion: int) -> None:
    """Enforcement guard for future quotation operations.

    Raises `CotizacionNoHabilitada` when quotation is not enabled, so a real
    quotation operation can reject the request inside its own transaction. This
    is the enforce side; `cotizacion_habilitada` is the consult side — both use
    the same rule.
    """
    if not cotizacion_habilitada(db, id_precotizacion):
        raise CotizacionNoHabilitada(id_precotizacion)
