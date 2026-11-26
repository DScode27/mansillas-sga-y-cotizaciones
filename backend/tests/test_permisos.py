"""Pruebas unitarias de `permisos_service` (HU-18, RN-5).

Ejercitan el service directamente contra PostgreSQL real usando el fixture `db`
y la `Fabrica` (empresa recién creada con `permiso_qr = 1` por el DEFAULT del
esquema). Cubren la tarea 3.2:

- Actualizar a cada valor válido ({1, 2, 3}) y leer de vuelta exactamente ese
  valor (`actualizar_permiso_qr` + `obtener_permiso_qr`).
- Rechazar valores fuera de {1, 2, 3} con `PermisoInvalido` sin modificar el
  valor almacenado.

No se tocan los endpoints HTTP (eso corresponde a tareas posteriores); aquí se
valida la capa de lectura/actualización sobre `empresa.permiso_qr`.

Requirements: 2.1, 2.2, 2.6
"""

import pytest
from sqlalchemy import text

from app.config import settings
from app.services.permisos_service import (
    PERMISOS_VALIDOS,
    PermisoInvalido,
    actualizar_permiso_qr,
    obtener_permiso_qr,
)


def _permiso_en_bd(db, id_empresa: int) -> int:
    """Lee `empresa.permiso_qr` directamente de la BD (fuente de verdad)."""
    db.expire_all()
    valor = db.execute(
        text(
            f"SELECT permiso_qr FROM {settings.db_schema}.empresa "
            "WHERE id_empresa = :id_empresa"
        ),
        {"id_empresa": id_empresa},
    ).scalar_one()
    return int(valor)


# --- Round-trip: actualizar a cada valor válido y leer de vuelta ------------
# Validates: Requirements 2.1, 2.2
@pytest.mark.parametrize("permiso", PERMISOS_VALIDOS)
def test_actualizar_valido_y_leer_de_vuelta(fabrica, db, permiso):
    empresa = fabrica.empresa()

    # `actualizar_permiso_qr` devuelve el valor guardado (Req 2.2)...
    guardado = actualizar_permiso_qr(db, id_empresa=empresa.id_empresa, permiso=permiso)
    assert guardado == permiso

    # ...y leerlo de vuelta con el service devuelve exactamente ese valor (Req 2.1).
    assert obtener_permiso_qr(db, id_empresa=empresa.id_empresa) == permiso

    # La escritura quedó persistida en la BD (no solo en la sesión).
    assert _permiso_en_bd(db, empresa.id_empresa) == permiso


# Round-trip completo recorriendo los tres niveles sobre la misma empresa:
# cada actualización sobrescribe la anterior y la lectura refleja el último.
# Validates: Requirements 2.1, 2.2
def test_round_trip_secuencial_sobre_la_misma_empresa(fabrica, db):
    empresa = fabrica.empresa()

    for permiso in (2, 3, 1, 2):
        actualizar_permiso_qr(db, id_empresa=empresa.id_empresa, permiso=permiso)
        assert obtener_permiso_qr(db, id_empresa=empresa.id_empresa) == permiso
        assert _permiso_en_bd(db, empresa.id_empresa) == permiso


# --- Rechazo de valores inválidos sin modificar el valor almacenado ---------
# Validates: Requirements 2.6
@pytest.mark.parametrize("permiso_invalido", [0, 4, -1, 5, 100, -10])
def test_rechaza_invalido_sin_modificar_almacenado(fabrica, db, permiso_invalido):
    empresa = fabrica.empresa()

    # Valor de partida conocido (válido) sobre el que verificar la invariante.
    actualizar_permiso_qr(db, id_empresa=empresa.id_empresa, permiso=2)
    antes = _permiso_en_bd(db, empresa.id_empresa)
    assert antes == 2

    # Un valor fuera de {1, 2, 3} lanza `PermisoInvalido` (Req 2.6)...
    with pytest.raises(PermisoInvalido):
        actualizar_permiso_qr(
            db, id_empresa=empresa.id_empresa, permiso=permiso_invalido
        )

    # ...y el valor almacenado no cambia, ni para el service ni en la BD.
    db.rollback()
    assert _permiso_en_bd(db, empresa.id_empresa) == 2
    assert obtener_permiso_qr(db, id_empresa=empresa.id_empresa) == 2


# El rechazo de un valor inválido también se cumple sobre el DEFAULT de la BD
# (empresa recién creada, permiso_qr = 1): no se escribe nada.
# Validates: Requirements 2.6
def test_rechaza_invalido_conserva_default(fabrica, db):
    empresa = fabrica.empresa()
    assert _permiso_en_bd(db, empresa.id_empresa) == 1  # DEFAULT 1 del esquema

    with pytest.raises(PermisoInvalido):
        actualizar_permiso_qr(db, id_empresa=empresa.id_empresa, permiso=0)

    db.rollback()
    assert _permiso_en_bd(db, empresa.id_empresa) == 1
