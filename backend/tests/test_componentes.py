"""Pruebas del checklist de componentes de una silla (HU-08, HU-09).

Este módulo cubre, por ahora, la Property 2 del diseño (round-trip de
persistencia del checklist) ejercitando el service `componentes_service`
directamente: `guardar_checklist` seguido de `obtener_checklist`. Los endpoints
HTTP se añaden en tareas posteriores; esta propiedad valida la capa de upsert y
lectura sobre `silla_componente` + `componente`.

El proyecto aún no incluye `hypothesis` como dependencia, así que la propiedad se
expresa como un test parametrizado que recorre combinaciones relevantes sobre los
cinco componentes del catálogo y los cuatro estados del enum (y la observación
opcional), que es la alternativa prevista en la estrategia de pruebas del diseño.
"""

from itertools import cycle, islice

import pytest
from sqlalchemy import func, select, text

from app.models import SillaComponente
from app.services.componentes_service import (
    ESTADOS_COMPONENTE,
    ChecklistIncompleto,
    guardar_checklist,
    obtener_checklist,
)

# El catálogo `componente` se siembra con exactamente cinco filas desde
# SQLMansillasSIC.sql (GENERATED ALWAYS AS IDENTITY -> ids 1..5).
IDS_CATALOGO = (1, 2, 3, 4, 5)


def _silla(fabrica):
    """Crea una silla lista para evaluar su checklist."""
    datos = fabrica.escenario()
    return fabrica.silla(datos["visita"], datos["empleado"])


def _items(pares):
    """Construye la lista de items del checklist a partir de (id, estado, obs)."""
    return [
        {"id_componente": id_componente, "estado": estado, "observacion": observacion}
        for id_componente, estado, observacion in pares
    ]


# Combinaciones relevantes de (id_componente, estado, observacion) que recorren
# los cinco componentes del catálogo, los cuatro estados del enum, subconjuntos
# parciales y observaciones presentes/ausentes.
def _casos_round_trip():
    casos: list[list[tuple[int, str, str | None]]] = []

    # Un componente, cada estado, con y sin observación.
    for estado in ESTADOS_COMPONENTE:
        casos.append([(1, estado, None)])
        casos.append([(1, estado, f"nota {estado}")])

    # Los cinco componentes, cada uno con un estado distinto rotando el enum.
    estados_rotados = list(islice(cycle(ESTADOS_COMPONENTE), len(IDS_CATALOGO)))
    casos.append(
        [
            (id_componente, estado, f"obs-{id_componente}")
            for id_componente, estado in zip(IDS_CATALOGO, estados_rotados)
        ]
    )

    # Subconjunto parcial del catálogo (solo tres componentes), observación mixta.
    casos.append(
        [
            (2, "BUENO", None),
            (4, "DANADO", "cambiar"),
            (5, "MANTENIMIENTO", ""),
        ]
    )

    # Todos los componentes en el mismo estado, sin observación.
    casos.append([(id_componente, "DANADO", None) for id_componente in IDS_CATALOGO])

    return casos


# Feature: checklist-componentes-silla, Property 2: Round-trip de persistencia
# del checklist (upsert). Para toda silla y toda lista de pares (id_componente
# del catálogo, estado del enum) con observación opcional, tras guardar y luego
# leer el checklist, cada componente enviado aparece exactamente una vez con el
# último estado y la última observación enviados (reenviar el mismo cuerpo no
# crea filas duplicadas ni cambia el resultado).
# Validates: Requirements 1.1, 1.2, 1.3, 4.1
@pytest.mark.parametrize("pares", _casos_round_trip())
def test_round_trip_persistencia_checklist(fabrica, db, pares):
    silla = _silla(fabrica)
    items = _items(pares)

    # Resultado esperado: el último estado/observación por componente, ordenado
    # por id_componente (dedup conservando el último, como hace el upsert).
    esperado = {
        id_componente: (estado, observacion)
        for id_componente, estado, observacion in pares
    }

    # 1. Guardar y leer: cada componente aparece exactamente una vez con su
    #    último estado y observación (Req 1.1, 1.2, 1.3, 4.1).
    guardado = guardar_checklist(db, silla.id_silla, items)
    leido = obtener_checklist(db, silla.id_silla)

    assert guardado == leido  # guardar devuelve el checklist resultante

    ids_leidos = [fila["id_componente"] for fila in leido]
    assert ids_leidos == sorted(set(esperado))  # una fila por componente, sin duplicados
    assert len(ids_leidos) == len(set(ids_leidos))

    por_id = {fila["id_componente"]: fila for fila in leido}
    for id_componente, (estado, observacion) in esperado.items():
        assert por_id[id_componente]["estado"] == estado
        assert por_id[id_componente]["observacion"] == observacion

    db.expire_all()
    filas_bd = db.scalar(
        select(func.count())
        .select_from(SillaComponente)
        .where(SillaComponente.id_silla == silla.id_silla)
    )
    assert filas_bd == len(esperado)

    # 2. Idempotencia: reenviar el mismo cuerpo no crea filas duplicadas ni
    #    cambia el resultado (Req 1.2).
    reenviado = guardar_checklist(db, silla.id_silla, items)
    assert reenviado == leido

    db.expire_all()
    filas_tras_reenvio = db.scalar(
        select(func.count())
        .select_from(SillaComponente)
        .where(SillaComponente.id_silla == silla.id_silla)
    )
    assert filas_tras_reenvio == len(esperado)


