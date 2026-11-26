"""Pruebas de la ficha pública ampliada por QR (HU-17).

Cubren las dos ampliaciones de la vista pública (`app/routers/qr.py`), sin auth:

- `GET /qr/silla/{token}` ahora devuelve, además de los datos básicos, el nombre
  de la empresa y de la sede dueñas, el `serial_antiguo` y el estado de los
  componentes (`componentes`), reusando el checklist de la silla. Nunca expone
  datos personales del empleado (RN-3/RN-4).
- `GET /qr/silla/{token}/fotos` lista los `id_fotografia` de la silla y
  `GET /qr/silla/{token}/fotos/{id}` sirve los bytes, resolviendo la silla por
  su `token_publico`. Una foto de otra silla por el mismo endpoint da 404, y un
  token inexistente da 404.

Las fixtures `cliente`, `fabrica`, `db` vienen de `conftest.py`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from app.config import settings
from app.models import Fotografia
from app.services import fotos_storage

# PNG 1x1 mínimo válido (lo que valida/guarda `fotos_storage`).
_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f6f0000000049454e44ae426082"
)


def _token(silla) -> str:
    return str(silla.token_publico)


def _guardar_componentes(cliente, fabrica, silla, datos, items):
    """Guarda el checklist de la silla vía el endpoint del técnico dueño."""
    # El técnico de la visita es quien puede escribir el checklist.
    headers = {"X-Dev-User-Id": str(datos["tecnico"].id_usuario)}
    resp = cliente.put(
        f"/sillas/{silla.id_silla}/componentes",
        json={"items": items},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


def test_ficha_publica_incluye_empresa_sede_serial_y_componentes(cliente, fabrica):
    """La ficha pública trae empresa, sede, serial y el estado de componentes."""
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"], serial_antiguo="OLD-1")

    items = [
        {"id_componente": 1, "estado": "BUENO"},
        {"id_componente": 2, "estado": "MANTENIMIENTO"},
        {"id_componente": 3, "estado": "BUENO"},
        {"id_componente": 4, "estado": "DANADO", "observacion": "roto"},
        {"id_componente": 5, "estado": "NO_APLICA"},
    ]
    _guardar_componentes(cliente, fabrica, silla, datos, items)

    respuesta = cliente.get(f"/qr/silla/{_token(silla)}")
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()

    assert cuerpo["empresa"] == datos["empresa"].nombre
    assert cuerpo["sede"] == datos["sede"].nombre
    assert cuerpo["serial_antiguo"] == "OLD-1"

    componentes = cuerpo["componentes"]
    assert len(componentes) == 5
    por_id = {c["id_componente"]: c for c in componentes}
    assert por_id[2]["estado"] == "MANTENIMIENTO"
    assert por_id[4]["estado"] == "DANADO"
    assert por_id[4]["observacion"] == "roto"
    # Cada componente trae su nombre del catálogo.
    assert all(c["nombre"] for c in componentes)


def test_ficha_publica_no_expone_datos_personales_del_empleado(cliente, fabrica):
    """La ficha pública nunca incluye nombre/documento/correo del empleado."""
    datos = fabrica.escenario()
    empleado = datos["empleado"]
    silla = fabrica.silla(datos["visita"], empleado)

    respuesta = cliente.get(f"/qr/silla/{_token(silla)}")
    assert respuesta.status_code == 200, respuesta.text
    crudo = respuesta.text
    assert empleado.nombre not in crudo
    assert empleado.documento not in crudo
    assert empleado.correo not in crudo


def _crear_foto(db, silla) -> Fotografia:
    """Guarda un PNG real en el almacenamiento y registra su fila `fotografia`."""
    nombre = fotos_storage.guardar(_PNG_1X1, ".png")
    foto = Fotografia(id_silla=silla.id_silla, ruta_archivo=nombre)
    db.add(foto)
    db.commit()
    db.refresh(foto)
    return foto


def test_listar_fotos_publicas_por_token(cliente, fabrica, db):
    """`GET /qr/silla/{token}/fotos` lista los id_fotografia de la silla."""
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    foto = _crear_foto(db, silla)
    try:
        respuesta = cliente.get(f"/qr/silla/{_token(silla)}/fotos")
        assert respuesta.status_code == 200, respuesta.text
        ids = [f["id_fotografia"] for f in respuesta.json()]
        assert ids == [foto.id_fotografia]
    finally:
        fotos_storage.eliminar(foto.ruta_archivo)


def test_servir_foto_publica_por_token(cliente, fabrica, db):
    """`GET /qr/silla/{token}/fotos/{id}` devuelve los bytes de la imagen."""
    datos = fabrica.escenario()
    silla = fabrica.silla(datos["visita"], datos["empleado"])
    foto = _crear_foto(db, silla)
    try:
        respuesta = cliente.get(
            f"/qr/silla/{_token(silla)}/fotos/{foto.id_fotografia}"
        )
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.headers["content-type"] == "image/png"
        assert respuesta.content == _PNG_1X1
    finally:
        fotos_storage.eliminar(foto.ruta_archivo)


def test_foto_de_otra_silla_por_token_da_404(cliente, fabrica, db):
    """El token de una silla no sirve una foto que pertenece a otra silla."""
    datos = fabrica.escenario()
    silla_a = fabrica.silla(datos["visita"], datos["empleado"])
    silla_b = fabrica.silla(datos["visita"], datos["empleado"], serial_antiguo="B")
    foto_b = _crear_foto(db, silla_b)
    try:
        # Se pide la foto de B usando el token de A → 404.
        respuesta = cliente.get(
            f"/qr/silla/{_token(silla_a)}/fotos/{foto_b.id_fotografia}"
        )
        assert respuesta.status_code == 404
    finally:
        fotos_storage.eliminar(foto_b.ruta_archivo)


def test_fotos_publicas_token_inexistente_da_404(cliente):
    """Un token que no resuelve a ninguna silla da 404 en ambos endpoints."""
    token = uuid.uuid4()
    assert cliente.get(f"/qr/silla/{token}/fotos").status_code == 404
    assert cliente.get(f"/qr/silla/{token}/fotos/1").status_code == 404
