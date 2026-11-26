import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import (
    CurrentUser,
    get_current_user,
    require_tecnico_owns_visita,
    require_role,
)
from app.models import Empleado, Silla, Visita
from app.services.componentes_service import (
    ChecklistIncompleto,
    ComponenteDesconocido,
    EstadoInvalido,
    guardar_checklist,
    obtener_checklist,
    obtener_sugerencia,
)

router = APIRouter(tags=["sillas"])

SERIAL_DUPLICADO = "serial_antiguo duplicado para la empresa"


class SillaCreate(BaseModel):
    id_empleado: int | None = None
    cargo: str | None = None
    serial_antiguo: str | None = None
    observaciones: str | None = None


class SillaUpdate(BaseModel):
    serial_antiguo: str | None = None
    observaciones: str | None = None


class SillaCreadaOut(BaseModel):
    """Response contract of the registration endpoint (task 3.2)."""

    id_silla: int
    id_empresa: int
    id_sede: int
    id_departamento: int
    id_empleado: int
    cargo: str
    codigo_qr: str
    token_publico: uuid.UUID


class SillaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_silla: int
    id_empresa: int
    id_visita: int
    id_sede: int
    id_departamento: int
    id_empleado: int
    cargo: str
    numero_qr: int
    codigo_qr: str
    token_publico: uuid.UUID
    serial_antiguo: str | None
    observaciones: str | None
    estado: str
    fecha_registro: datetime


class ComponenteItemIn(BaseModel):
    id_componente: int
    estado: str
    observacion: str | None = None


class ChecklistIn(BaseModel):
    items: list[ComponenteItemIn]


class ComponenteItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_componente: int
    nombre: str
    estado: str
    observacion: str | None


class ChecklistOut(BaseModel):
    id_silla: int
    items: list[ComponenteItemOut]
    sugerir_cambio: bool


def _normalizar_texto(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio or None


def _es_serial_duplicado(error: IntegrityError) -> bool:
    detalle = str(getattr(error, "orig", error))
    return "serial_antiguo" in detalle or "duplicate key" in detalle


def _visita_de(db: Session, silla: Silla) -> Visita | None:
    return db.get(Visita, silla.id_visita)


def get_silla_by_token(db: Session, token: str | uuid.UUID) -> Silla | None:
    """Return the chair behind a public token, or `None` when it does not exist."""
    try:
        valor = token if isinstance(token, uuid.UUID) else uuid.UUID(str(token))
    except (ValueError, AttributeError, TypeError):
        return None
    return db.scalar(select(Silla).where(Silla.token_publico == valor))


def _cargar_silla(db: Session, id_silla: int) -> Silla:
    silla = db.get(Silla, id_silla)
    if silla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    return silla


def _autorizar_silla(db: Session, user: CurrentUser, silla: Silla) -> None:
    if user.rol == "COMERCIAL_MANSILLAS":
        return
    if user.rol != "TECNICO":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Rol no autorizado")

    visita = _visita_de(db, silla)
    if visita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    require_tecnico_owns_visita(user, visita)


@router.post(
    "/visitas/{id_visita}/sillas",
    response_model=SillaCreadaOut,
    status_code=status.HTTP_201_CREATED,
)
def registrar_silla(
    id_visita: int,
    payload: SillaCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("TECNICO"))],
) -> Silla:
    visita = db.get(Visita, id_visita)
    if visita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    require_tecnico_owns_visita(user, visita)

    cargo = _normalizar_texto(payload.cargo)
    faltantes = [
        campo
        for campo, valor in (("id_empleado", payload.id_empleado), ("cargo", cargo))
        if valor is None
    ]
    if faltantes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Información incompleta: faltan {', '.join(faltantes)}",
        )

    empleado = db.get(Empleado, payload.id_empleado)
    if empleado is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    if empleado.id_empresa != visita.id_empresa or empleado.id_sede != visita.id_sede:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El empleado no pertenece a la empresa y sede de la visita",
        )

    silla = Silla(
        id_empresa=empleado.id_empresa,
        id_visita=visita.id_visita,
        id_sede=empleado.id_sede,
        id_departamento=empleado.id_departamento,
        id_empleado=empleado.id_empleado,
        cargo=cargo,
        codigo_qr="",
        serial_antiguo=_normalizar_texto(payload.serial_antiguo),
        observaciones=_normalizar_texto(payload.observaciones),
    )
    db.add(silla)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _es_serial_duplicado(error):
            raise HTTPException(status.HTTP_409_CONFLICT, SERIAL_DUPLICADO) from None
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No fue posible registrar la silla",
        ) from None

    db.refresh(silla)
    return silla


@router.get("/sillas/token/{token}", response_model=SillaCreadaOut)
def obtener_silla_por_token(
    token: str,
    db: Annotated[Session, Depends(get_db)],
) -> Silla:
    silla = get_silla_by_token(db, token)
    if silla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    return silla


@router.get("/sillas/{id_silla}", response_model=SillaOut)
def obtener_silla(
    id_silla: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Silla:
    silla = _cargar_silla(db, id_silla)
    _autorizar_silla(db, user, silla)
    return silla


@router.put("/sillas/{id_silla}", response_model=SillaOut)
def actualizar_silla(
    id_silla: int,
    payload: SillaUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("TECNICO"))],
) -> Silla:
    silla = _cargar_silla(db, id_silla)
    _autorizar_silla(db, user, silla)

    datos = payload.model_dump(exclude_unset=True)
    if "serial_antiguo" in datos:
        silla.serial_antiguo = _normalizar_texto(datos["serial_antiguo"])
    if "observaciones" in datos:
        silla.observaciones = _normalizar_texto(datos["observaciones"])

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if _es_serial_duplicado(error):
            raise HTTPException(status.HTTP_409_CONFLICT, SERIAL_DUPLICADO) from None
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No fue posible actualizar la silla",
        ) from None

    db.refresh(silla)
    return silla


@router.put("/sillas/{id_silla}/componentes", response_model=ChecklistOut)
def guardar_componentes(
    id_silla: int,
    payload: ChecklistIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("TECNICO"))],
) -> ChecklistOut:
    silla = _cargar_silla(db, id_silla)
    _autorizar_silla(db, user, silla)

    items = [item.model_dump() for item in payload.items]
    try:
        checklist = guardar_checklist(db, id_silla, items)
    except ComponenteDesconocido as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    except (EstadoInvalido, ChecklistIncompleto) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None

    return ChecklistOut(
        id_silla=id_silla,
        items=[ComponenteItemOut.model_validate(fila) for fila in checklist],
        sugerir_cambio=obtener_sugerencia(db, id_silla),
    )


@router.get("/sillas/{id_silla}/componentes", response_model=ChecklistOut)
def leer_componentes(
    id_silla: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ChecklistOut:
    silla = _cargar_silla(db, id_silla)
    _autorizar_silla(db, user, silla)

    checklist = obtener_checklist(db, id_silla)
    return ChecklistOut(
        id_silla=id_silla,
        items=[ComponenteItemOut.model_validate(fila) for fila in checklist],
        sugerir_cambio=obtener_sugerencia(db, id_silla),
    )