# Feature: checklist-componentes-silla, Property 2: Round-trip de persistencia
# del checklist (upsert) — rama de last-write-wins. Reenviar el mismo componente
# con un estado/observación distinto actualiza la fila existente (UNIQUE
# id_silla, id_componente) en lugar de duplicarla.
# Validates: Requirements 1.2, 1.3, 4.1
def test_round_trip_ultimo_estado_gana(fabrica, db):
    silla = _silla(fabrica)

    guardar_checklist(
        db,
        silla.id_silla,
        _items([(1, "BUENO", "inicial"), (2, "MANTENIMIENTO", None)]),
    )
    # Segundo guardado: actualiza el componente 1 y añade el 3; el 2 queda intacto.
    guardar_checklist(
        db,
        silla.id_silla,
        _items([(1, "DANADO", "corregido"), (3, "NO_APLICA", None)]),
    )

    leido = {fila["id_componente"]: fila for fila in obtener_checklist(db, silla.id_silla)}

    assert set(leido) == {1, 2, 3}
    assert (leido[1]["estado"], leido[1]["observacion"]) == ("DANADO", "corregido")
    assert (leido[2]["estado"], leido[2]["observacion"]) == ("MANTENIMIENTO", None)
    assert (leido[3]["estado"], leido[3]["observacion"]) == ("NO_APLICA", None)

    db.expire_all()
    filas_bd = db.scalar(
        select(func.count())
        .select_from(SillaComponente)
        .where(SillaComponente.id_silla == silla.id_silla)
    )
    assert filas_bd == 3


# --- Property 1: equivalencia API <-> vista_estado_mantenimiento ------------
#
# Property 1 se ejercita por el endpoint HTTP PUT/GET /sillas/{id}/componentes,
# comparando el `sugerir_cambio` de la respuesta de la API contra una consulta
# directa a `mansillas.vista_estado_mantenimiento` para la misma silla. Como
# `hypothesis` no es dependencia del proyecto, la propiedad se expresa con casos
# parametrizados que recorren las combinaciones relevantes del umbral > 0.70
# (4/5 DANADO -> true; 3/5 DANADO -> false; 3 DANADO + 1 NO_APLICA sobre 4
# aplicables = 0.75 -> true; todos NO_APLICA -> false), más subconjuntos y
# observaciones mixtas. Cada caso incluye además una edición intermedia que debe
# mantener la equivalencia.


def _pares_a_items(pares):
    """(id, estado) | (id, estado, obs) -> items del cuerpo del endpoint."""
    items = []
    for par in pares:
        id_componente, estado = par[0], par[1]
        observacion = par[2] if len(par) > 2 else None
        items.append(
            {"id_componente": id_componente, "estado": estado, "observacion": observacion}
        )
    return items


def _sugerencia_vista(db, id_silla):
    """Lee el booleano derivado directamente de la vista (fuente de verdad)."""
    db.expire_all()
    fila = db.execute(
        text(
            "SELECT sugerir_cambio "
            "FROM mansillas.vista_estado_mantenimiento "
            "WHERE id_silla = :id"
        ),
        {"id": id_silla},
    ).scalar_one_or_none()
    # La vista agrupa toda silla (LEFT JOIN); sin aplicables devuelve FALSE.
    return bool(fila) if fila is not None else False


