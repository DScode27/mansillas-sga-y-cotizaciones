from datetime import datetime
from io import BytesIO
from typing import Annotated

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from qrcode.constants import ERROR_CORRECT_H
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import CurrentUser, get_current_user, require_role
from app.models import Fotografia, Silla, Visita
from app.routers.fotos import _MEDIA_POR_EXTENSION
from app.routers.sillas import get_silla_by_token
from app.services import fotos_storage, permisos_service, qr_service
from app.services.email_service import EmailSender, get_email_sender
from app.services.permisos_service import PermisoInvalido
from app.services.qr_service import (
    EmpleadoNoEncontrado,
    OtpExpiradoOUsado,
    OtpInvalido,
    PermisoInsuficiente,
    SoloAdminCliente,
)

router = APIRouter(prefix="/qr", tags=["qr"])

MARGIN = 1.2 * cm
COLUMNS = 3
ROWS = 4
QR_SIZE = 4 * cm  # well above the 3 cm x 3 cm minimum


class QrPdfRequest(BaseModel):
    ids: list[int] = []


class ComponentePublicoOut(BaseModel):
    """One component's state in the public chair lookup (HU-17)."""

    id_componente: int
    nombre: str
    estado: str
    observacion: str | None = None


class ConsultaPublicaOut(BaseModel):
    """Public chair lookup response (HU-17): chair data + owning company's
    permiso_qr and component states. Never includes the employee's name,
    document or email (RN-3/RN-4); company/branch and components are chair data,
    not personal data."""

    id_silla: int
    codigo_qr: str
    estado: str
    cargo: str
    serial_antiguo: str | None = None
    empresa: str | None = None
    sede: str | None = None
    permiso_qr: int
    componentes: list[ComponentePublicoOut] = []


class FotoPublicaOut(BaseModel):
    """One photograph reference in the public chair lookup (HU-17).

    Only the identifier is exposed; the bytes are served by the anonymous
    `GET /qr/silla/{token}/fotos/{id_fotografia}` endpoint keyed by the public
    token. No stored path or file name is leaked."""

    id_fotografia: int


class PermisoQrOut(BaseModel):
    """Current QR permission level for a company (HU-18)."""

    id_empresa: int
    permiso_qr: int


class PermisoQrUpdate(BaseModel):
    """New QR permission level; validated as 1/2/3 in permisos_service (422)."""

    permiso_qr: int


class SolicitudOtp(BaseModel):
    """OTP request body (HU-24): the employee identifies by email or document."""

    correo: str | None = None
    documento: str | None = None


class TicketCreate(BaseModel):
    """Ticket creation body through the public QR flow (HU-24)."""

    asunto: str
    descripcion: str
    correo: str | None = None
    documento: str | None = None
    codigo: str


class TicketOut(BaseModel):
    """Public ticket response (HU-24). Never exposes the employee's personal
    data; only the chair and ticket fields."""

    id_ticket: int
    id_silla: int
    asunto: str
    descripcion: str
    estado: str
    fecha_creacion: datetime


def _token_de(silla: Silla) -> str:
    return str(silla.token_publico)


def url_publica_silla(silla: Silla) -> str:
    """Public URL encoded inside the QR: never personal data.

    Points to the frontend SPA route (`/qr/:token`), not the backend API path.
    """
    return f"{settings.frontend_url.rstrip('/')}/qr/{_token_de(silla)}"


def _imagen_qr(silla: Silla) -> BytesIO:
    codigo = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    codigo.add_data(url_publica_silla(silla))
    codigo.make(fit=True)
    imagen = codigo.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    imagen.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _cargar_sillas(db: Session, ids: list[int]) -> list[Silla]:
    unicos = list(dict.fromkeys(ids))
    sillas = list(db.scalars(select(Silla).where(Silla.id_silla.in_(unicos))).all())
    if len(sillas) != len(unicos):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    por_id = {silla.id_silla: silla for silla in sillas}
    return [por_id[id_silla] for id_silla in unicos]


def _autorizar_lote(db: Session, user: CurrentUser, sillas: list[Silla]) -> None:
    if user.rol == "COMERCIAL_MANSILLAS":
        return
    if user.rol != "TECNICO":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Rol no autorizado")

    visitas = {
        visita.id_visita: visita
        for visita in db.scalars(
            select(Visita).where(
                Visita.id_visita.in_({silla.id_visita for silla in sillas})
            )
        ).all()
    }
    for silla in sillas:
        visita = visitas.get(silla.id_visita)
        if visita is None or visita.id_tecnico != user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "No autorizado para esta visita",
            )


