---
inclusion: always
---

# Estructura — backend Mansillas

Workspace de Kiro: `backend/` (raíz del repo abierta como esta carpeta). Rutas
relativas a `backend/`.

## Árbol relevante
```
app/
  main.py              # crea la app, CORS, registra routers
  config.py            # Settings (pydantic-settings), is_production, normalizar_database_url
  db.py                # engine, SessionLocal, get_db
  deps.py              # RBAC de negocio: CurrentUser, require_role, require_tecnico_owns_visita
  dependencies.py      # RBAC de seguridad: UsuarioPublico (otro dueño; no unificar)
  security.py          # JWT, bcrypt, hash_token
  schemas.py           # esquemas Pydantic compartidos
  supabase_client.py   # cliente Supabase (hoy sin consumir)
  models/              # un archivo por tabla; __init__.py reexporta todos
  routers/             # auth, usuarios (seguridad); visitas, sillas, qr, accesos (negocio)
  services/            # auth_service, usuarios_service
database/
  SQLMansillasSIC.sql  # esquema, triggers y "REGLAS QUE DEBE APLICAR EL BACKEND"
  seed_dev.py, test_db.py
tests/                 # pytest; conftest.py reconstruye el esquema sobre TEST_DATABASE_URL
.kiro/specs/           # mansillas-backend (spec de Davidson, conservar intacto) + mis specs
.kiro/steering/        # este directorio
```

## Modelos existentes
`app/models/__init__.py` exporta: `Empresa`, `Sede`, `Departamento`, `Usuario`,
`Empleado`, `Visita`, `Silla`, `Precotizacion`, `AccesoPrecotizacion`,
`SesionUsuario`.

Sin modelo ni router todavía (existen en el SQL, los necesitan mis historias):
`fotografia` (HU-10), `codigo_verificacion` (HU-15), `aceptacion_precotizacion`
(HU-15), `cotizacion` (solo el alcance de HU-16: habilitar cotización tras
aceptar). `componente`/`silla_componente` (checklist y evaluación >70%) son de
Esteban: mis historias los consumen, no los implementan.

## Endpoints implementados (reutilizar, no duplicar)
- `auth.py`: `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`.
- `usuarios.py`: `GET /usuarios`, `POST /usuarios`, `PUT /usuarios/{id}/rol`.
- `visitas.py`: `POST/GET /visitas`, `GET/PUT/DELETE /visitas/{id}`.
- `sillas.py`: `POST /visitas/{id_visita}/sillas`, `GET /sillas/token/{token}`,
  `GET /sillas/{id}`, `PUT /sillas/{id}`.
- `qr.py`: `POST /qr/pdf`.
- `accesos.py`: `GET /precotizaciones/{id}/accesos` + servicio `registrar_acceso`.

## Propiedad por módulo
- Seguridad (auth, usuarios, `dependencies.py`): otro desarrollador. No modificar
  salvo autorización; documentar riesgos detectados.
- Negocio base (visitas, sillas, qr, accesos, `deps.py`): spec de Davidson.
  Reutilizar como plantilla y base de mis extensiones.
- Componentes, checklist y evaluación de sillas (`componente`, `silla_componente`,
  `vista_estado_mantenimiento`): corresponde a Esteban. Mis historias pueden
  **consumir** esa información, pero no deben duplicar su implementación.
- Fotos / precotización / OTP / aceptación: mis historias. Cotización: solo el
  alcance definido por HU-16 (habilitar la cotización tras aceptar), no el
  desarrollo completo del módulo de cotización.
- Frontend: vive en `origin/dev/nicolas`; consultar en solo lectura sus contratos.

## Convenciones al extender
- Nuevo modelo → crear `app/models/<tabla>.py` y reexportarlo en
  `app/models/__init__.py` (orden alfabético, igual que el existente).
- Nuevo router → crear `app/routers/<recurso>.py` siguiendo el patrón de
  `sillas.py`/`visitas.py` y registrarlo en `app/main.py`.
- Autorización de negocio con `app/deps.py` (`require_role`,
  `require_tecnico_owns_visita`).
- `IntegrityError` y `RAISE EXCEPTION` de triggers → traducir a `HTTPException`
  (409/422/400).
- Columnas generadas por la BD → `FetchedValue()` en el modelo.
- Nuevas pruebas en `tests/`, reutilizando las fixtures de `conftest.py`.

## Reglas de ubicación de specs
- `.kiro/specs/mansillas-backend/` es de Davidson: conservar intacto, no reutilizar
  su `specId`.
- Mis specs (cuando se autoricen): `levantamiento-adicional` (HU-02/10),
  `gestion-precotizacion` (HU-12/13), `aceptacion-precotizacion` (HU-15/16), cada
  una con su propio identificador por el proceso nativo de Kiro.

## Restricciones
- No modificar el esquema SQL, el frontend, `conftest.py`, ni los módulos/ramas de
  otros desarrolladores sin autorización.
- No crear ramas, commits, merges ni push sin autorización.