# (pares_iniciales, pares_edicion) cubriendo el umbral 0.70 y el recálculo.
_CASOS_EQUIVALENCIA = [
    # 4/5 DANADO (0.80 > 0.70) -> true; editar uno a BUENO -> 3/5 (0.60) -> false.
    (
        [(1, "DANADO"), (2, "DANADO"), (3, "DANADO"), (4, "DANADO"), (5, "BUENO")],
        [(1, "BUENO")],
    ),
    # 3/5 DANADO (0.60 <= 0.70) -> false; editar otro a DANADO -> 4/5 -> true.
    (
        [(1, "DANADO"), (2, "DANADO"), (3, "DANADO"), (4, "BUENO"), (5, "BUENO")],
        [(4, "DANADO")],
    ),
    # 3 DANADO + 1 NO_APLICA sobre 4 aplicables (3/4 = 0.75) -> true;
    # editar el NO_APLICA a DANADO -> 4/5 aplicables (0.80) -> sigue true.
    (
        [(1, "DANADO"), (2, "DANADO"), (3, "DANADO"), (4, "NO_APLICA"), (5, "BUENO")],
        [(4, "DANADO")],
    ),
    # Todos NO_APLICA -> sin aplicables -> false; editar uno a DANADO -> 1/1 -> true.
    (
        [(id_componente, "NO_APLICA") for id_componente in IDS_CATALOGO],
        [(3, "DANADO")],
    ),
    # Subconjunto parcial con observaciones: 2 DANADO de 3 aplicables (0.666) ->
    # false; subir el BUENO a DANADO -> 3/3 (1.0) -> true.
    (
        [(2, "DANADO", "cambiar"), (4, "DANADO", "roto"), (5, "BUENO", "ok")],
        [(5, "DANADO", "tambien roto")],
    ),
    # Checklist vacío implícito: solo BUENO/MANTENIMIENTO, ningún DANADO -> false;
    # mantener sin DANADO tras editar -> false.
    (
        [(1, "BUENO"), (2, "MANTENIMIENTO"), (3, "BUENO")],
        [(2, "BUENO")],
    ),
]


# Feature: checklist-componentes-silla, Property 1: Equivalencia con la vista
# (sugerencia derivada). Para toda silla y todo conjunto de estados de
# componentes aplicados mediante el endpoint de guardado, el valor
# `sugerir_cambio` devuelto por la API SHALL coincidir siempre con
# `vista_estado_mantenimiento.sugerir_cambio` para esa misma silla, incluso
# después de editar cualquier componente.
# Validates: Requirements 4.2, 5.1, 5.2, 5.4, 5.5
@pytest.mark.parametrize("pares_iniciales,pares_edicion", _CASOS_EQUIVALENCIA)
def test_equivalencia_api_vista(cliente, fabrica, auth, db, pares_iniciales, pares_edicion):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    tecnico = datos["tecnico"]

    # 1. Guardar el checklist inicial por el endpoint: el `sugerir_cambio` de la
    #    respuesta PUT coincide con la vista (Req 4.2, 5.1, 5.2).
    respuesta_put = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json={"items": _pares_a_items(pares_iniciales)},
        headers=auth(tecnico),
    )
    assert respuesta_put.status_code == 200, respuesta_put.text
    assert respuesta_put.json()["sugerir_cambio"] == _sugerencia_vista(db, silla.id_silla)

    # 2. La lectura GET también coincide con la vista (misma fuente derivada).
    respuesta_get = cliente.get(
        f"/sillas/{silla.id_silla}/componentes",
        headers=auth(tecnico),
    )
    assert respuesta_get.status_code == 200, respuesta_get.text
    assert respuesta_get.json()["sugerir_cambio"] == _sugerencia_vista(db, silla.id_silla)

    # 3. Edición intermedia de un componente: el recálculo de la API sigue
    #    coincidiendo con la vista tras editar (Req 5.4, 5.5).
    respuesta_edicion = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json={"items": _pares_a_items(pares_edicion)},
        headers=auth(tecnico),
    )
    assert respuesta_edicion.status_code == 200, respuesta_edicion.text
    assert respuesta_edicion.json()["sugerir_cambio"] == _sugerencia_vista(db, silla.id_silla)

    # 4. Y la relectura tras la edición mantiene la equivalencia.
    respuesta_get_final = cliente.get(
        f"/sillas/{silla.id_silla}/componentes",
        headers=auth(tecnico),
    )
    assert respuesta_get_final.status_code == 200, respuesta_get_final.text
    assert respuesta_get_final.json()["sugerir_cambio"] == _sugerencia_vista(db, silla.id_silla)

