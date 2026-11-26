"""Router del inventario de sillas y su exportación (HU-11, R5-R7).

Solo traduce HTTP y aplica RBAC; la consulta con alcance por rol y la
generación de los archivos viven en `inventario_export_service`. El rol y la
empresa provienen del usuario autenticado (`CurrentUser`), nunca de la petición.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import CurrentUser, require_role
from app.schemas import InventarioItemOut
from app.services.inventario_export_service import (
    FormatoNoAdmitido,
    consultar_inventario,
    exportar,
)

router = APIRouter(prefix="/inventario", tags=["inventario"])

# Ambos roles con visibilidad de inventario; el alcance concreto lo decide el
# service a partir del rol del usuario (R5.1, R5.3, R5.4).
InventarioUser = Annotated[
    CurrentUser, Depends(require_role("COMERCIAL_MANSILLAS", "ADMIN_CLIENTE"))
]


@router.get("/", response_model=list[InventarioItemOut])
def listar_inventario(
    db: Annotated[Session, Depends(get_db)],
    user: InventarioUser,
) -> list[dict]:
    """Devuelve el inventario dentro del alcance del rol (R5.3, R5.4, R6.1).

    `COMERCIAL_MANSILLAS` ve todas las empresas; `ADMIN_CLIENTE` solo la suya.
    Si no hay sillas en el alcance, devuelve 200 con una lista vacía (R6.2).
    """
    return consultar_inventario(db, rol=user.rol, id_empresa=user.empresa_id)


@router.get("/exportar")
def exportar_inventario(
    formato: Literal["csv", "xlsx"],
    db: Annotated[Session, Depends(get_db)],
    user: InventarioUser,
) -> Response:
    """Exporta el inventario del alcance del rol como `csv` o `xlsx` (R7).

    Reusa la consulta con alcance por rol y delega la generación al service,
    que devuelve el contenido y su `media_type` (R7.5). El archivo se envía como
    descarga vía `Content-Disposition`. Un formato no admitido se traduce a 400
    con el mensaje que enumera los formatos válidos (R7.3).
    """
    filas = consultar_inventario(db, rol=user.rol, id_empresa=user.empresa_id)

    try:
        contenido, media_type = exportar(filas, formato)
    except FormatoNoAdmitido as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None

    return Response(
        content=contenido,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="inventario.{formato}"'
        },
    )
