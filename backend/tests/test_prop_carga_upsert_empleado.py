"""Property test P4: el upsert de empleado por identidad no duplica (HU-19).

# Feature: carga-masiva-y-exportacion-inventario, Property 4

**Property 4: El upsert de empleado por identidad no duplica**

*Para todo* empleado identificado por `documento` o `correo`, procesar una fila
con esa identidad cuando el empleado ya existe actualiza la fila existente (el
conteo de empleados de la empresa no cambia) en lugar de crear uno nuevo.

**Validates: Requirements 4.5, 4.6**

Estrategia
----------
Hypothesis genera la *identidad* con la que se vuelve a procesar al empleado
(solo `documento`, solo `correo`, o ambos) y los valores nuevos de `nombre` y
`cargo` con los que debe quedar actualizado. La verificación opera sobre la
lógica del service (`carga_excel_service._upsert_empleado`), usando la base
desechable para los conteos, como indica el diseño.

Por cada ejemplo:

1. Se crea un empleado base invocando `_upsert_empleado` con una identidad única
   (documento y correo distintos por ejemplo). La unicidad por ejemplo evita
   chocar con `UNIQUE (id_empresa, documento)` y con el `correo` global entre
   los ejemplos que comparten la misma empresa de prueba.
2. Se cuenta cuántos empleados tiene la empresa tras esa creación.
3. Se reprocesa una fila con la MISMA identidad (según el campo elegido) pero
   con `nombre`/`cargo` distintos.
4. Se comprueba que el conteo de empleados de la empresa NO cambió (no se creó
   otro empleado), que es la misma fila (mismo `id_empleado`) y que quedó
   actualizada con los datos nuevos.

Las fixtures `db`/`fabrica` tienen ámbito de función y Hypothesis reutiliza sus
instancias entre ejemplos. La empresa/sede/departamento se crean UNA vez (fuera
del `@given`, cacheadas en `_ESTADO`) y se reutilizan; como cada ejemplo usa una
identidad única, la reutilización no provoca colisiones de unicidad. Se suprime
`HealthCheck.function_scoped_fixture` por esa reutilización deliberada.
"""

from __future__ import annotations

import itertools

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select

from app.models import Empleado
from app.services import carga_excel_service as svc

# Contador global: identidad única por ejemplo (documento/correo distintos),
# para no chocar con `UNIQUE (id_empresa, documento)` ni el `correo` global al
# compartir la misma empresa de prueba entre ejemplos.
_SECUENCIA = itertools.count(1)

# Empresa/sede/departamento creados una sola vez por ejecución del test.
_ESTADO: dict = {}

# Texto no vacío para los `nombre`/`cargo` nuevos del reproceso.
_texto = st.text(
    alphabet=st.characters(min_codepoint=65, max_codepoint=90),
    min_size=1,
    max_size=20,
)


def _contar_empleados(db, id_empresa: int) -> int:
    """Número de empleados de la empresa en la base desechable."""
    return db.execute(
        select(func.count())
        .select_from(Empleado)
        .where(Empleado.id_empresa == id_empresa)
    ).scalar_one()


# Feature: carga-masiva-y-exportacion-inventario, Property 4: El upsert de empleado por identidad no duplica
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    identificar_por=st.sampled_from(("documento", "correo", "ambos")),
    nombre_nuevo=_texto,
    cargo_nuevo=_texto,
)
def test_reprocesar_misma_identidad_actualiza_sin_duplicar(
    db,
    fabrica,
    identificar_por,
    nombre_nuevo,
    cargo_nuevo,
):
    """Reprocesar una identidad existente actualiza el empleado sin crear otro.

    Para toda identidad (`documento`, `correo` o ambos), tras crear un empleado
    base y reprocesar una fila con esa misma identidad: el conteo de empleados de
    la empresa no cambia, es la misma fila (mismo `id_empleado`) la que se
    actualiza y queda con los nuevos `nombre`/`cargo` (y `id_sede`/`id_departamento`).

    _Requirements: 4.5, 4.6_
    """
    escenario = _ESTADO.get("escenario")
    if escenario is None:
        empresa = fabrica.empresa("UpsertEmpleado")
        sede = fabrica.sede(empresa)
        departamento = fabrica.departamento(empresa, sede)
        escenario = {
            "id_empresa": empresa.id_empresa,
            "id_sede": sede.id_sede,
            "id_departamento": departamento.id_departamento,
        }
        _ESTADO["escenario"] = escenario

    id_empresa = escenario["id_empresa"]
    id_sede = escenario["id_sede"]
    id_departamento = escenario["id_departamento"]

    # Identidad única por ejemplo.
    n = next(_SECUENCIA)
    documento = f"DOC{n:09d}"
    correo = f"upsert{n}@carga.local"

    # 1) Crear el empleado base con documento y correo informados.
    fila_inicial: dict[str, str | None] = {
        "sede": "S",
        "departamento": "D",
        "nombre": f"Nombre inicial {n}",
        "cargo": f"Cargo inicial {n}",
        "documento": documento,
        "correo": correo,
    }
    empleado = svc._upsert_empleado(
        db, id_empresa, id_sede, id_departamento, fila_inicial
    )
    db.commit()
    id_empleado_original = empleado.id_empleado

    # 2) Conteo de empleados de la empresa tras la creación.
    conteo_antes = _contar_empleados(db, id_empresa)

    # 3) Reprocesar con la MISMA identidad (según el campo elegido) y datos nuevos.
    fila_reproceso: dict[str, str | None] = {
        "sede": "S",
        "departamento": "D",
        "nombre": nombre_nuevo,
        "cargo": cargo_nuevo,
        "documento": None,
        "correo": None,
    }
    if identificar_por in ("documento", "ambos"):
        fila_reproceso["documento"] = documento
    if identificar_por in ("correo", "ambos"):
        fila_reproceso["correo"] = correo

    empleado_reproc = svc._upsert_empleado(
        db, id_empresa, id_sede, id_departamento, fila_reproceso
    )
    db.commit()

    # 4a) No se creó otro empleado: el conteo no cambió y es la misma fila.
    assert _contar_empleados(db, id_empresa) == conteo_antes
    assert empleado_reproc.id_empleado == id_empleado_original

    # 4b) La fila existente quedó actualizada con los datos nuevos.
    db.refresh(empleado_reproc)
    assert empleado_reproc.nombre == nombre_nuevo
    assert empleado_reproc.cargo == cargo_nuevo
    assert empleado_reproc.id_sede == id_sede
    assert empleado_reproc.id_departamento == id_departamento