# --- Property 3: rechazo de estados fuera del enum --------------------------
#
# Property 3 se ejercita por el endpoint HTTP PUT /sillas/{id}/componentes: el
# técnico dueño de la visita intenta guardar un componente con un `estado` que
# no pertenece a {BUENO, MANTENIMIENTO, DANADO, NO_APLICA}. El guardado debe
# responder 400 y no persistir ninguna fila con ese estado inválido. Como
# `hypothesis` no es dependencia del proyecto, la propiedad se expresa con casos
# parametrizados que recorren cadenas fuera del enum: un valor arbitrario
# ("ROTO"), el enum con la caja incorrecta ("bueno"), la cadena vacía (""), la
# variante acentuada que no es el valor del CHECK ("DAÑADO" con Ñ frente a
# "DANADO"), y una etiqueta desconocida ("UNKNOWN").
_ESTADOS_FUERA_DEL_ENUM = ["ROTO", "bueno", "", "DAÑADO", "UNKNOWN"]


# Feature: checklist-componentes-silla, Property 3: Rechazo de estados fuera del
# enum. Para toda cadena de estado que no pertenezca a {BUENO, MANTENIMIENTO,
# DANADO, NO_APLICA}, el guardado SHALL responder 400 y no persistir ninguna
# fila con ese estado.
# Validates: Requirements 2.2
@pytest.mark.parametrize("estado_invalido", _ESTADOS_FUERA_DEL_ENUM)
def test_rechazo_estados_fuera_del_enum(cliente, fabrica, auth, db, estado_invalido):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    tecnico = datos["tecnico"]

    # El técnico dueño intenta guardar un componente del catálogo con un estado
    # que no pertenece al enum: el guardado SHALL responder 400 (Req 2.2).
    respuesta = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json={"items": [{"id_componente": 1, "estado": estado_invalido, "observacion": None}]},
        headers=auth(tecnico),
    )
    assert respuesta.status_code == 400, respuesta.text

    # Y no persiste ninguna fila con ese estado inválido (ni para esta silla ni
    # para ninguna otra): la transacción no debe haber escrito nada.
    db.expire_all()
    filas_con_estado_invalido = db.scalar(
        select(func.count())
        .select_from(SillaComponente)
        .where(SillaComponente.estado == estado_invalido)
    )
    assert filas_con_estado_invalido == 0

    filas_de_la_silla = db.scalar(
        select(func.count())
        .select_from(SillaComponente)
        .where(SillaComponente.id_silla == silla.id_silla)
    )
    assert filas_de_la_silla == 0

# --- Property 4: el técnico ajeno nunca escribe el checklist ----------------
#
# Property 4 se ejercita por el endpoint HTTP PUT /sillas/{id}/componentes: un
# TECNICO cuyo identificador no coincide con `visita.id_tecnico` de la visita de
# la silla intenta registrar o editar el checklist. El guardado SHALL responder
# 403 y dejar el checklist sin cambios (ni filas nuevas, ni estados/observaciones
# alterados). Como `hypothesis` no es dependencia del proyecto, la propiedad se
# expresa con casos parametrizados que recorren varios cuerpos de escritura con
# valores válidos del enum: un único componente, todos los componentes rotando
# el enum, un subconjunto parcial con observaciones y todos en el mismo estado.
# Cada caso parte de un checklist inicial guardado por el técnico dueño, de modo
# que la invariante "sin cambios" se comprueba sobre contenido real.
_PAYLOADS_AJENO = [
    # Un único componente que el ajeno intentaría tocar.
    [(1, "DANADO", "roto")],
    # Todos los componentes del catálogo, rotando el enum.
    [
        (id_componente, estado, f"obs-{id_componente}")
        for id_componente, estado in zip(
            IDS_CATALOGO, islice(cycle(ESTADOS_COMPONENTE), len(IDS_CATALOGO))
        )
    ],
    # Subconjunto parcial con observaciones mixtas.
    [(2, "MANTENIMIENTO", "revisar"), (4, "DANADO", None), (5, "NO_APLICA", "")],
    # Todos los componentes en el mismo estado, sin observación.
    [(id_componente, "BUENO", None) for id_componente in IDS_CATALOGO],
]


