"""Portal cliente (M7, R11, R4): consulta de solo lectura para el ADMIN_CLIENTE.

Capa HTTP delgada: valida rol, acota a la empresa del usuario autenticado y
arma la respuesta. El aislamiento por empresa (R4) es estructural: todo se
restringe a `user.empresa_id`, nunca a un identificador que venga del request;
un `ADMIN_CLIENTE` sin empresa resuelta recibe listas vacías.

Rutas:
- `GET /portal-cliente/sillas`: sillas levantadas de su empresa, con nombre de
  sede, estado de componentes, `sugerir_cambio` y los ids de sus fotos (las
  imágenes se bajan por el endpoint autenticado de fotos de la silla).
- `GET /portal-cliente/precotizaciones`: precotizaciones de su empresa.

No expone datos personales del empleado (RN-3/RN-4): sede/componentes/fotos son
datos de la silla.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import CurrentUser, require_role
from app.models import Fotografia, Precotizacion
from app.services import componentes_service

router = APIRouter(prefix="/portal-cliente", tags=["portal-cliente"])

AdminClienteUser = Annotated[CurrentUser, Depends(require_role("ADMIN_CLIENTE"))]


class ComponenteEstadoOut(BaseModel):
    id_componente: int
    nombre: str
    estado: str
    observacion: str | None = None


class FotoRefOut(BaseModel):
    id_fotografia: int


class SillaClienteOut(BaseModel):
    id_silla: int
    codigo_qr: str
    cargo: str
    sede: str | None = None
    estado: str
    sugerir_cambio: bool
    componentes: list[ComponenteEstadoOut] = []
    fotos: list[FotoRefOut] = []


class PrecotizacionClienteOut(BaseModel):
    id_precotizacion: int
    estado: str
    fecha_creacion: datetime
    observaciones: str | None = None


@router.get("/sillas", response_model=list[SillaClienteOut])
def listar_mis_sillas(
    db: Annotated[Session, Depends(get_db)],
    user: AdminClienteUser,
) -> list[SillaClienteOut]:
    """Sillas levantadas de la empresa del ADMIN_CLIENTE (solo lectura).

    Acotado a `user.empresa_id`; sin empresa resuelta devuelve lista vacía. No
    filtra por estado de la visita: el cliente ve todo lo levantado de su
    empresa. Cada silla trae el nombre de su sede, el estado de componentes, la
    sugerencia de cambio (`vista_estado_mantenimiento`) y los ids de sus fotos.
    """
    if user.empresa_id is None:
        return []

    schema = settings.db_schema
    filas = db.execute(
        text(
            f"""
            SELECT s.id_silla,
                   s.codigo_qr,
                   s.cargo,
                   s.estado,
                   se.nombre AS sede
            FROM {schema}.silla AS s
            LEFT JOIN {schema}.sede AS se
                ON se.id_empresa = s.id_empresa
               AND se.id_sede = s.id_sede
            WHERE s.id_empresa = :id_empresa
            ORDER BY s.id_silla
            """
        ),
        {"id_empresa": user.empresa_id},
    ).mappings().all()

    salida: list[SillaClienteOut] = []
    for fila in filas:
        id_silla = fila["id_silla"]
        componentes = componentes_service.obtener_checklist(db, id_silla)
        sugerir = componentes_service.obtener_sugerencia(db, id_silla)
        fotos = db.scalars(
            select(Fotografia.id_fotografia)
            .where(Fotografia.id_silla == id_silla)
            .order_by(Fotografia.id_fotografia)
        ).all()
        salida.append(
            SillaClienteOut(
                id_silla=id_silla,
                codigo_qr=fila["codigo_qr"],
                cargo=fila["cargo"],
                sede=fila["sede"],
                estado=fila["estado"],
                sugerir_cambio=sugerir,
                componentes=[
                    ComponenteEstadoOut(**c) for c in componentes
                ],
                fotos=[FotoRefOut(id_fotografia=fid) for fid in fotos],
            )
        )
    return salida


@router.get("/precotizaciones", response_model=list[PrecotizacionClienteOut])
def listar_mis_precotizaciones(
    db: Annotated[Session, Depends(get_db)],
    user: AdminClienteUser,
) -> list[PrecotizacionClienteOut]:
    """Precotizaciones de la empresa del ADMIN_CLIENTE (solo lectura).

    Acotado a `user.empresa_id`; sin empresa resuelta devuelve lista vacía.
    Orden determinista por `id_precotizacion`.
    """
    if user.empresa_id is None:
        return []

    precotizaciones = db.scalars(
        select(Precotizacion)
        .where(Precotizacion.id_empresa == user.empresa_id)
        .order_by(Precotizacion.id_precotizacion)
    ).all()
    return [
        PrecotizacionClienteOut(
            id_precotizacion=p.id_precotizacion,
            estado=p.estado,
            fecha_creacion=p.fecha_creacion,
            observaciones=p.observaciones,
        )
        for p in precotizaciones
    ]
