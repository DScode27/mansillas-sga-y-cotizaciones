from io import BytesIO
from typing import Annotated

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Response, status
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
from app.deps import CurrentUser, get_current_user
from app.models import Silla, Visita

router = APIRouter(prefix="/qr", tags=["qr"])

MARGIN = 1.2 * cm
COLUMNS = 3
ROWS = 4
QR_SIZE = 4 * cm  # well above the 3 cm x 3 cm minimum


class QrPdfRequest(BaseModel):
    ids: list[int] = []


def _token_de(silla: Silla) -> str:
    return str(silla.token_publico)


def url_publica_silla(silla: Silla) -> str:
    """Public URL encoded inside the QR: never personal data."""
    return f"{settings.frontend_url.rstrip('/')}/silla/{_token_de(silla)}"


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
