"""Lógica de negocio del listado de empleados por empresa (Fase 4, R9).

El router (`app/routers/empleados.py`) solo traduce HTTP y aplica RBAC; aquí vive
la consulta parametrizada con `text()` sobre el esquema configurado.

El alcance multiempresa se decide por rol (como `inventario_export_service` y
`permisos_service`): los roles internos (`COMERCIAL_MANSILLAS`, `TECNICO`) listan
los empleados de cualquier empresa; el `ADMIN_CLIENTE` solo los de su propia
empresa. El router aplica el aislamiento antes de llamar aquí; el service filtra
por `id_empresa` con orden determinista.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings


class SedeNoEncontrada(Exception):
    """La sede no existe en la empresa indicada (→ 400).

    La FK compuesta `(id_empresa, id_sede)` exige que la sede pertenezca a la
    empresa; se valida antes del INSERT para dar un error claro en vez de un
    fallo de integridad.
    """


class DepartamentoNoEncontrado(Exception):
    """El departamento no existe en la empresa y sede indicadas (→ 400).

    La FK compuesta `(id_empresa, id_departamento)` exige que el departamento
    pertenezca a la empresa; además se comprueba que cuelgue de la sede elegida,
    para no aceptar combinaciones sede/departamento incoherentes.
    """


class DocumentoEnUso(Exception):
    """Ya existe un empleado con ese documento en la empresa (→ 409).

    Corresponde a la restricción `UNIQUE (id_empresa, documento)` del SQL.
    """


def listar_empleados(db: Session, *, id_empresa: int) -> list[dict]:
    """Devuelve los empleados de `id_empresa`, ordenados por `id_empleado`.

    Consulta parametrizada con `text()` filtrando por `id_empresa`. Si la empresa
    no existe (o no tiene empleados), devuelve una lista vacía.
    """
    schema = settings.db_schema

    filas = db.execute(
        text(
            f"""
            SELECT id_empleado, id_empresa, id_sede, id_departamento,
                   nombre, documento, correo, cargo, activo
            FROM {schema}.empleado
            WHERE id_empresa = :id_empresa
            ORDER BY id_empleado
            """
        ),
        {"id_empresa": id_empresa},
    ).mappings().all()

    return [dict(fila) for fila in filas]


def crear_empleado(
    db: Session,
    *,
    id_empresa: int,
    id_sede: int,
    id_departamento: int,
    nombre: str,
    cargo: str,
    documento: str | None,
    correo: str | None,
) -> dict:
    """Crea un empleado en una empresa y devuelve sus columnas (`EmpleadoOut`).

    El `id_empresa` viene de la ruta (el cliente lo elige de un desplegable, no
    lo digita); `id_sede` e `id_departamento` llegan del cuerpo porque son los
    desplegables encadenados de la pantalla. Antes del INSERT valida:

    - que la sede exista en la empresa (`SedeNoEncontrada`, por la FK compuesta
      `(id_empresa, id_sede)`);
    - que el departamento exista en la empresa y cuelgue de esa sede
      (`DepartamentoNoEncontrado`, por la FK compuesta
      `(id_empresa, id_departamento)` más la coherencia sede/departamento);
    - que el documento, si viene, no esté ya usado en la empresa
      (`DocumentoEnUso`, por `UNIQUE (id_empresa, documento)`).

    Inserta con `activo = TRUE` (default del SQL) y confirma con `db.commit()`
    porque `get_db` revierte al cerrar la petición.

    Raises SedeNoEncontrada, DepartamentoNoEncontrado, DocumentoEnUso.
    """
    schema = settings.db_schema

    sede = db.execute(
        text(
            f"""
            SELECT 1 FROM {schema}.sede
            WHERE id_empresa = :id_empresa AND id_sede = :id_sede
            """
        ),
        {"id_empresa": id_empresa, "id_sede": id_sede},
    ).first()
    if sede is None:
        raise SedeNoEncontrada

    departamento = db.execute(
        text(
            f"""
            SELECT 1 FROM {schema}.departamento
            WHERE id_empresa = :id_empresa
              AND id_departamento = :id_departamento
              AND id_sede = :id_sede
            """
        ),
        {
            "id_empresa": id_empresa,
            "id_departamento": id_departamento,
            "id_sede": id_sede,
        },
    ).first()
    if departamento is None:
        raise DepartamentoNoEncontrado

    if documento is not None:
        duplicado = db.execute(
            text(
                f"""
                SELECT 1 FROM {schema}.empleado
                WHERE id_empresa = :id_empresa AND documento = :documento
                """
            ),
            {"id_empresa": id_empresa, "documento": documento},
        ).first()
        if duplicado is not None:
            raise DocumentoEnUso

    fila = db.execute(
        text(
            f"""
            INSERT INTO {schema}.empleado
                (id_empresa, id_sede, id_departamento,
                 nombre, documento, correo, cargo)
            VALUES
                (:id_empresa, :id_sede, :id_departamento,
                 :nombre, :documento, :correo, :cargo)
            RETURNING id_empleado, id_empresa, id_sede, id_departamento,
                      nombre, documento, correo, cargo, activo
            """
        ),
        {
            "id_empresa": id_empresa,
            "id_sede": id_sede,
            "id_departamento": id_departamento,
            "nombre": nombre,
            "documento": documento,
            "correo": correo,
            "cargo": cargo,
        },
    ).mappings().first()
    db.commit()

    return dict(fila)
