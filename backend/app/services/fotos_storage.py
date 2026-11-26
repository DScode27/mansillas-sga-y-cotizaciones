"""Local-disk storage and validation for chair photographs (HU-10).

Files are written to `settings.photo_storage_path` under a server-generated
UUID name; only the **relative** path is kept in `fotografia.ruta_archivo`.
A single mechanism, no provider abstraction (see the spec's storage decision).

The helper raises domain errors (`FotoDemasiadoGrande`, `FotoInvalida`,
`FotoAlmacenamientoError`) so the router maps them to HTTP status codes without
coupling this module to FastAPI.
"""

from __future__ import annotations

import io
import logging
import uuid
import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.config import settings

logger = logging.getLogger(__name__)

# Allowed Pillow formats → file extension used for the stored name.
_EXTENSION_POR_FORMATO = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


class FotoDemasiadoGrande(Exception):
    """The upload exceeds `photo_max_bytes` (maps to 413)."""


class FotoInvalida(Exception):
    """The upload is not a valid, non-corrupt image of an allowed format (400)."""


class FotoAlmacenamientoError(Exception):
    """An unexpected storage read/write failure (maps to 500)."""


def _formatos_permitidos() -> set[str]:
    return {fmt.upper() for fmt in settings.photo_allowed_formats}


def validar_y_leer(flujo) -> tuple[bytes, str]:
    """Read the upload with a hard size cap and validate its real content.

    `flujo` is any binary file-like object with `.read()` (e.g. FastAPI's
    `UploadFile.file`). Returns the raw bytes and the extension to store with.

    Raises `FotoDemasiadoGrande` if more than `photo_max_bytes` are read, and
    `FotoInvalida` for a non-image, corrupt/truncated image, or a format outside
    the allowed set. Pillow's decompression-bomb warning/error is treated as a
    validation failure.
    """
    limite = settings.photo_max_bytes
    datos = flujo.read(limite + 1)
    if datos is None:
        raise FotoInvalida("Archivo vacío")
    if len(datos) > limite:
        raise FotoDemasiadoGrande("La fotografía supera el tamaño permitido")
    if not datos:
        raise FotoInvalida("Archivo vacío")

    permitidos = _formatos_permitidos() & set(_EXTENSION_POR_FORMATO)
    try:
        with warnings.catch_warnings():
            # Pillow raises DecompressionBombWarning for oversized images; make
            # it an error so it is rejected as invalid content.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            # First pass: verify() detects most corruption cheaply and reads the
            # real format from the file header, without a full decode.
            with Image.open(io.BytesIO(datos)) as imagen:
                formato = (imagen.format or "").upper()
                imagen.verify()

            # Reject disallowed formats before the costly full decode. A format
            # outside the extension map is also rejected (no KeyError below).
            if formato not in permitidos:
                raise FotoInvalida(
                    f"Formato no permitido: {formato or 'desconocido'}"
                )

            # verify() leaves the image unusable; reopen and force a full decode
            # (load) to catch truncated files that verify() misses.
            with Image.open(io.BytesIO(datos)) as imagen:
                imagen.load()
    except FotoInvalida:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise FotoInvalida("Imagen demasiado grande") from error
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise FotoInvalida("Archivo de imagen inválido o dañado") from error

    return datos, _EXTENSION_POR_FORMATO[formato]


def guardar(datos: bytes, extension: str) -> str:
    """Write `datos` under a UUID filename and return the relative path.

    The write is done to a temporary name and then renamed, so a failed write
    never leaves a half-written file at the final path.
    """
    directorio = settings.photo_storage_path
    try:
        directorio.mkdir(parents=True, exist_ok=True)
        nombre = f"{uuid.uuid4().hex}{extension}"
        destino = directorio / nombre
        temporal = directorio / f".{nombre}.tmp"
        try:
            temporal.write_bytes(datos)
            temporal.replace(destino)
        except OSError:
            # Clean up a partial temp file if the write/rename failed.
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                logger.exception(
                    "No se pudo limpiar el archivo temporal: %s", temporal
                )
            raise
    except OSError as error:
        raise FotoAlmacenamientoError("No fue posible guardar la fotografía") from error
    return nombre


def resolver(ruta_relativa: str) -> Path:
    """Resolve a stored relative path, guaranteeing it stays inside storage.

    Raises `FotoInvalida` if the path escapes the storage directory and
    `FileNotFoundError` if the physical file does not exist.
    """
    base = settings.photo_storage_path.resolve()
    objetivo = (base / ruta_relativa).resolve()
    if base != objetivo and base not in objetivo.parents:
        raise FotoInvalida("Ruta de archivo fuera del almacenamiento autorizado")
    if not objetivo.is_file():
        raise FileNotFoundError(ruta_relativa)
    return objetivo


def eliminar(ruta_relativa: str) -> None:
    """Best-effort compensating delete; logs instead of raising on failure."""
    try:
        base = settings.photo_storage_path.resolve()
        objetivo = (base / ruta_relativa).resolve()
        if base == objetivo or base in objetivo.parents:
            Path(objetivo).unlink(missing_ok=True)
    except OSError:
        logger.exception("No se pudo eliminar la fotografía huérfana: %s", ruta_relativa)