def _componer_pdf(sillas: list[Silla]) -> bytes:
    page_width, page_height = A4
    ancho_util = page_width - 2 * MARGIN
    alto_util = page_height - 2 * MARGIN
    ancho_celda = ancho_util / COLUMNS
    alto_celda = alto_util / ROWS
    por_pagina = COLUMNS * ROWS

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    for indice, silla in enumerate(sillas):
        posicion = indice % por_pagina
        if indice and posicion == 0:
            pdf.showPage()

        columna = posicion % COLUMNS
        fila = posicion // COLUMNS

        x = MARGIN + columna * ancho_celda
        y_tope = page_height - MARGIN - fila * alto_celda

        imagen = _imagen_qr(silla)
        x_qr = x + (ancho_celda - QR_SIZE) / 2
        y_qr = y_tope - 0.4 * cm - QR_SIZE
        pdf.drawImage(
            ImageReader(imagen),
            x_qr,
            y_qr,
            width=QR_SIZE,
            height=QR_SIZE,
        )

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawCentredString(
            x + ancho_celda / 2,
            y_qr - 0.7 * cm,
            silla.codigo_qr,
        )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@router.get("/silla/{token}", response_model=ConsultaPublicaOut)
def consultar_silla_publica(
    token: str,
    db: Annotated[Session, Depends(get_db)],
) -> ConsultaPublicaOut:
    """Public chair lookup (HU-17): no `get_current_user`, no auth required.

    Resolves the chair by its public token; an unknown or malformed token
    yields 404 "QR no válido". Returns only basic chair data plus the owning
    company's `permiso_qr`, never the employee's personal data.
    """
    silla = get_silla_by_token(db, token)
    if silla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "QR no válido")

    datos = qr_service.consultar_silla_publica(db, silla)
    return ConsultaPublicaOut(**datos)


@router.get("/silla/{token}/fotos", response_model=list[FotoPublicaOut])
def listar_fotos_publicas(
    token: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[FotoPublicaOut]:
    """Public photo listing for a chair (HU-17): no auth, keyed by public token.

    Resolves the chair by its `token_publico` (unknown/malformed → 404) and
    returns only the photo identifiers; the bytes are served by the companion
    endpoint. The public token (a 128-bit UUID) acts as the capability to view
    this chair's photographs and nothing else. No personal data is involved: a
    photograph belongs to the chair, not to the employee (RN-3/RN-4).
    """
    silla = get_silla_by_token(db, token)
    if silla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "QR no válido")

    fotos = db.scalars(
        select(Fotografia)
        .where(Fotografia.id_silla == silla.id_silla)
        .order_by(Fotografia.id_fotografia)
    ).all()
    return [FotoPublicaOut(id_fotografia=foto.id_fotografia) for foto in fotos]


@router.get("/silla/{token}/fotos/{id_fotografia}")
def obtener_foto_publica(
    token: str,
    id_fotografia: int,
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    """Serve one chair photograph through the public QR (HU-17): no auth.

    Resolves the chair by its `token_publico`; the requested photograph must
    belong to that chair (otherwise 404, so the token never grants access to
    another chair's photos). `fotos_storage.resolver` guarantees the stored path
    cannot escape the storage directory.
    """
    silla = get_silla_by_token(db, token)
    if silla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "QR no válido")

    foto = db.get(Fotografia, id_fotografia)
    if foto is None or foto.id_silla != silla.id_silla:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")

    try:
        ruta = fotos_storage.resolver(foto.ruta_archivo)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado") from None
    except fotos_storage.FotoInvalida:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado") from None
    except OSError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible leer la fotografía",
        ) from None

    media = _MEDIA_POR_EXTENSION.get(ruta.suffix.lower(), "application/octet-stream")
    return FileResponse(ruta, media_type=media)


