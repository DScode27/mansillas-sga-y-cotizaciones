"""Endpoint de carga masiva de empleados por Excel (HU-19, R1-R3).

Capa HTTP delgada: protege el endpoint con RBAC (`ADMIN_CLIENTE`), valida la
extensión del archivo antes de leerlo y delega todo el procesamiento al service
`carga_excel_service`. El aislamiento multiempresa es estructural: el
`id_empresa` sale siempre del `ADMIN_CLIENTE` autenticado (`user.empresa_id`),
nunca del archivo.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, require_role
from ..schemas import ReporteCargaOut
from ..services import carga_excel_service
from ..services.carga_excel_service import (
    ArchivoVacio,
    ColumnasFaltantes,
    FormatoInvalido,
)

router = APIRouter(prefix="/carga-masiva", tags=["carga-masiva"])

EXTENSION_ESPERADA = ".xlsx"


@router.post("/empleados", response_model=ReporteCargaOut)
async def cargar_empleados(
    archivo: UploadFile,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("ADMIN_CLIENTE"))],
) -> ReporteCargaOut:
    """Procesa un `.xlsx` de empleados y devuelve el Reporte_Resultado (R1-R3).

    El RBAC de `require_role("ADMIN_CLIENTE")` cubre 401 (sin sesión) y 403 (rol
    distinto). Se valida la extensión `.xlsx` antes de leer el contenido (400 si
    no es compatible) y se traducen las validaciones de formato del service
    (`FormatoInvalido`, `ColumnasFaltantes`, `ArchivoVacio`) a HTTP 400.
    """
    nombre_archivo = archivo.filename or ""
    if not nombre_archivo.lower().endswith(EXTENSION_ESPERADA):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Formato no compatible: se requiere un archivo .xlsx",
        )

    contenido = await archivo.read()

    try:
        resultado = carga_excel_service.procesar_carga(
            db,
            id_empresa=user.empresa_id,
            id_usuario=user.id,
            nombre_archivo=nombre_archivo,
            contenido=contenido,
        )
    except ColumnasFaltantes as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
    except (FormatoInvalido, ArchivoVacio) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None

    return ReporteCargaOut.model_validate(resultado)
