"""Tests de ejemplo del inventario de sillas y su exportación (HU-11, R5-R7).

Siguen el patrón de `conftest.py`/`test_sillas.py`: usan las fixtures `cliente`,
`fabrica`, `auth` y `db`. El inventario se materializa con la fábrica (empresa →
sede → departamento → empleado → comercial → técnico → visita → sillas) y las
peticiones se hacen contra el stub de autenticación de desarrollo
(`X-Dev-User-Id`). Omitir ese header simula una petición sin sesión (401).

Rutas cubiertas:
- `GET /inventario/`         — listado con alcance por rol (R5.1, R5.3, R5.4, R6).
- `GET /inventario/exportar` — exportación `csv`/`xlsx` (R7).
"""

import csv
import io

from openpyxl import load_workbook

from app.services.inventario_export_service import (
    ENCABEZADOS,
    MEDIA_TYPES,
    FormatoNoAdmitido,
    exportar,
)


def _crear_sillas(fabrica, escenario, cantidad):
    """Crea `cantidad` sillas en el escenario y devuelve sus id_silla."""
    ids = []
    for _ in range(cantidad):
        silla = fabrica.silla(escenario["visita"], escenario["empleado"])
        ids.append(silla.id_silla)
    return ids


def _admin(fabrica, empresa):
    """Usuario ADMIN_CLIENTE atado a una empresa (alcance de su empresa)."""
    return fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)


# --- GET /inventario/ : autenticación y autorización -------------------------


def test_listar_inventario_sin_sesion_da_401(cliente):
    """Sin cabecera de sesión, el listado responde 401 (R5.1)."""
    respuesta = cliente.get("/inventario/")

    assert respuesta.status_code == 401, respuesta.text


def test_listar_inventario_rol_no_autorizado_da_403(cliente, fabrica, auth):
    """Un rol fuera del alcance (TECNICO) recibe 403 (R5.2)."""
    tecnico = fabrica.usuario("TECNICO")

    respuesta = cliente.get("/inventario/", headers=auth(tecnico))

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "Rol no autorizado"


def test_listar_inventario_empleado_cliente_da_403(cliente, fabrica, auth):
    """El EMPLEADO_CLIENTE tampoco puede ver el inventario (R5.2)."""
    empresa = fabrica.empresa()
    empleado_cliente = fabrica.usuario("EMPLEADO_CLIENTE", empresa=empresa)

    respuesta = cliente.get("/inventario/", headers=auth(empleado_cliente))

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "Rol no autorizado"


# --- GET /inventario/ : inventario vacío -------------------------------------


def test_listar_inventario_vacio_da_200(cliente, fabrica, auth):
    """Sin sillas en el alcance, el comercial recibe 200 con lista vacía (R6.2)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.get("/inventario/", headers=auth(comercial))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


def test_listar_inventario_admin_sin_sillas_da_200_vacio(cliente, fabrica, auth):
    """El ADMIN_CLIENTE de una empresa sin sillas recibe 200 con lista vacía (R6.2)."""
    empresa = fabrica.empresa()
    admin = _admin(fabrica, empresa)

    respuesta = cliente.get("/inventario/", headers=auth(admin))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


# --- GET /inventario/ : alcance por rol --------------------------------------


def test_comercial_ve_todas_las_empresas(cliente, fabrica, auth):
    """`COMERCIAL_MANSILLAS` ve el inventario de todas las empresas (R5.3)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    escenario_a = fabrica.escenario()
    escenario_b = fabrica.escenario()
    ids_a = _crear_sillas(fabrica, escenario_a, 2)
    ids_b = _crear_sillas(fabrica, escenario_b, 3)

    respuesta = cliente.get("/inventario/", headers=auth(comercial))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    devueltas = {fila["id_silla"] for fila in cuerpo}
    assert devueltas == set(ids_a) | set(ids_b)

    # Cada ítem trae las columnas del inventario (R6.1).
    for fila in cuerpo:
        for columna in ("id_silla", *ENCABEZADOS):
            assert columna in fila


