"""Pruebas de ejemplo y edge cases de la carga masiva de empleados (HU-19).

Cubren el endpoint `POST /carga-masiva/empleados` siguiendo el patrón de
`conftest.py`/`test_sillas.py` (fixtures `cliente`, `fabrica`, `auth`, `db`).
Los `.xlsx` se construyen en memoria con `openpyxl` y se envían como
multipart/form-data en el campo `archivo` que espera el router.

Casos de autorización y formato (R1-R2):

- 401 sin sesión (sin cabecera de usuario de desarrollo).
- 403 con un rol distinto de `ADMIN_CLIENTE`.
- 400 por extensión distinta de `.xlsx`.
- 400 por columnas obligatorias faltantes.
- 400 por archivo sin filas de datos.

Casos de procesamiento por fila (R3) y aislamiento multiempresa (R1.3):

- Reporte con mezcla de filas válidas e inválidas (obligatoria vacía): las
  válidas se aplican sin abortar por las inválidas, los conteos cuadran y queda
  el registro de la carga en `carga_excel`.
- Todo lo creado queda en `user.empresa_id`, nunca en otra empresa.
"""

from __future__ import annotations

import io

from openpyxl import Workbook
from sqlalchemy import func, select, text

from app.models import Departamento, Empleado, Sede

# Media type de un `.xlsx` para el multipart de subida.
XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# Encabezados del Formato_Carga (obligatorias + opcionales) en el orden en que
# los escribimos en el libro de prueba.
ENCABEZADOS = ("sede", "departamento", "nombre", "cargo", "documento", "correo")


def _xlsx(encabezados: list[str], filas: list[list[object]]) -> bytes:
    """Arma un `.xlsx` en memoria con los encabezados y filas dados."""
    libro = Workbook()
    hoja = libro.active
    hoja.append(list(encabezados))
    for fila in filas:
        hoja.append(fila)
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _subir(cliente, headers, contenido: bytes, *, nombre: str = "carga.xlsx"):
    """POST del `.xlsx` al endpoint de carga masiva como multipart."""
    return cliente.post(
        "/carga-masiva/empleados",
        files={"archivo": (nombre, contenido, XLSX_MEDIA_TYPE)},
        headers=headers,
    )


def _registros_carga_excel(db, id_empresa: int) -> list[dict]:
    """Filas registradas en `carga_excel` para la empresa dada."""
    db.expire_all()
    filas = db.execute(
        text(
            """
            SELECT nombre_archivo, registros_procesados, registros_con_error,
                   id_usuario
            FROM carga_excel
            WHERE id_empresa = :id_empresa
            ORDER BY id_carga
            """
        ),
        {"id_empresa": id_empresa},
    ).mappings().all()
    return [dict(fila) for fila in filas]


# --- Autorización (R1.1, R1.2) ---------------------------------------------


def test_carga_sin_sesion_da_401(cliente, fabrica):
    """Sin sesión autenticada, la carga responde 401 (R1.1)."""
    empresa = fabrica.empresa()
    fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)
    contenido = _xlsx(
        list(ENCABEZADOS),
        [["Sede A", "Área A", "Juan", "Analista", "DOC001", "juan@x.local"]],
    )

    respuesta = _subir(cliente, {}, contenido)

    assert respuesta.status_code == 401, respuesta.text


