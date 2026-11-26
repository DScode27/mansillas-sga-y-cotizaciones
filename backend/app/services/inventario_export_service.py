"""Lógica de negocio de la consulta y exportación de inventario (HU-11, R5-R7).

El router (`app/routers/inventario.py`) solo traduce HTTP y aplica RBAC; aquí
viven la consulta del inventario con el alcance por rol y la generación de los
archivos de exportación.

El alcance multiempresa se decide por rol: `COMERCIAL_MANSILLAS` ve todas las
empresas; `ADMIN_CLIENTE` solo su propia empresa (`id_empresa`). El router pasa
`rol` e `id_empresa` del usuario autenticado; el service nunca los infiere de la
petición.
"""

from __future__ import annotations

import csv
import io

from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings

# Encabezados del archivo de exportación, en orden fijo (R7.4). La consulta
# devuelve un dict por silla con estas claves más `id_silla`.
ENCABEZADOS = (
    "empresa",
    "sede",
    "departamento",
    "empleado",
    "cargo",
    "codigo_qr",
    "estado",
)

# Tipo de contenido por formato admitido (R7.5).
MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class FormatoNoAdmitido(Exception):
    """El formato solicitado no es `csv` ni `xlsx` (→ 400) (R7.3).

    El mensaje enumera los formatos admitidos para que el router lo devuelva al
    cliente tal cual.
    """

    def __init__(self) -> None:
        super().__init__(
            "Formato no admitido; los formatos admitidos son: "
            + ", ".join(MEDIA_TYPES)
        )


def consultar_inventario(
    db: Session, *, rol: str, id_empresa: int | None
) -> list[dict]:
    """Devuelve el inventario de sillas dentro del alcance del rol.

    Une `silla` con `empresa`, `sede`, `departamento` y `empleado` para traer,
    por cada silla, su empresa, sede, departamento, empleado, cargo, código QR y
    estado (R6.1). El alcance depende del rol:

    - `COMERCIAL_MANSILLAS`: todas las empresas (R5.3).
    - `ADMIN_CLIENTE`: únicamente las sillas de `id_empresa` (R5.4).

    Devuelve una lista de dicts con las claves de `ENCABEZADOS` más `id_silla`.
    Si no hay sillas en el alcance autorizado, devuelve una lista vacía (R6.2).
    """
    schema = settings.db_schema

    consulta = f"""
        SELECT s.id_silla,
               e.nombre  AS empresa,
               se.nombre AS sede,
               d.nombre  AS departamento,
               emp.nombre AS empleado,
               s.cargo,
               s.codigo_qr,
               s.estado
        FROM {schema}.silla AS s
        JOIN {schema}.empresa AS e
            ON e.id_empresa = s.id_empresa
        JOIN {schema}.sede AS se
            ON se.id_empresa = s.id_empresa
           AND se.id_sede = s.id_sede
        JOIN {schema}.departamento AS d
            ON d.id_empresa = s.id_empresa
           AND d.id_sede = s.id_sede
           AND d.id_departamento = s.id_departamento
        JOIN {schema}.empleado AS emp
            ON emp.id_empresa = s.id_empresa
           AND emp.id_empleado = s.id_empleado
    """

    parametros: dict[str, object] = {}
    # El ADMIN_CLIENTE solo ve su propia empresa; el COMERCIAL_MANSILLAS ve todo.
    if rol == "ADMIN_CLIENTE":
        consulta += " WHERE s.id_empresa = :id_empresa"
        parametros["id_empresa"] = id_empresa

    consulta += " ORDER BY s.id_silla"

    filas = db.execute(text(consulta), parametros).mappings().all()
    return [dict(fila) for fila in filas]


def _valor_celda(valor: object) -> str:
    """Normaliza el valor de una celda a texto para la exportación.

    Un valor ausente (`None`) se escribe como cadena vacía; el resto se
    convierte con `str`, de modo que ambos formatos reciben siempre texto.
    """
    return "" if valor is None else str(valor)


def exportar(filas: list[dict], formato: str) -> tuple[bytes, str]:
    """Genera el archivo de exportación y devuelve `(contenido, media_type)`.

    El archivo siempre comienza con la fila de encabezados `ENCABEZADOS` (R7.4),
    seguida de una fila de datos por cada ítem del inventario, con los valores en
    el orden de `ENCABEZADOS`. El `media_type` devuelto corresponde al formato
    (R7.5).

    - `csv`: se construye con el módulo estándar `csv` (R7.1).
    - `xlsx`: se construye con `openpyxl` sobre un buffer en memoria (R7.2).

    Lanza `FormatoNoAdmitido` si `formato` no es `csv` ni `xlsx` (R7.3).
    """
    if formato not in MEDIA_TYPES:
        raise FormatoNoAdmitido()

    if formato == "csv":
        buffer = io.StringIO()
        escritor = csv.writer(buffer)
        escritor.writerow(ENCABEZADOS)
        for fila in filas:
            escritor.writerow([_valor_celda(fila.get(col)) for col in ENCABEZADOS])
        contenido = buffer.getvalue().encode("utf-8")
        return contenido, MEDIA_TYPES["csv"]

    # formato == "xlsx"
    libro = Workbook()
    hoja = libro.active
    hoja.append(list(ENCABEZADOS))
    for fila in filas:
        hoja.append([_valor_celda(fila.get(col)) for col in ENCABEZADOS])
    buffer_bytes = io.BytesIO()
    libro.save(buffer_bytes)
    return buffer_bytes.getvalue(), MEDIA_TYPES["xlsx"]