def _snapshot_checklist(db, id_silla):
    """Fotografía (id_componente, estado, observacion) del checklist persistido."""
    db.expire_all()
    filas = db.execute(
        select(
            SillaComponente.id_componente,
            SillaComponente.estado,
            SillaComponente.observacion,
        ).where(SillaComponente.id_silla == id_silla)
    ).all()
    return sorted((fila.id_componente, fila.estado, fila.observacion) for fila in filas)


# Feature: checklist-componentes-silla, Property 4: El técnico ajeno nunca
# escribe el checklist. Para todo TECNICO cuyo identificador no coincida con
# `visita.id_tecnico` de la visita de la silla, cualquier intento de registrar o
# editar el checklist SHALL responder 403 y dejar el checklist sin cambios.
# Validates: Requirements 3.1, 3.2, 4.4, 4.5
@pytest.mark.parametrize("payload_ajeno", _PAYLOADS_AJENO)
def test_tecnico_ajeno_no_escribe_checklist(cliente, fabrica, auth, db, payload_ajeno):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    tecnico_duenno = datos["tecnico"]
    tecnico_ajeno = fabrica.usuario("TECNICO")  # otro técnico, no dueño de la visita

    # Estado inicial del checklist, guardado por el técnico dueño, para que la
    # invariante "sin cambios" se verifique sobre contenido real (Req 4.4).
    respuesta_inicial = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json={"items": [
            {"id_componente": 1, "estado": "BUENO", "observacion": "inicial"},
            {"id_componente": 3, "estado": "MANTENIMIENTO", "observacion": None},
        ]},
        headers=auth(tecnico_duenno),
    )
    assert respuesta_inicial.status_code == 200, respuesta_inicial.text

    antes = _snapshot_checklist(db, silla.id_silla)

    # El técnico ajeno intenta registrar/editar el checklist: SHALL responder 403
    # con el mensaje de autorización denegada para esa visita (Req 3.2).
    respuesta_ajeno = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json={"items": _pares_a_items(payload_ajeno)},
        headers=auth(tecnico_ajeno),
    )
    assert respuesta_ajeno.status_code == 403, respuesta_ajeno.text
    assert respuesta_ajeno.json()["detail"] == "No autorizado para esta visita"

    # Y el checklist queda intacto: ni filas nuevas ni estados/observaciones
    # alterados (Req 4.4, 4.5).
    despues = _snapshot_checklist(db, silla.id_silla)
    assert despues == antes

# --- Casos de RBAC por ejemplo (task 6.1) -----------------------------------
#
# Control de acceso de los endpoints del checklist sobre la silla:
#   PUT  /sillas/{id}/componentes  -> escritura, exige TECNICO dueño de la visita
#   GET  /sillas/{id}/componentes  -> lectura, COMERCIAL_MANSILLAS (cualquiera)
#                                     o TECNICO dueño; otros roles 403
# Sin autenticación ambos endpoints responden 401 con WWW-Authenticate: Bearer.
# Se usan únicamente las fixtures existentes (`cliente`, `fabrica`, `auth`).

# Un item válido mínimo para ejercer la escritura del checklist.
_ITEM_VALIDO = {"items": [{"id_componente": 1, "estado": "BUENO", "observacion": None}]}


# (a) El técnico dueño de la visita escribe el checklist -> 200.
# Validates: Requirements 1.4, 3.1
def test_rbac_tecnico_duenno_escribe_200(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])

    respuesta = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json=_ITEM_VALIDO,
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id_silla"] == silla.id_silla
    assert {item["id_componente"] for item in cuerpo["items"]} == {1}


# (b) Un TECNICO que no es dueño de la visita no escribe -> 403.
# Validates: Requirements 3.2, 4.4, 4.5
def test_rbac_tecnico_ajeno_escribe_403(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    tecnico_ajeno = fabrica.usuario("TECNICO")

    respuesta = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json=_ITEM_VALIDO,
        headers=auth(tecnico_ajeno),
    )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "No autorizado para esta visita"


# (c) COMERCIAL_MANSILLAS lee cualquier silla -> 200, pero no escribe -> 403.
# Validates: Requirements 3.1, 3.2, 3.3, 4.3
def test_rbac_comercial_lee_200_escribe_403(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    comercial = datos["comercial"]  # COMERCIAL_MANSILLAS

    # Lectura permitida sobre cualquier silla.
    lectura = cliente.get(
        f"/sillas/{silla.id_silla}/componentes",
        headers=auth(comercial),
    )
    assert lectura.status_code == 200, lectura.text
    assert lectura.json()["id_silla"] == silla.id_silla

    # Escritura denegada: el rol no pasa require_role("TECNICO").
    escritura = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json=_ITEM_VALIDO,
        headers=auth(comercial),
    )
    assert escritura.status_code == 403, escritura.text
    assert escritura.json()["detail"] == "Rol no autorizado"