def test_admin_cliente_ve_solo_su_empresa(cliente, fabrica, auth):
    """`ADMIN_CLIENTE` ve únicamente las sillas de su propia empresa (R5.4)."""
    escenario_propio = fabrica.escenario()
    escenario_ajeno = fabrica.escenario()
    ids_propios = _crear_sillas(fabrica, escenario_propio, 2)
    _crear_sillas(fabrica, escenario_ajeno, 3)

    admin = _admin(fabrica, escenario_propio["empresa"])

    respuesta = cliente.get("/inventario/", headers=auth(admin))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    devueltas = {fila["id_silla"] for fila in cuerpo}
    assert devueltas == set(ids_propios)

    # Todas las filas pertenecen a la empresa del admin (aislamiento).
    nombre_empresa = escenario_propio["empresa"].nombre
    assert all(fila["empresa"] == nombre_empresa for fila in cuerpo)


# --- GET /inventario/exportar : formato y Content-Type -----------------------


def test_exportar_csv_content_type_y_encabezados(cliente, fabrica, auth):
    """La exportación CSV responde 200, el Content-Type de CSV y la fila de
    encabezados (R7.1, R7.4, R7.5)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    escenario = fabrica.escenario()
    _crear_sillas(fabrica, escenario, 2)

    respuesta = cliente.get(
        "/inventario/exportar",
        params={"formato": "csv"},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"].startswith(MEDIA_TYPES["csv"])

    filas = list(csv.reader(io.StringIO(respuesta.content.decode("utf-8"))))
    assert filas[0] == list(ENCABEZADOS)
    # Encabezados + una fila por silla del alcance.
    assert len(filas) == 1 + 2


def test_exportar_xlsx_content_type_y_encabezados(cliente, fabrica, auth):
    """La exportación XLSX responde 200, el Content-Type de XLSX y la fila de
    encabezados (R7.2, R7.4, R7.5)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    escenario = fabrica.escenario()
    _crear_sillas(fabrica, escenario, 2)

    respuesta = cliente.get(
        "/inventario/exportar",
        params={"formato": "xlsx"},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"].startswith(MEDIA_TYPES["xlsx"])

    libro = load_workbook(io.BytesIO(respuesta.content))
    hoja = libro.active
    filas = list(hoja.iter_rows(values_only=True))
    assert list(filas[0]) == list(ENCABEZADOS)
    # Encabezados + una fila por silla del alcance.
    assert len(filas) == 1 + 2


def test_exportar_vacio_solo_encabezados(cliente, fabrica, auth):
    """Sin sillas, la exportación CSV trae solo la fila de encabezados (R6.2, R7.4)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.get(
        "/inventario/exportar",
        params={"formato": "csv"},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 200, respuesta.text
    filas = list(csv.reader(io.StringIO(respuesta.content.decode("utf-8"))))
    assert filas == [list(ENCABEZADOS)]


def test_exportar_sin_sesion_da_401(cliente):
    """Sin cabecera de sesión, la exportación responde 401 (R5.1)."""
    respuesta = cliente.get("/inventario/exportar", params={"formato": "csv"})

    assert respuesta.status_code == 401, respuesta.text


def test_exportar_rol_no_autorizado_da_403(cliente, fabrica, auth):
    """Un rol fuera del alcance recibe 403 también al exportar (R5.2)."""
    tecnico = fabrica.usuario("TECNICO")

    respuesta = cliente.get(
        "/inventario/exportar",
        params={"formato": "csv"},
        headers=auth(tecnico),
    )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "Rol no autorizado"


def test_exportar_formato_no_admitido_rechazado(cliente, fabrica, auth):
    """Un formato distinto de `csv`/`xlsx` se rechaza antes de generar archivo.

    La ruta declara `formato: Literal["csv", "xlsx"]`, por lo que la validación
    de la petición rechaza cualquier otro valor con 422 (R7.3).
    """
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.get(
        "/inventario/exportar",
        params={"formato": "pdf"},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 422, respuesta.text


def test_exportar_service_formato_no_admitido_es_400():
    """El origen del 400 es el service: `exportar` con formato inválido lanza
    `FormatoNoAdmitido`, que el router traduce a 400 (R7.3)."""
    try:
        exportar([], "pdf")
    except FormatoNoAdmitido as error:
        assert "csv" in str(error) and "xlsx" in str(error)
    else:  # pragma: no cover - el service debe rechazar el formato
        raise AssertionError("exportar debió lanzar FormatoNoAdmitido")
