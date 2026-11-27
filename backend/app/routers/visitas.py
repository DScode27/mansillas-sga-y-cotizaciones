from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import (
    ComercialUser,
    CurrentUser,
    get_current_user,
    require_tecnico_owns_visita,
)
from app.models import Empresa, Sede, Silla, Usuario, Visita

router = APIRouter(prefix="/visitas", tags=["visitas"])

EstadoVisita = Literal["PROGRAMADA", "EN_CURSO", "FINALIZADA", "CANCELADA"]

REQUIRED_FIELDS = ("id_empresa", "id_sede", "id_tecnico", "cantidad_estimada")
EDITABLE_FIELDS = ("id_sede", "id_tecnico", "fecha_programada", "estado", "observaciones")


class VisitaCreate(BaseModel):
    id_empresa: int | None = None
    id_sede: int | None = None
    id_tecnico: int | None = None
    cantidad_estimada: int | None = None
    fecha_programada: datetime | None = None
    observaciones: str | None = None


class VisitaUpdate(BaseModel):
    id_sede: int | None = None
    id_tecnico: int | None = None
    fecha_programada: datetime | None = None
    estado: EstadoVisita | None = None
    observaciones: str | None = None
    # Accepted for client compatibility but never written: RN-04 keeps the
    # original estimate untouched.
    cantidad_estimada: int | None = None


class VisitaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_visita: int
    id_empresa: int
    id_sede: int
    id_comercial: int
    id_tecnico: int
    fecha_programada: datetime | None
    cantidad_estimada: int
    estado: str
    observaciones: str | None


def _campos_faltantes(payload: VisitaCreate) -> list[str]:
    return [campo for campo in REQUIRED_FIELDS if getattr(payload, campo) is None]


def _validar_referencias(
    db: Session,
    id_empresa: int,
    id_sede: int,
    id_tecnico: int,
) -> None:
    if db.get(Empresa, id_empresa) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")

    sede = db.get(Sede, id_sede)
    if sede is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    if sede.id_empresa != id_empresa:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "La sede no pertenece a la empresa",
        )

    tecnico = db.get(Usuario, id_tecnico)
    if tecnico is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    if tecnico.rol != "TECNICO":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El usuario asignado no tiene rol TECNICO",
        )


def _cargar_visita(db: Session, id_visita: int) -> Visita:
    visita = db.get(Visita, id_visita)
    if visita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    return visita


def _autorizar_lectura(user: CurrentUser, visita: Visita) -> None:
    if user.rol == "COMERCIAL_MANSILLAS":
        return
    if user.rol == "TECNICO":
        require_tecnico_owns_visita(user, visita)
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Rol no autorizado")


@router.post("", response_model=VisitaOut, status_code=status.HTTP_201_CREATED)
def crear_visita(
    payload: VisitaCreate,
    db: Annotated[Session, Depends(get_db)],
    user: ComercialUser,
) -> Visita:
    faltantes = _campos_faltantes(payload)
    if faltantes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Campos obligatorios faltantes: {', '.join(faltantes)}",
        )
    if payload.cantidad_estimada is not None and payload.cantidad_estimada < 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "cantidad_estimada no puede ser negativa",
        )

    _validar_referencias(
        db,
        payload.id_empresa,
        payload.id_sede,
        payload.id_tecnico,
    )

    visita = Visita(
        id_empresa=payload.id_empresa,
        id_sede=payload.id_sede,
        id_comercial=user.id,
        id_tecnico=payload.id_tecnico,
        fecha_programada=payload.fecha_programada,
        cantidad_estimada=payload.cantidad_estimada,
        observaciones=payload.observaciones,
    )
    db.add(visita)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No fue posible registrar la visita",
        ) from None
    db.refresh(visita)
    return visita


@router.get("", response_model=list[VisitaOut])
def listar_visitas(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[Visita]:
    if user.rol == "COMERCIAL_MANSILLAS":
        stmt = select(Visita)
    elif user.rol == "TECNICO":
        stmt = select(Visita).where(Visita.id_tecnico == user.id)
    elif user.rol == "ADMIN_CLIENTE":
        # Portal cliente (R4): solo las visitas de su propia empresa. Sin
        # empresa resuelta, lista vacía (igual que portal_cliente.py).
        if user.empresa_id is None:
            return []
        stmt = select(Visita).where(Visita.id_empresa == user.empresa_id)
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Rol no autorizado")
    return list(db.scalars(stmt.order_by(Visita.id_visita)).all())


@router.get("/{id_visita}", response_model=VisitaOut)
def obtener_visita(
    id_visita: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Visita:
    visita = _cargar_visita(db, id_visita)
    _autorizar_lectura(user, visita)
    return visita


@router.put("/{id_visita}", response_model=VisitaOut)
def actualizar_visita(
    id_visita: int,
    payload: VisitaUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: ComercialUser,
) -> Visita:
    visita = _cargar_visita(db, id_visita)
    datos = payload.model_dump(exclude_unset=True)
    datos.pop("cantidad_estimada", None)

    id_sede = datos.get("id_sede", visita.id_sede)
    id_tecnico = datos.get("id_tecnico", visita.id_tecnico)
    if "id_sede" in datos or "id_tecnico" in datos:
        _validar_referencias(db, visita.id_empresa, id_sede, id_tecnico)

    for campo in EDITABLE_FIELDS:
        if campo in datos:
            setattr(visita, campo, datos[campo])

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No fue posible actualizar la visita",
        ) from None
    db.refresh(visita)
    return visita


@router.put("/{id_visita}/finalizar", response_model=VisitaOut)
def finalizar_visita(
    id_visita: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Visita:
    """El técnico dueño de la visita la marca como FINALIZADA (HU-28).

    Cierra el levantamiento desde la pantalla móvil del técnico, sin pasar por el
    `PUT /visitas/{id}` del comercial. Solo el TECNICO asignado a la visita puede
    hacerlo (`require_tecnico_owns_visita`); cualquier otro rol recibe 403. No
    reescribe `cantidad_estimada` (RN-04). Idempotente: finalizar una visita ya
    FINALIZADA la deja igual.
    """
    if user.rol != "TECNICO":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Rol no autorizado")

    visita = _cargar_visita(db, id_visita)
    require_tecnico_owns_visita(user, visita)

    visita.estado = "FINALIZADA"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No fue posible finalizar la visita",
        ) from None
    db.refresh(visita)
    return visita


@router.delete("/{id_visita}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_visita(
    id_visita: int,
    db: Annotated[Session, Depends(get_db)],
    user: ComercialUser,
) -> None:
    visita = _cargar_visita(db, id_visita)

    tiene_sillas = db.scalar(
        select(Silla.id_silla).where(Silla.id_visita == visita.id_visita).limit(1)
    )
    if tiene_sillas is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La visita tiene sillas registradas",
        )

    db.delete(visita)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La visita no puede eliminarse",
        ) from None