@router.post("/silla/{token}/otp", status_code=status.HTTP_204_NO_CONTENT)
def solicitar_otp_publico(
    token: str,
    payload: SolicitudOtp,
    db: Annotated[Session, Depends(get_db)],
    sender: Annotated[EmailSender, Depends(get_email_sender)],
) -> Response:
    """Solicitud pública de OTP (HU-24): no `get_current_user`, sin auth.

    Resuelve la silla por su token público; un token desconocido o mal formado
    responde 404 "QR no válido". Delega en `qr_service.solicitar_otp`, que
    identifica al empleado por `correo` o `documento` dentro de la empresa dueña
    de la silla y le envía el OTP; si no hay empleado que coincida, se traduce a
    404 "Empleado no encontrado". Responde 204 sin cuerpo al emitir el OTP.
    """
    silla = get_silla_by_token(db, token)
    if silla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "QR no válido")

    try:
        qr_service.solicitar_otp(
            db,
            silla=silla,
            correo=payload.correo,
            documento=payload.documento,
            sender=sender,
        )
    except EmpleadoNoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empleado no encontrado")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/silla/{token}/ticket",
    response_model=TicketOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_ticket_publico(
    token: str,
    payload: TicketCreate,
    db: Annotated[Session, Depends(get_db)],
) -> TicketOut:
    """Creación pública de ticket por QR (HU-24): no `get_current_user`, sin auth.

    Resuelve la silla por su token público; un token desconocido o mal formado
    responde 404 "QR no válido". Delega en `qr_service.crear_ticket_por_qr`, que
    aplica el `permiso_qr` de la empresa dueña, valida el OTP del empleado y crea
    el ticket. Traduce las excepciones de dominio a HTTP:
    `EmpleadoNoEncontrado` → 404 "Empleado no encontrado",
    `PermisoInsuficiente` → 403 "Permiso insuficiente", `SoloAdminCliente` → 403
    "Solo el administrador del cliente puede crear tickets", `OtpInvalido` → 400
    "OTP inválido", `OtpExpiradoOUsado` → 400 "OTP expirado o ya utilizado".
    Responde 201 con el `TicketOut`.
    """
    silla = get_silla_by_token(db, token)
    if silla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "QR no válido")

    try:
        ticket = qr_service.crear_ticket_por_qr(
            db,
            silla=silla,
            correo=payload.correo,
            documento=payload.documento,
            codigo=payload.codigo,
            asunto=payload.asunto,
            descripcion=payload.descripcion,
        )
    except EmpleadoNoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empleado no encontrado")
    except PermisoInsuficiente:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permiso insuficiente")
    except SoloAdminCliente:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo el administrador del cliente puede crear tickets",
        )
    except OtpInvalido:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "OTP inválido")
    except OtpExpiradoOUsado:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "OTP expirado o ya utilizado"
        )

    return TicketOut(
        id_ticket=ticket.id_ticket,
        id_silla=ticket.id_silla,
        asunto=ticket.asunto,
        descripcion=ticket.descripcion,
        estado=ticket.estado,
        fecha_creacion=ticket.fecha_creacion,
    )


@router.post("/pdf")
def descargar_pdf(
    payload: QrPdfRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Response:
    if not payload.ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Debe seleccionar al menos una silla",
        )

    sillas = _cargar_sillas(db, payload.ids)
    _autorizar_lote(db, user, sillas)

    contenido = _componer_pdf(sillas)
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="qr_sillas.pdf"',
        },
    )


def _autorizar_empresa(user: CurrentUser, id_empresa: int) -> None:
    """Aislamiento multiempresa (HU-18, RN-6).

    `require_role("ADMIN_CLIENTE")` ya garantiza el rol (403 "Rol no autorizado"
    si no coincide). Aquí comprobamos que el `ADMIN_CLIENTE` solo opere sobre su
    propia empresa: si `user.empresa_id` difiere de `id_empresa`, 403.
    """
    if user.empresa_id != id_empresa:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "No autorizado para esta empresa",
        )


@router.get("/empresas/{id_empresa}/permiso-qr", response_model=PermisoQrOut)
def obtener_permiso_qr(
    id_empresa: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("ADMIN_CLIENTE"))],
) -> PermisoQrOut:
    """Lee `empresa.permiso_qr` de la empresa del `ADMIN_CLIENTE` (HU-18).

    Ruta resultante: `/qr/empresas/{id_empresa}/permiso-qr` (el router lleva el
    prefijo `/qr`; no se modifica `app/main.py`). Exige rol `ADMIN_CLIENTE`
    (`require_role` → 403 "Rol no autorizado") y que la empresa objetivo sea la
    del usuario (`_autorizar_empresa` → 403 "No autorizado para esta empresa").
    """
    _autorizar_empresa(user, id_empresa)
    permiso = permisos_service.obtener_permiso_qr(db, id_empresa=id_empresa)
    return PermisoQrOut(id_empresa=id_empresa, permiso_qr=permiso)


@router.put("/empresas/{id_empresa}/permiso-qr", response_model=PermisoQrOut)
def actualizar_permiso_qr(
    id_empresa: int,
    payload: PermisoQrUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("ADMIN_CLIENTE"))],
) -> PermisoQrOut:
    """Actualiza `empresa.permiso_qr` de la empresa del `ADMIN_CLIENTE` (HU-18).

    Ruta resultante: `/qr/empresas/{id_empresa}/permiso-qr` (prefijo `/qr` del
    router; sin tocar `app/main.py`). Mismo RBAC que el GET. Delega en
    `permisos_service.actualizar_permiso_qr`, que valida el nivel 1/2/3; un valor
    fuera de ese conjunto lanza `PermisoInvalido`, traducido a 422 "permiso_qr
    debe ser 1, 2 o 3".
    """
    _autorizar_empresa(user, id_empresa)
    try:
        permiso = permisos_service.actualizar_permiso_qr(
            db, id_empresa=id_empresa, permiso=payload.permiso_qr
        )
    except PermisoInvalido:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "permiso_qr debe ser 1, 2 o 3",
        )

    return PermisoQrOut(id_empresa=id_empresa, permiso_qr=permiso)