# (d) Un rol que no es TECNICO ni COMERCIAL_MANSILLAS no lee -> 403.
# Validates: Requirements 3.3, 4.3, 4.4, 4.5
def test_rbac_rol_sin_privilegio_lee_403(cliente, fabrica, auth):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    # Usuario externo del cliente: válido para autenticar, sin privilegio sobre
    # el checklist (la CHECK del SQL exige id_empresa para los roles de cliente).
    externo = fabrica.usuario("ADMIN_CLIENTE", empresa=datos["empresa"])

    respuesta = cliente.get(
        f"/sillas/{silla.id_silla}/componentes",
        headers=auth(externo),
    )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "Rol no autorizado"


# (e) Sin autenticación: PUT y GET responden 401 con WWW-Authenticate: Bearer.
# Validates: Requirements 3.1, 4.3
def test_rbac_sin_auth_401_con_www_authenticate(cliente, fabrica):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])

    for respuesta in (
        cliente.put(f"/sillas/{silla.id_silla}/componentes", json=_ITEM_VALIDO),
        cliente.get(f"/sillas/{silla.id_silla}/componentes"),
    ):
        assert respuesta.status_code == 401, respuesta.text
        assert respuesta.headers.get("WWW-Authenticate") == "Bearer"

# --- Casos de validación de entrada por ejemplo (task 6.2) ------------------
#
# Validación de entrada del endpoint PUT /sillas/{id}/componentes, ejercida por
# el TECNICO dueño de la visita (para que RBAC pase y la petición alcance la
# validación del service `componentes_service.guardar_checklist`). Cubre:
#   Req 2.1  id_componente fuera del catálogo `componente`   -> 404
#   Req 2.2  estado fuera del enum                            -> 400
#   Req 2.3  falta id_componente/estado en un elemento        -> ver nota 400/422
#   Req 2.4  id_silla inexistente                             -> 404
#
# Nota sobre Req 2.3 (distinción 400 vs 422): por decisión de diseño el schema
# `ComponenteItemIn` declara `id_componente: int` y `estado: str` como campos
# REQUERIDOS y no anulables, y el `estado` NO usa `Literal` (para que el enum lo
# valide el service con 400). En consecuencia, cuando un elemento OMITE por
# completo `id_componente` o `estado` (o envía `estado: null`), la barrera que
# responde es la validación de Pydantic de FastAPI -> 422 Unprocessable Entity,
# antes de ejecutar el cuerpo del endpoint. La garantía de 400 con mensaje de
# datos incompletos (`ChecklistIncompleto`) del diseño es una barrera a nivel de
# service, alcanzable al invocar `guardar_checklist` con un item cuyo
# `id_componente`/`estado` es `None`. Se prueban ambos caminos: el 422 del
# contrato HTTP y el 400 `ChecklistIncompleto` del service.

# Item válido reutilizable para construir cuerpos de prueba.
_ITEM_OK = {"id_componente": 1, "estado": "BUENO", "observacion": None}


def _sin_filas_silla(db, id_silla):
    """Cuenta las filas de `silla_componente` persistidas para una silla."""
    db.expire_all()
    return db.scalar(
        select(func.count())
        .select_from(SillaComponente)
        .where(SillaComponente.id_silla == id_silla)
    )


# (a) Estado fuera del enum -> 400 y no persiste nada (Req 2.2).
# Validates: Requirements 2.2
@pytest.mark.parametrize("estado_invalido", ["ROTO", "bueno", "", "DAÑADO", "PENDIENTE"])
def test_validacion_estado_fuera_del_enum_400(cliente, fabrica, auth, db, estado_invalido):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])

    respuesta = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json={"items": [{"id_componente": 1, "estado": estado_invalido, "observacion": None}]},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 400, respuesta.text
    assert _sin_filas_silla(db, silla.id_silla) == 0