def test_carga_con_rol_no_admin_cliente_da_403(cliente, fabrica, auth):
    """Un rol distinto de ADMIN_CLIENTE no puede cargar (R1.2)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    contenido = _xlsx(
        list(ENCABEZADOS),
        [["Sede A", "Área A", "Juan", "Analista", "DOC001", "juan@x.local"]],
    )

    respuesta = _subir(cliente, auth(comercial), contenido)

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "Rol no autorizado"


# --- Validación de formato del archivo (R2) --------------------------------


def test_carga_extension_no_xlsx_da_400(cliente, fabrica, auth):
    """Una extensión distinta de `.xlsx` se rechaza con 400 (R2.1)."""
    empresa = fabrica.empresa()
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)
    contenido = _xlsx(
        list(ENCABEZADOS),
        [["Sede A", "Área A", "Juan", "Analista", "DOC001", "juan@x.local"]],
    )

    respuesta = cliente.post(
        "/carga-masiva/empleados",
        files={"archivo": ("empleados.csv", contenido, "text/csv")},
        headers=auth(admin),
    )

    assert respuesta.status_code == 400, respuesta.text
    assert ".xlsx" in respuesta.json()["detail"]


def test_carga_columnas_faltantes_da_400(cliente, fabrica, auth):
    """Faltar una columna obligatoria devuelve 400 con la columna ausente (R2.2)."""
    empresa = fabrica.empresa()
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)
    # Falta la columna obligatoria `cargo`.
    encabezados = ["sede", "departamento", "nombre", "documento", "correo"]
    contenido = _xlsx(
        encabezados,
        [["Sede A", "Área A", "Juan", "DOC001", "juan@x.local"]],
    )

    respuesta = _subir(cliente, auth(admin), contenido)

    assert respuesta.status_code == 400, respuesta.text
    assert "cargo" in respuesta.json()["detail"]


def test_carga_archivo_vacio_da_400(cliente, fabrica, auth):
    """Un archivo con encabezados pero sin filas de datos devuelve 400 (R2.3)."""
    empresa = fabrica.empresa()
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)
    contenido = _xlsx(list(ENCABEZADOS), [])

    respuesta = _subir(cliente, auth(admin), contenido)

    assert respuesta.status_code == 400, respuesta.text
    assert "vac" in respuesta.json()["detail"].lower()


# --- Procesamiento por fila y reporte (R3) ---------------------------------


def test_carga_mezcla_validas_invalidas_sin_abortar(cliente, fabrica, auth, db):
    """Las filas válidas se aplican aunque otras fallen y se informa el reporte.

    Dos filas válidas y una inválida (cargo vacío): el endpoint devuelve 200 con
    total_procesadas=3, total_aplicadas=2 y un Error_Fila para la fila 2; se
    crean la sede, el departamento y los dos empleados, y queda el resumen en
    `carga_excel` con 3 procesados y 1 con error (R3.2-R3.5).
    """
    empresa = fabrica.empresa()
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)
    contenido = _xlsx(
        list(ENCABEZADOS),
        [
            ["Sede Norte", "Ventas", "Ana", "Analista", "DOC001", "ana@x.local"],
            # Fila inválida: `cargo` vacío.
            ["Sede Norte", "Ventas", "Beto", None, "DOC002", "beto@x.local"],
            ["Sede Norte", "Ventas", "Caro", "Jefe", "DOC003", "caro@x.local"],
        ],
    )

    respuesta = _subir(cliente, auth(admin), contenido)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["nombre_archivo"] == "carga.xlsx"
    assert cuerpo["total_procesadas"] == 3
    assert cuerpo["total_aplicadas"] == 2
    assert len(cuerpo["errores"]) == 1
    # El Error_Fila apunta a la fila 2 (1-based sobre las filas de datos).
    assert cuerpo["errores"][0]["fila"] == 2
    assert cuerpo["errores"][0]["motivo"]
    # Invariante del reporte: procesadas = aplicadas + errores (R3.4).
    assert cuerpo["total_procesadas"] == cuerpo["total_aplicadas"] + len(
        cuerpo["errores"]
    )

    db.expire_all()
    # Solo se aplicaron las dos filas válidas (R3.2/R3.3).
    empleados = db.execute(
        select(Empleado).where(Empleado.id_empresa == empresa.id_empresa)
    ).scalars().all()
    nombres = {empleado.nombre for empleado in empleados}
    assert nombres == {"Ana", "Caro"}
    assert "Beto" not in nombres
    # Buscar-o-crear no duplicó la sede ni el departamento compartidos (R4).
    assert db.execute(
        select(func.count())
        .select_from(Sede)
        .where(Sede.id_empresa == empresa.id_empresa)
    ).scalar_one() == 1
    assert db.execute(
        select(func.count())
        .select_from(Departamento)
        .where(Departamento.id_empresa == empresa.id_empresa)
    ).scalar_one() == 1

    # El resumen quedó registrado en carga_excel (R3.5).
    registros = _registros_carga_excel(db, empresa.id_empresa)
    assert len(registros) == 1
    assert registros[0]["nombre_archivo"] == "carga.xlsx"
    assert registros[0]["registros_procesados"] == 3
    assert registros[0]["registros_con_error"] == 1
    assert registros[0]["id_usuario"] == admin.id_usuario


def test_carga_todas_invalidas_no_aplica_nada(cliente, fabrica, auth, db):
    """Si todas las filas son inválidas no se aplica nada pero sí se registra (R3)."""
    empresa = fabrica.empresa()
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)
    contenido = _xlsx(
        list(ENCABEZADOS),
        [
            # Falta `nombre`.
            ["Sede Sur", "Compras", None, "Analista", "DOC010", "a@x.local"],
            # Falta `sede`.
            [None, "Compras", "Deborah", "Jefe", "DOC011", "d@x.local"],
        ],
    )

    respuesta = _subir(cliente, auth(admin), contenido)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["total_procesadas"] == 2
    assert cuerpo["total_aplicadas"] == 0
    assert len(cuerpo["errores"]) == 2

    db.expire_all()
    assert db.execute(
        select(func.count())
        .select_from(Empleado)
        .where(Empleado.id_empresa == empresa.id_empresa)
    ).scalar_one() == 0

    registros = _registros_carga_excel(db, empresa.id_empresa)
    assert len(registros) == 1
    assert registros[0]["registros_procesados"] == 2
    assert registros[0]["registros_con_error"] == 2


# --- Aislamiento multiempresa (R1.3) ---------------------------------------


def test_carga_aislamiento_multiempresa(cliente, fabrica, auth, db):
    """Todo lo creado queda en la empresa del admin, nunca en otra (R1.3).

    Existe una segunda empresa en la base; tras la carga del admin de la primera
    empresa, ni esa segunda empresa ni ninguna otra reciben sedes,
    departamentos o empleados nuevos: todo se asocia a `user.empresa_id`.
    """
    empresa_propia = fabrica.empresa("Propia")
    admin = fabrica.usuario("ADMIN_CLIENTE", empresa=empresa_propia)
    # Segunda empresa totalmente ajena a la carga.
    empresa_ajena = fabrica.empresa("Ajena")

    contenido = _xlsx(
        list(ENCABEZADOS),
        [
            ["Sede Centro", "TI", "Elena", "Dev", "DOC100", "elena@x.local"],
            ["Sede Centro", "TI", "Fabio", "Dev", "DOC101", "fabio@x.local"],
        ],
    )

    respuesta = _subir(cliente, auth(admin), contenido)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["total_aplicadas"] == 2

    db.expire_all()

    # Todo lo creado pertenece a la empresa propia.
    for modelo in (Sede, Departamento, Empleado):
        creados = db.execute(
            select(func.count())
            .select_from(modelo)
            .where(modelo.id_empresa == empresa_propia.id_empresa)
        ).scalar_one()
        assert creados >= 1

    # La empresa ajena no recibió nada de esta carga.
    for modelo in (Sede, Departamento, Empleado):
        ajenos = db.execute(
            select(func.count())
            .select_from(modelo)
            .where(modelo.id_empresa == empresa_ajena.id_empresa)
        ).scalar_one()
        assert ajenos == 0

    # Cada empleado creado apunta a la empresa propia.
    empleados = db.execute(
        select(Empleado).where(Empleado.id_empresa == empresa_propia.id_empresa)
    ).scalars().all()
    assert {empleado.nombre for empleado in empleados} == {"Elena", "Fabio"}
    for empleado in empleados:
        assert empleado.id_empresa == empresa_propia.id_empresa
        assert empleado.activo is True

    # El registro de auditoría también queda en la empresa propia, no en la ajena.
    assert len(_registros_carga_excel(db, empresa_propia.id_empresa)) == 1
    assert _registros_carga_excel(db, empresa_ajena.id_empresa) == []
