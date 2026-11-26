"""Tests del alta del catálogo organizacional: empresa, sede y departamento.

Cubren los endpoints de creación añadidos sobre los listados de `test_catalogos`:
- `POST /empresas`               (solo COMERCIAL_MANSILLAS)
- `POST /empresas/{id}/sedes`    (COMERCIAL_MANSILLAS cualquier empresa;
                                  ADMIN_CLIENTE solo la suya)
- `POST /sedes/{id}/departamentos` (mismo alcance que sedes)

Siguen el patrón de `test_catalogos.py`: fixtures `cliente`, `fabrica`, `auth`;
el stub de desarrollo (`X-Dev-User-Id`) autentica. Omitirlo simula una petición
sin sesión (401).
"""


def _admin(fabrica, empresa):
    """Usuario ADMIN_CLIENTE atado a una empresa (alcance de su empresa)."""
    return fabrica.usuario("ADMIN_CLIENTE", empresa=empresa)


# --- POST /empresas ----------------------------------------------------------


def test_crear_empresa_sin_sesion_da_401(cliente):
    """Sin cabecera de sesión, el alta de empresa responde 401."""
    respuesta = cliente.post(
        "/empresas", json={"nombre": "Nueva S.A.", "nit": "900111222-3"}
    )

    assert respuesta.status_code == 401, respuesta.text