# (b) id_componente inexistente en el catálogo -> 404 y no persiste nada (Req 2.1).
# Validates: Requirements 2.1
@pytest.mark.parametrize("id_inexistente", [6, 99, 1000])
def test_validacion_id_componente_inexistente_404(cliente, fabrica, auth, db, id_inexistente):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])

    respuesta = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json={"items": [{"id_componente": id_inexistente, "estado": "BUENO", "observacion": None}]},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 404, respuesta.text
    assert _sin_filas_silla(db, silla.id_silla) == 0


# (c) id_silla inexistente -> 404 (Req 2.4). La silla se carga antes de validar
# el cuerpo; un identificador sin fila responde 404 "No encontrado".
# Validates: Requirements 2.4
@pytest.mark.parametrize("id_silla_inexistente", [1, 404, 9999])
def test_validacion_id_silla_inexistente_404(cliente, fabrica, auth, id_silla_inexistente):
    # Escenario con un técnico válido, pero sin crear la silla objetivo.
    datos = fabrica.escenario()

    respuesta = cliente.put(
        f"/sillas/{id_silla_inexistente}/componentes",
        json={"items": [_ITEM_OK]},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json()["detail"] == "No encontrado"


# (d) Falta `estado` o `id_componente` en el cuerpo HTTP: al ser campos
# requeridos y no anulables del schema, FastAPI/Pydantic responde 422 antes de
# llegar al service, y no persiste nada (Req 2.3, barrera de contrato HTTP).
# Validates: Requirements 2.3
@pytest.mark.parametrize(
    "item_incompleto",
    [
        {"estado": "BUENO"},  # falta id_componente
        {"id_componente": 1},  # falta estado
        {"id_componente": 1, "estado": None},  # estado nulo (campo no anulable)
        {"observacion": "sin claves requeridas"},  # faltan ambos
    ],
)
def test_validacion_item_incompleto_422_por_contrato(cliente, fabrica, auth, db, item_incompleto):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])

    respuesta = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json={"items": [item_incompleto]},
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 422, respuesta.text
    assert _sin_filas_silla(db, silla.id_silla) == 0


# (e) Camino de datos incompletos del service (Req 2.3): invocando
# `guardar_checklist` con un item cuyo `id_componente`/`estado` es None se lanza
# `ChecklistIncompleto`, que el router traduce a 400. Esta es la garantía 400 que
# describe el diseño; verificamos además que no persiste nada.
# Validates: Requirements 2.3
@pytest.mark.parametrize(
    "item_incompleto",
    [
        {"id_componente": None, "estado": "BUENO", "observacion": None},
        {"id_componente": 1, "estado": None, "observacion": None},
        {"estado": "BUENO"},  # id_componente ausente -> get() devuelve None
        {"id_componente": 1},  # estado ausente -> get() devuelve None
    ],
)
def test_validacion_checklist_incompleto_en_service(fabrica, db, item_incompleto):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])

    with pytest.raises(ChecklistIncompleto):
        guardar_checklist(db, silla.id_silla, [item_incompleto])

    assert _sin_filas_silla(db, silla.id_silla) == 0

# --- Casos de la sugerencia de cambio (HU-09) por ejemplo (task 6.3) --------
#
# Sugerencia_Cambio derivada de `vista_estado_mantenimiento` ejercida por el
# endpoint PUT/GET /sillas/{id}/componentes, actuando siempre el TECNICO dueño
# de la visita. La regla (RN-01): `sugerir_cambio` es verdadero cuando
# (DANADO / Componentes_Aplicables) > 0.70, y falso cuando no hay aplicables.
# Un Componente_Aplicable es aquel cuyo estado registrado no es NO_APLICA.
# Cada caso comprueba el booleano tanto en la respuesta del PUT como en el GET
# posterior, y lo contrasta con la lectura directa de la vista para fijar la
# fuente de verdad. El último caso verifica el recálculo dinámico (Req 5.4):
# tras alcanzar `true`, bajar un DANADO a BUENO y releer debe dar `false`.


