import random

from sqlalchemy import func, select

from app.models import Visita


def test_crear_visita_ok(cliente, fabrica, auth):
    datos = fabrica.escenario()
    respuesta = cliente.post(
        "/visitas",
        json={
            "id_empresa": datos["empresa"].id_empresa,
            "id_sede": datos["sede"].id_sede,
            "id_tecnico": datos["tecnico"].id_usuario,
            "cantidad_estimada": 12,
            "fecha_programada": "2026-12-01T09:00:00",
            "observaciones": "Primera visita",
        },
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["id_empresa"] == datos["empresa"].id_empresa
    assert cuerpo["id_sede"] == datos["sede"].id_sede
    assert cuerpo["id_tecnico"] == datos["tecnico"].id_usuario
    assert cuerpo["id_comercial"] == datos["comercial"].id_usuario
    assert cuerpo["cantidad_estimada"] == 12
    assert cuerpo["estado"] == "PROGRAMADA"


def test_crear_visita_campos_faltantes(cliente, fabrica, auth):
    datos = fabrica.escenario()
    respuesta = cliente.post(
        "/visitas",
        json={
            "id_empresa": datos["empresa"].id_empresa,
            "id_tecnico": datos["tecnico"].id_usuario,
        },
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 400, respuesta.text
    detalle = respuesta.json()["detail"]
    assert "id_sede" in detalle
    assert "cantidad_estimada" in detalle


def test_crear_visita_requiere_comercial(cliente, fabrica, auth):
    datos = fabrica.escenario()
    respuesta = cliente.post(
        "/visitas",
        json={
            "id_empresa": datos["empresa"].id_empresa,
            "id_sede": datos["sede"].id_sede,
            "id_tecnico": datos["tecnico"].id_usuario,
            "cantidad_estimada": 5,
        },
        headers=auth(datos["tecnico"]),
    )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "Rol no autorizado"


def test_cantidad_estimada_no_se_reescribe(cliente, fabrica, auth, db):
    datos = fabrica.escenario()
    creada = cliente.post(
        "/visitas",
        json={
            "id_empresa": datos["empresa"].id_empresa,
            "id_sede": datos["sede"].id_sede,
            "id_tecnico": datos["tecnico"].id_usuario,
            "cantidad_estimada": 7,
        },
        headers=auth(datos["comercial"]),
    ).json()

    respuesta = cliente.put(
        f"/visitas/{creada['id_visita']}",
        json={"cantidad_estimada": 99, "estado": "EN_CURSO", "observaciones": "En campo"},
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["cantidad_estimada"] == 7
    assert cuerpo["estado"] == "EN_CURSO"
    assert cuerpo["observaciones"] == "En campo"

    visita = db.get(Visita, creada["id_visita"])
    db.refresh(visita)
    assert visita.cantidad_estimada == 7


def test_visita_inexistente_da_404(cliente, fabrica, auth):
    datos = fabrica.escenario()
    respuesta = cliente.get("/visitas/999999", headers=auth(datos["comercial"]))
    assert respuesta.status_code == 404


def test_tecnico_ajeno_no_puede_leer_visita(cliente, fabrica, auth):
    datos = fabrica.escenario()
    otro_tecnico = fabrica.usuario("TECNICO")

    respuesta = cliente.get(
        f"/visitas/{datos['visita'].id_visita}",
        headers=auth(otro_tecnico),
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No autorizado para esta visita"


def test_eliminar_visita_con_sillas_devuelve_409(cliente, fabrica, auth):
    datos = fabrica.escenario()
    fabrica.silla(datos["visita"], datos["empleado"])

    respuesta = cliente.delete(
        f"/visitas/{datos['visita'].id_visita}",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 409


def test_eliminar_visita_sin_sillas(cliente, fabrica, auth, db):
    datos = fabrica.escenario()

    respuesta = cliente.delete(
        f"/visitas/{datos['visita'].id_visita}",
        headers=auth(datos["comercial"]),
    )

    assert respuesta.status_code == 204
    restantes = db.scalar(
        select(func.count())
        .select_from(Visita)
        .where(Visita.id_visita == datos["visita"].id_visita)
    )
    assert restantes == 0


def test_tecnico_solo_ve_sus_visitas(cliente, fabrica, auth, db):
    """Property 3: a technician sees exactly the visits assigned to them.

    120 visits are distributed at random among 6 technicians, so the assertion
    covers the property over 120 randomised data points.
    """
    generador = random.Random(20261125)

    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    tecnicos = [fabrica.usuario("TECNICO") for _ in range(6)]

    esperado: dict[int, set[int]] = {tecnico.id_usuario: set() for tecnico in tecnicos}
    for _ in range(120):
        tecnico = generador.choice(tecnicos)
        visita = fabrica.visita(empresa, sede, comercial, tecnico)
        esperado[tecnico.id_usuario].add(visita.id_visita)

    vistos: set[int] = set()
    for tecnico in tecnicos:
        respuesta = cliente.get("/visitas", headers=auth(tecnico))
        assert respuesta.status_code == 200, respuesta.text
        obtenidos = {visita["id_visita"] for visita in respuesta.json()}
        assert obtenidos == esperado[tecnico.id_usuario]
        assert vistos.isdisjoint(obtenidos)
        vistos |= obtenidos

    total = len(db.scalars(select(Visita)).all())
    assert vistos == {visita.id_visita for visita in db.scalars(select(Visita)).all()}
    assert total == 120


def test_admin_cliente_ve_solo_las_visitas_de_su_empresa(cliente, fabrica, auth):
    """El ADMIN_CLIENTE ve las visitas de su empresa y solo esas (R4).

    Empresa A (la suya) tiene una visita; empresa B tiene otra. El admin cliente
    de A debe recibir 200 con la visita de A y nunca la de B.
    """
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    tecnico = fabrica.usuario("TECNICO")

    empresa_a = fabrica.empresa("Empresa A")
    sede_a = fabrica.sede(empresa_a)
    visita_a = fabrica.visita(empresa_a, sede_a, comercial, tecnico)

    empresa_b = fabrica.empresa("Empresa B")
    sede_b = fabrica.sede(empresa_b)
    visita_b = fabrica.visita(empresa_b, sede_b, comercial, tecnico)

    admin_cliente = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa_a)

    respuesta = cliente.get("/visitas", headers=auth(admin_cliente))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    ids = {visita["id_visita"] for visita in cuerpo}
    assert ids == {visita_a.id_visita}
    assert visita_b.id_visita not in ids
    # Los nombres de sede y técnico vienen resueltos.
    fila = next(v for v in cuerpo if v["id_visita"] == visita_a.id_visita)
    assert fila["sede_nombre"] == sede_a.nombre
    assert fila["tecnico_nombre"] == tecnico.nombre


def test_admin_cliente_sin_empresa_lista_vacia(cliente, fabrica, auth):
    """Un ADMIN_CLIENTE sin empresa resuelta recibe 200 con lista vacía."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    tecnico = fabrica.usuario("TECNICO")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    fabrica.visita(empresa, sede, comercial, tecnico)

    admin_sin_empresa = fabrica.usuario("ADMIN_CLIENTE")  # empresa=None

    respuesta = cliente.get("/visitas", headers=auth(admin_sin_empresa))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


def test_comercial_ve_todas_las_visitas(cliente, fabrica, auth):
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    tecnicos = [fabrica.usuario("TECNICO") for _ in range(3)]

    creadas = {
        fabrica.visita(empresa, sede, comercial, tecnico).id_visita
        for tecnico in tecnicos
    }

    respuesta = cliente.get("/visitas", headers=auth(comercial))
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert {visita["id_visita"] for visita in cuerpo} == creadas
    # El nombre de la sede viene resuelto para todas (comparten sede).
    assert all(v["sede_nombre"] == sede.nombre for v in cuerpo)
    nombres_tecnico = {t.id_usuario: t.nombre for t in tecnicos}
    assert all(
        v["tecnico_nombre"] == nombres_tecnico[v["id_tecnico"]] for v in cuerpo
    )


def test_listar_visitas_resuelve_nombre_para_tecnico(cliente, fabrica, auth):
    """El TECNICO también recibe sede_nombre y tecnico_nombre resueltos."""
    datos = fabrica.escenario()
    respuesta = cliente.get("/visitas", headers=auth(datos["tecnico"]))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    fila = next(v for v in cuerpo if v["id_visita"] == datos["visita"].id_visita)
    assert fila["sede_nombre"] == datos["sede"].nombre
    assert fila["tecnico_nombre"] == datos["tecnico"].nombre


def test_finalizar_visita_tecnico_dueno(cliente, fabrica, auth):
    """El técnico dueño marca su visita como FINALIZADA (HU-28)."""
    datos = fabrica.escenario()
    respuesta = cliente.put(
        f"/visitas/{datos['visita'].id_visita}/finalizar",
        headers=auth(datos["tecnico"]),
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "FINALIZADA"


def test_finalizar_visita_tecnico_ajeno_da_403(cliente, fabrica, auth):
    """Un técnico que no es el asignado no puede finalizar la visita."""
    datos = fabrica.escenario()
    otro = fabrica.usuario("TECNICO")
    respuesta = cliente.put(
        f"/visitas/{datos['visita'].id_visita}/finalizar",
        headers=auth(otro),
    )
    assert respuesta.status_code == 403


def test_finalizar_visita_rol_no_tecnico_da_403(cliente, fabrica, auth):
    """El comercial usa su propio PUT; este endpoint es solo del técnico."""
    datos = fabrica.escenario()
    respuesta = cliente.put(
        f"/visitas/{datos['visita'].id_visita}/finalizar",
        headers=auth(datos["comercial"]),
    )
    assert respuesta.status_code == 403


def test_finalizar_visita_inexistente_da_404(cliente, fabrica, auth):
    """Finalizar una visita que no existe responde 404."""
    tecnico = fabrica.usuario("TECNICO")
    respuesta = cliente.put("/visitas/999999/finalizar", headers=auth(tecnico))
    assert respuesta.status_code == 404
