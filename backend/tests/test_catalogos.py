"""Tests de los listados de catálogo: sedes, departamentos y empleados (R9).

Siguen el patrón de `conftest.py`/`test_inventario.py`: usan las fixtures
`cliente`, `fabrica` y `auth`. El catálogo se materializa con la fábrica
(empresa → sede → departamento → empleado) y las peticiones usan el stub de
autenticación de desarrollo (`X-Dev-User-Id`). Omitir ese header simula una
petición sin sesión (401).

Rutas cubiertas:
- `GET /empresas/{id_empresa}/sedes`
- `GET /sedes/{id_sede}/departamentos`
- `GET /empresas/{id_empresa}/empleados`

Alcance por rol: los internos (`COMERCIAL_MANSILLAS`, `TECNICO`) ven los de
cualquier empresa; el `ADMIN_CLIENTE` solo los de su propia empresa (aislamiento
coherente con `routers/qr.py`).
"""


def _admin(fabrica, empresa):
    """Usuario ADMIN_CLIENTE atado a una empresa (alcance de su empresa)."""
    return fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)


# --- GET /empresas/{id}/sedes ------------------------------------------------


def test_listar_sedes_sin_sesion_da_401(cliente, fabrica):
    """Sin cabecera de sesión, el listado de sedes responde 401."""
    empresa = fabrica.empresa()

    respuesta = cliente.get(f"/empresas/{empresa.id_empresa}/sedes")

    assert respuesta.status_code == 401, respuesta.text


def test_listar_sedes_rol_no_autorizado_da_403(cliente, fabrica, auth):
    """Un rol fuera del alcance (EMPLEADO_CLIENTE) recibe 403."""
    empresa = fabrica.empresa()
    empleado_cliente = fabrica.usuario("EMPLEADO_CLIENTE", empresa=empresa)

    respuesta = cliente.get(
        f"/empresas/{empresa.id_empresa}/sedes",
        headers=auth(empleado_cliente),
    )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "Rol no autorizado"


def test_comercial_lista_sedes_de_la_empresa(cliente, fabrica, auth):
    """`COMERCIAL_MANSILLAS` ve las sedes de la empresa pedida, ordenadas."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede_a = fabrica.sede(empresa)
    sede_b = fabrica.sede(empresa)

    respuesta = cliente.get(
        f"/empresas/{empresa.id_empresa}/sedes",
        headers=auth(comercial),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [fila["id_sede"] for fila in cuerpo] == [sede_a.id_sede, sede_b.id_sede]
    primera = cuerpo[0]
    for columna in ("id_sede", "id_empresa", "nombre", "direccion", "ciudad"):
        assert columna in primera
    assert all(fila["id_empresa"] == empresa.id_empresa for fila in cuerpo)


def test_tecnico_lista_sedes_de_cualquier_empresa(cliente, fabrica, auth):
    """Un rol interno `TECNICO` también lista las sedes de cualquier empresa."""
    tecnico = fabrica.usuario("TECNICO")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)

    respuesta = cliente.get(
        f"/empresas/{empresa.id_empresa}/sedes",
        headers=auth(tecnico),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert [fila["id_sede"] for fila in respuesta.json()] == [sede.id_sede]


def test_admin_cliente_lista_sedes_de_su_empresa(cliente, fabrica, auth):
    """El `ADMIN_CLIENTE` ve las sedes de su propia empresa."""
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    admin = _admin(fabrica, empresa)

    respuesta = cliente.get(
        f"/empresas/{empresa.id_empresa}/sedes",
        headers=auth(admin),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert [fila["id_sede"] for fila in respuesta.json()] == [sede.id_sede]


def test_admin_cliente_no_ve_sedes_de_otra_empresa(cliente, fabrica, auth):
    """Aislamiento: el `ADMIN_CLIENTE` de otra empresa recibe 403."""
    empresa_propia = fabrica.empresa()
    empresa_ajena = fabrica.empresa()
    fabrica.sede(empresa_ajena)
    admin = _admin(fabrica, empresa_propia)

    respuesta = cliente.get(
        f"/empresas/{empresa_ajena.id_empresa}/sedes",
        headers=auth(admin),
    )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "No autorizado para esta empresa"


def test_listar_sedes_empresa_inexistente_da_lista_vacia(cliente, fabrica, auth):
    """Para un rol interno, una empresa inexistente devuelve 200 con lista vacía."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.get("/empresas/999999/sedes", headers=auth(comercial))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []


# --- GET /sedes/{id}/departamentos -------------------------------------------


def test_listar_departamentos_sin_sesion_da_401(cliente, fabrica):
    """Sin cabecera de sesión, el listado de departamentos responde 401."""
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)

    respuesta = cliente.get(f"/sedes/{sede.id_sede}/departamentos")

    assert respuesta.status_code == 401, respuesta.text