def test_comercial_crea_empresa(cliente, fabrica, auth):
    """`COMERCIAL_MANSILLAS` crea una empresa (201) con todas sus columnas."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.post(
        "/empresas",
        json={
            "nombre": "ACME S.A.",
            "nit": "900111222-3",
            "correo": "contacto@acme.test",
            "telefono": "6011234567",
        },
        headers=auth(comercial),
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "ACME S.A."
    assert cuerpo["nit"] == "900111222-3"
    # permiso_qr y activa los fija el SQL por defecto.
    assert cuerpo["permiso_qr"] == 1
    assert cuerpo["activa"] is True
    for columna in (
        "id_empresa",
        "nombre",
        "nit",
        "correo",
        "telefono",
        "permiso_qr",
        "activa",
    ):
        assert columna in cuerpo


def test_crear_empresa_nit_duplicado_da_409(cliente, fabrica, auth):
    """Un NIT ya usado responde 409 (`UNIQUE (nit)`)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    existente = fabrica.empresa()

    respuesta = cliente.post(
        "/empresas",
        json={"nombre": "Otra", "nit": existente.nit},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 409, respuesta.text


def test_crear_empresa_rol_no_autorizado_da_403(cliente, fabrica, auth):
    """Un rol que no es comercial (p. ej. TECNICO) no puede crear empresas."""
    tecnico = fabrica.usuario("TECNICO")

    respuesta = cliente.post(
        "/empresas",
        json={"nombre": "X", "nit": "900999888-7"},
        headers=auth(tecnico),
    )

    assert respuesta.status_code == 403, respuesta.text


def test_crear_empresa_sin_nombre_da_422(cliente, fabrica, auth):
    """Falta un campo obligatorio: validación de Pydantic (422)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.post(
        "/empresas", json={"nit": "900999888-7"}, headers=auth(comercial)
    )

    assert respuesta.status_code == 422, respuesta.text


# --- GET /empresas -----------------------------------------------------------


def test_comercial_lista_todas_las_empresas(cliente, fabrica, auth):
    """`COMERCIAL_MANSILLAS` ve todas las empresas, ordenadas."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    emp_a = fabrica.empresa()
    emp_b = fabrica.empresa()

    respuesta = cliente.get("/empresas", headers=auth(comercial))

    assert respuesta.status_code == 200, respuesta.text
    ids = [fila["id_empresa"] for fila in respuesta.json()]
    assert emp_a.id_empresa in ids and emp_b.id_empresa in ids
    assert ids == sorted(ids)


def test_admin_cliente_solo_ve_su_empresa(cliente, fabrica, auth):
    """El `ADMIN_CLIENTE` recibe únicamente su empresa, no las demás."""
    empresa = fabrica.empresa()
    fabrica.empresa()  # otra empresa que NO debe aparecer
    admin = _admin(fabrica, empresa)

    respuesta = cliente.get("/empresas", headers=auth(admin))

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [fila["id_empresa"] for fila in cuerpo] == [empresa.id_empresa]


# --- POST /empresas/{id}/sedes -----------------------------------------------


def test_comercial_crea_sede(cliente, fabrica, auth):
    """`COMERCIAL_MANSILLAS` registra una sede en una empresa (201)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/sedes",
        json={"nombre": "Sede Norte", "direccion": "Cra 1", "ciudad": "Bogotá"},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Sede Norte"
    assert cuerpo["id_empresa"] == empresa.id_empresa
    assert "id_sede" in cuerpo


def test_crear_sede_empresa_inexistente_da_404(cliente, fabrica, auth):
    """Una empresa inexistente responde 404."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.post(
        "/empresas/999999/sedes",
        json={"nombre": "Sede"},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 404, respuesta.text


def test_crear_sede_nombre_duplicado_da_409(cliente, fabrica, auth):
    """Un nombre de sede repetido en la misma empresa responde 409."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/sedes",
        json={"nombre": sede.nombre},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 409, respuesta.text


def test_admin_cliente_crea_sede_en_su_empresa(cliente, fabrica, auth):
    """El `ADMIN_CLIENTE` puede registrar una sede en su propia empresa."""
    empresa = fabrica.empresa()
    admin = _admin(fabrica, empresa)

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/sedes",
        json={"nombre": "Sede Admin"},
        headers=auth(admin),
    )

    assert respuesta.status_code == 201, respuesta.text


def test_admin_cliente_no_crea_sede_en_otra_empresa(cliente, fabrica, auth):
    """Aislamiento: el `ADMIN_CLIENTE` de otra empresa recibe 403."""
    empresa_propia = fabrica.empresa()
    empresa_ajena = fabrica.empresa()
    admin = _admin(fabrica, empresa_propia)

    respuesta = cliente.post(
        f"/empresas/{empresa_ajena.id_empresa}/sedes",
        json={"nombre": "Sede Ajena"},
        headers=auth(admin),
    )

    assert respuesta.status_code == 403, respuesta.text


def test_tecnico_no_crea_sede_da_403(cliente, fabrica, auth):
    """Un `TECNICO` no está autorizado para registrar sedes."""
    tecnico = fabrica.usuario("TECNICO")
    empresa = fabrica.empresa()

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/sedes",
        json={"nombre": "Sede"},
        headers=auth(tecnico),
    )

    assert respuesta.status_code == 403, respuesta.text


# --- POST /sedes/{id}/departamentos ------------------------------------------


def test_comercial_crea_departamento(cliente, fabrica, auth):
    """`COMERCIAL_MANSILLAS` registra un departamento en una sede (201).

    El `id_empresa` e `id_sede` los deriva el backend del path, no del cuerpo.
    """
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)

    respuesta = cliente.post(
        f"/sedes/{sede.id_sede}/departamentos",
        json={"nombre": "Contabilidad"},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Contabilidad"
    assert cuerpo["id_sede"] == sede.id_sede
    assert cuerpo["id_empresa"] == empresa.id_empresa
    assert "id_departamento" in cuerpo


def test_crear_departamento_sede_inexistente_da_404(cliente, fabrica, auth):
    """Una sede inexistente responde 404 (no se resuelve su empresa)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")

    respuesta = cliente.post(
        "/sedes/999999/departamentos",
        json={"nombre": "X"},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 404, respuesta.text


def test_crear_departamento_nombre_duplicado_da_409(cliente, fabrica, auth):
    """Un nombre repetido en la misma sede responde 409."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    dep = fabrica.departamento(empresa, sede)

    respuesta = cliente.post(
        f"/sedes/{sede.id_sede}/departamentos",
        json={"nombre": dep.nombre},
        headers=auth(comercial),
    )

    assert respuesta.status_code == 409, respuesta.text


def test_admin_cliente_no_crea_departamento_en_otra_empresa(cliente, fabrica, auth):
    """Aislamiento: el `ADMIN_CLIENTE` recibe 403 ante una sede ajena."""
    empresa_propia = fabrica.empresa()
    empresa_ajena = fabrica.empresa()
    sede_ajena = fabrica.sede(empresa_ajena)
    admin = _admin(fabrica, empresa_propia)

    respuesta = cliente.post(
        f"/sedes/{sede_ajena.id_sede}/departamentos",
        json={"nombre": "Área"},
        headers=auth(admin),
    )

    assert respuesta.status_code == 403, respuesta.text


# --- POST /empresas/{id}/empleados -------------------------------------------


def _cuerpo_empleado(sede, departamento, **extra):
    """Payload base del alta manual (sede/departamento de desplegables)."""
    cuerpo = {
        "id_sede": sede.id_sede,
        "id_departamento": departamento.id_departamento,
        "nombre": "Ana Pérez",
        "cargo": "Analista",
    }
    cuerpo.update(extra)
    return cuerpo


def test_comercial_crea_empleado(cliente, fabrica, auth):
    """`COMERCIAL_MANSILLAS` registra un empleado en una empresa (201).

    El `id_empresa` lo deriva el backend del path; `activo` lo fija el SQL.
    """
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    departamento = fabrica.departamento(empresa, sede)

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/empleados",
        json=_cuerpo_empleado(
            sede, departamento, documento="123", correo="ana@test.local"
        ),
        headers=auth(comercial),
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Ana Pérez"
    assert cuerpo["id_empresa"] == empresa.id_empresa
    assert cuerpo["id_sede"] == sede.id_sede
    assert cuerpo["id_departamento"] == departamento.id_departamento
    assert cuerpo["activo"] is True
    assert "id_empleado" in cuerpo


def test_crear_empleado_sede_inexistente_da_400(cliente, fabrica, auth):
    """Una sede que no existe en la empresa responde 400 (FK compuesta)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    departamento = fabrica.departamento(empresa, sede)

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/empleados",
        json=_cuerpo_empleado(
            sede, departamento, id_sede=999999
        ),
        headers=auth(comercial),
    )

    assert respuesta.status_code == 400, respuesta.text


def test_crear_empleado_departamento_de_otra_sede_da_400(cliente, fabrica, auth):
    """Un departamento que no cuelga de la sede elegida responde 400."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede_a = fabrica.sede(empresa)
    sede_b = fabrica.sede(empresa)
    dep_de_b = fabrica.departamento(empresa, sede_b)

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/empleados",
        # sede_a + departamento de sede_b: combinación incoherente.
        json=_cuerpo_empleado(sede_a, dep_de_b),
        headers=auth(comercial),
    )

    assert respuesta.status_code == 400, respuesta.text


def test_crear_empleado_documento_duplicado_da_409(cliente, fabrica, auth):
    """Un documento ya usado en la empresa responde 409 (`UNIQUE`)."""
    comercial = fabrica.usuario("COMERCIAL_MANSILLAS")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    departamento = fabrica.departamento(empresa, sede)
    existente = fabrica.empleado(empresa, sede, departamento)

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/empleados",
        json=_cuerpo_empleado(sede, departamento, documento=existente.documento),
        headers=auth(comercial),
    )

    assert respuesta.status_code == 409, respuesta.text


def test_admin_cliente_crea_empleado_en_su_empresa(cliente, fabrica, auth):
    """El `ADMIN_CLIENTE` puede dar de alta un empleado en su propia empresa."""
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    departamento = fabrica.departamento(empresa, sede)
    admin = _admin(fabrica, empresa)

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/empleados",
        json=_cuerpo_empleado(sede, departamento),
        headers=auth(admin),
    )

    assert respuesta.status_code == 201, respuesta.text


def test_admin_cliente_no_crea_empleado_en_otra_empresa(cliente, fabrica, auth):
    """Aislamiento: el `ADMIN_CLIENTE` recibe 403 ante una empresa ajena."""
    empresa_propia = fabrica.empresa()
    empresa_ajena = fabrica.empresa()
    sede_ajena = fabrica.sede(empresa_ajena)
    dep_ajeno = fabrica.departamento(empresa_ajena, sede_ajena)
    admin = _admin(fabrica, empresa_propia)

    respuesta = cliente.post(
        f"/empresas/{empresa_ajena.id_empresa}/empleados",
        json=_cuerpo_empleado(sede_ajena, dep_ajeno),
        headers=auth(admin),
    )

    assert respuesta.status_code == 403, respuesta.text


def test_tecnico_no_crea_empleado_da_403(cliente, fabrica, auth):
    """Un `TECNICO` no está autorizado para dar de alta empleados."""
    tecnico = fabrica.usuario("TECNICO")
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    departamento = fabrica.departamento(empresa, sede)

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/empleados",
        json=_cuerpo_empleado(sede, departamento),
        headers=auth(tecnico),
    )

    assert respuesta.status_code == 403, respuesta.text


def test_crear_empleado_sin_sesion_da_401(cliente, fabrica):
    """Sin cabecera de sesión, el alta de empleado responde 401."""
    empresa = fabrica.empresa()
    sede = fabrica.sede(empresa)
    departamento = fabrica.departamento(empresa, sede)

    respuesta = cliente.post(
        f"/empresas/{empresa.id_empresa}/empleados",
        json=_cuerpo_empleado(sede, departamento),
    )

    assert respuesta.status_code == 401, respuesta.text
