from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from user_agents import parse as parse_user_agent

from app.db import get_db
from app.deps import ComercialUser
from app.models import AccesoPrecotizacion, Precotizacion

router = APIRouter(tags=["accesos"])

MAX_LONGITUD = 150


class AccesoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_acceso: int
    id_precotizacion: int
    fecha_acceso: datetime
    ip: str | None
    navegador: str | None
    sistema_operativo: str | None


def _recortar(valor: str | None) -> str | None:
    if valor is None:
        return None
    return valor[:MAX_LONGITUD]


def registrar_acceso(
    db: Session,
    precotizacion_id: int,
    user_agent: str | None,
) -> AccesoPrecotizacion:
    """Log one access to a public pre-quotation link.

    Parses the User-Agent into browser and operating system and inserts a single
    `acceso_precotizacion` row. Called by the pre-quotation public endpoint.
    """
    agente = parse_user_agent(user_agent or "")
    acceso = AccesoPrecotizacion(
        id_precotizacion=precotizacion_id,
        navegador=_recortar(agente.browser.family),
        sistema_operativo=_recortar(agente.os.family),
    )
    db.add(acceso)
    db.commit()
    db.refresh(acceso)
    return acceso


@router.get("/precotizaciones/{id_precotizacion}/accesos", response_model=None)
def listar_accesos(
    id_precotizacion: int,
    db: Annotated[Session, Depends(get_db)],
    user: ComercialUser,
) -> list[AccesoOut] | dict[str, str]:
    if db.get(Precotizacion, id_precotizacion) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")

    accesos = db.scalars(
        select(AccesoPrecotizacion)
        .where(AccesoPrecotizacion.id_precotizacion == id_precotizacion)
        .order_by(AccesoPrecotizacion.fecha_acceso, AccesoPrecotizacion.id_acceso)
    ).all()

    if not accesos:
        return {"mensaje": "Sin accesos registrados"}
    return [AccesoOut.model_validate(acceso) for acceso in accesos]