def test_comercial_lista_departamentos_de_la_sede(cliente, fabrica, auth):
    """`COMERCIAL_MANSILLAS` ve los departamentos de la sede pedida, ordenados."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    dep_a = fabrica.departamento(empresa, sede)
    dep_b = fabrica.departamento(empresa, sede)

    respuesta = cliente.get(
        f"/sedes/{sede.id_sede}/departamentos",
        headers=auth(comercial),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [fila["id_departamento"] for fila in cuerpo] == [
        dep_a.id_departamento,
        dep_b.id_departamento,
    ]
    for columna in ("id_departamento", "id_empresa", "id_sede", "nombre"):
        assert columna in cuerpo[0]
    assert all(fila["id_sede"] == sede.id_sede for fila in cuerpo)


def test_admin_cliente_lista_departamentos_de_su_sede(cliente, fabrica, auth):
    """El `ADMIN_CLIENTE` ve los departamentos de una sede de su empresa."""
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    dep = fabrica.departamento(empresa, sede)
    admin = _admin(fabrica, empresa)

    respuesta = cliente.get(
        f"/sedes/{sede.id_sede}/departamentos",
        headers=auth(admin),
    )

    assert respuesta.status_code == 200, respuesta.text
    assert [fila["id_departamento"] for fila in respuesta.json()] == [
        dep.id_departamento
    ]


def test_admin_cliente_no_ve_departamentos_de_otra_empresa(cliente, fabrica, auth):
    """Aislamiento: el `ADMIN_CLIENTE` de otra empresa recibe 403 por la sede ajena."""
    empresa_propia = fabrica.empresa()
    empresa_ajena = fabrica.empresa()
    sede_ajena = fabrica.sede(empresa_ajena)
    fabrica.departamento(empresa_ajena, sede_ajena)
    admin = _admin(fabrica, empresa_propia)

    respuesta = cliente.get(
        f"/sedes/{sede_ajena.id_sede}/departamentos",
        headers=auth(admin),
    )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "No autorizado para esta empresa"


def test_listar_departamentos_sede_inexistente_da_404(cliente, fabrica, auth):
    """Una sede inexistente responde 404 (no se puede resolver su empresa)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.get("/sedes/999999/departamentos", headers=auth(comercial))

    assert respuesta.status_code == 404, respuesta.text


# --- GET /empresas/{id}/empleados --------------------------------------------


def test_listar_empleados_sin_sesion_da_401(cliente, fabrica):
    """Sin cabecera de sesión, el listado de empleados responde 401."""
    empresa = fabrica.empresa()

    respuesta = cliente.get(f"/empresas/{empresa.id_empresa}/empleados")

    assert respuesta.status_code == 401, respuesta.text


def test_comercial_lista_empleados_de_la_empresa(cliente, fabrica, auth):
    """`COMERCIAL_MANSILLAS` ve los empleados de la empresa pedida, ordenados."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    dep = fabrica.departamento(empresa, sede)
    emp_a = fabrica.empleado(empresa, sede, dep)
    emp_b = fabrica.empleado(empresa, sede, dep)

    respuesta = cliente.get(
        f"/empresas/{empresa.id_empresa}/empleados",
        headers=auth(comercial),
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [fila["id_empleado"] for fila in cuerpo] == [
        emp_a.id_empleado,
        emp_b.id_empleado,
    ]
    for columna in (
        "id_empleado",
        "id_empresa",
        "id_sede",
        "id_departamento",
        "nombre",
        "documento",
        "correo",
        "cargo",
        "activo",
    ):
        assert columna in cuerpo[0]
    assert all(fila["id_empresa"] == empresa.id_empresa for fila in cuerpo)


def test_admin_cliente_no_ve_empleados_de_otra_empresa(cliente, fabrica, auth):
    """Aislamiento: el `ADMIN_CLIENTE` de otra empresa recibe 403."""
    empresa_propia = fabrica.empresa()
    empresa_ajena = fabrica.empresa()
    sede_ajena = fabrica.sede(empresa_ajena)
    dep_ajeno = fabrica.departamento(empresa_ajena, sede_ajena)
    fabrica.empleado(empresa_ajena, sede_ajena, dep_ajeno)
    admin = _admin(fabrica, empresa_propia)

    respuesta = cliente.get(
        f"/empresas/{empresa_ajena.id_empresa}/empleados",
        headers=auth(admin),
    )

    assert respuesta.status_code == 403, respuesta.text
    assert respuesta.json()["detail"] == "No autorizado para esta empresa"


def test_listar_empleados_empresa_inexistente_da_lista_vacia(cliente, fabrica, auth):
    """Para un rol interno, una empresa inexistente devuelve 200 con lista vacía."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.get("/empresas/999999/empleados", headers=auth(comercial))

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == []
