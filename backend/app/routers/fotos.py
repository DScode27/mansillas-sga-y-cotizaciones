"""Chair photograph endpoints (HU-10).

Technicians attach photographs to chairs within their own visits; authorized
users consult and retrieve them. Files live on local disk (see
`app/services/fotos_storage.py`); only the relative path is stored in
`fotografia.ruta_archivo`. Photographs are never exposed through a public QR
endpoint nor a static public mount.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import CurrentUser, get_current_user, require_role, require_tecnico_owns_visita
from app.models import Fotografia, Silla, Visita
from app.services import fotos_storage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["fotos"])

# Media type per stored extension, for the retrieval response.
_MEDIA_POR_EXTENSION = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class DetalleError(BaseModel):
    """Standard FastAPI error body (`{"detail": "..."}`)."""

    detail: str


def _err_foto(descripcion: str, ejemplo: str) -> dict:
    return {
        "model": DetalleError,
        "description": descripcion,
        "content": {"application/json": {"example": {"detail": ejemplo}}},
    }


RESP_SUBIR_FOTO = {
    400: _err_foto("Archivo no es una imagen válida.", "Archivo inválido"),
    401: _err_foto("No autenticado.", "Token de acceso requerido"),
    403: _err_foto("Rol no autorizado o técnico ajeno a la visita.", "No autorizado para esta visita"),
    404: _err_foto("La silla no existe.", "No encontrado"),
    413: _err_foto("La fotografía supera el tamaño permitido.", "La fotografía supera el tamaño permitido"),
    500: _err_foto("Fallo de almacenamiento o de persistencia.", "No fue posible almacenar la fotografía"),
}
RESP_LISTAR_FOTOS = {
    401: _err_foto("No autenticado.", "Token de acceso requerido"),
    403: _err_foto("Rol no autorizado o técnico ajeno.", "No autorizado para esta visita"),
    404: _err_foto("La silla no existe.", "No encontrado"),
}
RESP_OBTENER_FOTO = {
    200: {
        "description": "Imagen de la fotografía.",
        "content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}},
    },
    401: _err_foto("No autenticado.", "Token de acceso requerido"),
    403: _err_foto("Rol no autorizado o técnico ajeno.", "No autorizado para esta visita"),
    404: _err_foto("Silla/foto inexistente o archivo ausente.", "No encontrado"),
    500: _err_foto("Fallo inesperado de lectura.", "No fue posible leer la fotografía"),
}


class FotografiaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_fotografia: int
    id_silla: int
    ruta_archivo: str
    nombre_archivo: str
    fecha_subida: datetime


def _a_salida(foto: Fotografia) -> FotografiaOut:
    """Build the response, deriving `nombre_archivo` from the stored path.

    `nombre_archivo` is not a schema column; it is the stored file name (the
    UUID name), consistent across POST and GET.
    """
    return FotografiaOut(
        id_fotografia=foto.id_fotografia,
        id_silla=foto.id_silla,
        ruta_archivo=foto.ruta_archivo,
        nombre_archivo=Path(foto.ruta_archivo).name,
        fecha_subida=foto.fecha_subida,
    )


def _cargar_silla(db: Session, id_silla: int) -> Silla:
    silla = db.get(Silla, id_silla)
    if silla is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    return silla


def _autorizar_lectura_silla(db: Session, user: CurrentUser, silla: Silla) -> None:
    """Same rule as reading a chair: commercial any, technician own visit."""
    if user.rol == "COMERCIAL_MANSILLAS":
        return
    if user.rol != "TECNICO":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Rol no autorizado")
    visita = db.get(Visita, silla.id_visita)
    if visita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    require_tecnico_owns_visita(user, visita)


@router.post(
    "/sillas/{id_silla}/fotos",
    response_model=FotografiaOut,
    status_code=status.HTTP_201_CREATED,
    responses=RESP_SUBIR_FOTO,
)
def subir_foto(
    id_silla: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("TECNICO"))],
    archivo: Annotated[UploadFile, File()],
) -> FotografiaOut:
    """Attach one photograph to a chair (multiple allowed via repeated calls).

    Only the technician owning the chair's visit may upload. Consistency: on a
    pre-commit failure the stored file is removed; once the row is committed the
    file is never deleted by a later error.
    """
    silla = _cargar_silla(db, id_silla)
    visita = db.get(Visita, silla.id_visita)
    if visita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    require_tecnico_owns_visita(user, visita)

    # Validate the real content and size before writing anything.
    try:
        datos, extension = fotos_storage.validar_y_leer(archivo.file)
    except fotos_storage.FotoDemasiadoGrande as error:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(error)
        ) from None
    except fotos_storage.FotoInvalida:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Archivo inválido"
        ) from None

    # Store the file (pre-commit). A write failure leaves no row and no file.
    try:
        nombre = fotos_storage.guardar(datos, extension)
    except fotos_storage.FotoAlmacenamientoError:
        logger.exception("Fallo al almacenar la fotografía de la silla %s", id_silla)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible almacenar la fotografía",
        ) from None

    # Persist the row, building the model inside the protected block.
    #
    # Two failure modes are distinguished without extra machinery:
    #   * Confirmed pre-commit failure (the transaction definitely did not
    #     commit, e.g. a flush/integrity error): compensate by deleting the
    #     just-stored file. A failing rollback must not prevent this.
    #   * Uncertain commit outcome (a connection-level error during COMMIT: the
    #     row MAY already be persisted): do NOT delete the file, to avoid
    #     orphaning a committed row. A rare orphan file is preferred and logged.
    # No distributed transaction or extra recovery is added.
    try:
        foto = Fotografia(id_silla=silla.id_silla, ruta_archivo=nombre)
        db.add(foto)
        db.commit()
    except DBAPIError as error:
        commit_incierto = bool(getattr(error, "connection_invalidated", False))
        try:
            db.rollback()
        except Exception:
            logger.exception("Fallo el rollback tras el error de persistencia")
        if commit_incierto:
            logger.error(
                "Resultado de commit incierto (silla %s); se conserva el archivo "
                "%s para no dejar una fila huérfana", id_silla, nombre,
            )
        else:
            logger.exception(
                "Fallo de persistencia confirmado (silla %s); compensando", id_silla
            )
            fotos_storage.eliminar(nombre)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible registrar la fotografía",
        ) from None
    except Exception:
        # Non-DBAPI error before a confirmed commit → treat as pre-commit and
        # compensate.
        logger.exception(
            "Fallo al registrar la fotografía (silla %s); compensando", id_silla
        )
        try:
            db.rollback()
        except Exception:
            logger.exception("Fallo el rollback tras el error de persistencia")
        fotos_storage.eliminar(nombre)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible registrar la fotografía",
        ) from None

    # Committed: the file is now owned by a row. Any error below (refresh,
    # serialization) must NOT delete the file.
    db.refresh(foto)
    return _a_salida(foto)


@router.get(
    "/sillas/{id_silla}/fotos",
    response_model=list[FotografiaOut],
    responses=RESP_LISTAR_FOTOS,
)
def listar_fotos(
    id_silla: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[FotografiaOut]:
    """Return all photographs of a chair (empty list when none)."""
    silla = _cargar_silla(db, id_silla)
    _autorizar_lectura_silla(db, user, silla)

    fotos = db.scalars(
        select(Fotografia)
        .where(Fotografia.id_silla == id_silla)
        .order_by(Fotografia.id_fotografia)
    ).all()
    return [_a_salida(foto) for foto in fotos]


@router.get("/sillas/{id_silla}/fotos/{id_fotografia}", responses=RESP_OBTENER_FOTO)
def obtener_foto(
    id_silla: int,
    id_fotografia: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FileResponse:
    """Stream one photograph's image bytes through the chair's access rules."""
    silla = _cargar_silla(db, id_silla)
    _autorizar_lectura_silla(db, user, silla)

    foto = db.get(Fotografia, id_fotografia)
    if foto is None or foto.id_silla != id_silla:
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