def _put_checklist(cliente, auth, tecnico, id_silla, pares):
    """PUT del checklist como el técnico dueño; exige 200 y devuelve el cuerpo."""
    respuesta = cliente.put(
        f"/sillas/{id_silla}/componentes",
        json={"items": _pares_a_items(pares)},
        headers=auth(tecnico),
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _get_sugerencia(cliente, auth, tecnico, id_silla):
    """GET del checklist como el técnico dueño; exige 200 y devuelve sugerir_cambio."""
    respuesta = cliente.get(
        f"/sillas/{id_silla}/componentes",
        headers=auth(tecnico),
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["sugerir_cambio"]


# (a) 4 de 5 componentes en DANADO (0.80 > 0.70) -> sugerir_cambio true.
# Validates: Requirements 5.1
def test_sugerencia_cuatro_de_cinco_danado_true(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    tecnico = datos["tecnico"]

    cuerpo = _put_checklist(
        cliente, auth, tecnico, silla.id_silla,
        [(1, "DANADO"), (2, "DANADO"), (3, "DANADO"), (4, "DANADO"), (5, "BUENO")],
    )

    assert cuerpo["sugerir_cambio"] is True
    assert _get_sugerencia(cliente, auth, tecnico, silla.id_silla) is True
    assert _sugerencia_vista(db, silla.id_silla) is True


# (b) 3 de 5 componentes en DANADO (0.60 <= 0.70) -> sugerir_cambio false.
# Validates: Requirements 5.2
def test_sugerencia_tres_de_cinco_danado_false(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    tecnico = datos["tecnico"]

    cuerpo = _put_checklist(
        cliente, auth, tecnico, silla.id_silla,
        [(1, "DANADO"), (2, "DANADO"), (3, "DANADO"), (4, "BUENO"), (5, "BUENO")],
    )

    assert cuerpo["sugerir_cambio"] is False
    assert _get_sugerencia(cliente, auth, tecnico, silla.id_silla) is False
    assert _sugerencia_vista(db, silla.id_silla) is False


# (c) 3 DANADO + 1 NO_APLICA sobre 4 aplicables (3/4 = 0.75 > 0.70) -> true.
# El NO_APLICA no cuenta como aplicable, así que el denominador es 4, no 5.
# Validates: Requirements 5.1
def test_sugerencia_tres_danado_un_no_aplica_sobre_cuatro_true(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    tecnico = datos["tecnico"]

    cuerpo = _put_checklist(
        cliente, auth, tecnico, silla.id_silla,
        [(1, "DANADO"), (2, "DANADO"), (3, "DANADO"), (4, "NO_APLICA"), (5, "BUENO")],
    )

    assert cuerpo["sugerir_cambio"] is True
    assert _get_sugerencia(cliente, auth, tecnico, silla.id_silla) is True
    assert _sugerencia_vista(db, silla.id_silla) is True


# (d) Sin componentes aplicables (los cinco en NO_APLICA) -> sugerir_cambio
# false, porque el denominador de aplicables es cero (Req 5.3).
# Validates: Requirements 5.3
def test_sugerencia_sin_aplicables_false(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    tecnico = datos["tecnico"]

    cuerpo = _put_checklist(
        cliente, auth, tecnico, silla.id_silla,
        [(id_componente, "NO_APLICA") for id_componente in IDS_CATALOGO],
    )

    assert cuerpo["sugerir_cambio"] is False
    assert _get_sugerencia(cliente, auth, tecnico, silla.id_silla) is False
    assert _sugerencia_vista(db, silla.id_silla) is False


# (e) Recálculo dinámico (Req 5.4): tras alcanzar `true` con 4/5 DANADO, bajar
# uno de los DANADO a BUENO deja 3/5 (0.60) y la siguiente lectura devuelve
# `false`. La sugerencia se deriva de la vista en cada consulta, sin persistir.
# Validates: Requirements 5.4, 5.5
def test_sugerencia_recalculo_dinamico_true_a_false(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    tecnico = datos["tecnico"]

    # Estado inicial: 4/5 DANADO -> true.
    cuerpo_inicial = _put_checklist(
        cliente, auth, tecnico, silla.id_silla,
        [(1, "DANADO"), (2, "DANADO"), (3, "DANADO"), (4, "DANADO"), (5, "BUENO")],
    )
    assert cuerpo_inicial["sugerir_cambio"] is True
    assert _get_sugerencia(cliente, auth, tecnico, silla.id_silla) is True

    # Edición: bajar un DANADO a BUENO -> 3/5 (0.60) -> la relectura da false.
    cuerpo_edicion = _put_checklist(
        cliente, auth, tecnico, silla.id_silla,
        [(1, "BUENO")],
    )
    assert cuerpo_edicion["sugerir_cambio"] is False
    assert _get_sugerencia(cliente, auth, tecnico, silla.id_silla) is False
    assert _sugerencia_vista(db, silla.id_silla) is False
