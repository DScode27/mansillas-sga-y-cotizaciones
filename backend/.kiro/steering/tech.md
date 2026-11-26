---
inclusion: always
---

# Tecnología — backend Mansillas

## Stack establecido
Fuente: `pyproject.toml`, `app/`, `database/SQLMansillasSIC.sql`.

- **Lenguaje**: Python. `pyproject.toml` exige `>=3.13`; `.python-version` fija
  `3.14`. Entorno actual: uv 0.13.10 y Python 3.14.10. Se mantiene 3.14.
- **Framework**: FastAPI (`fastapi[standard]`).
- **ORM**: SQLAlchemy 2.0 con modelos tipados (`Mapped[...]`).
- **Base de datos**: PostgreSQL (Supabase), esquema de trabajo `mansillas`.
- **Driver**: `psycopg` (v3). `config.normalizar_database_url` reescribe
  `postgresql://` a `postgresql+psycopg://`.
- **Config**: `pydantic-settings` leyendo variables de entorno y `backend/.env`.
  Ningún secreto vive en el código.
- **Librerías de dominio**: `pyjwt`, `bcrypt`, `qrcode[pil]`, `reportlab`,
  `user-agents`, `supabase`.
- **Gestor de paquetes**: `uv` con lockfile. Instalar con `uv sync --locked`
  (no modificar `uv.lock`).

## Comandos (Windows / PowerShell)
```powershell
# Sincronizar dependencias según el lockfile (no reinstala uv ni toca uv.lock)
uv sync --locked

# Iniciar el backend localmente
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# Swagger: http://127.0.0.1:8000/docs

# Pruebas (requiere TEST_DATABASE_URL a una BD aislada y desechable)
$env:TEST_DATABASE_URL = "postgresql+psycopg://usuario:clave@127.0.0.1:PUERTO/mansillas_test"
uv run pytest
```

## Variables de entorno
Fuente: `.env.example` y `app/config.py`. (No se muestran valores reales.)

| Variable | Obligatoria | Uso |
| --- | --- | --- |
| `DATABASE_URL` | Sí | Conexión SQLAlchemy; se normaliza el driver |
| `JWT_SECRET` | Sí en prod | Firma del JWT |
| `FRONTEND_URL` | Sí | CORS y URL embebida en el QR |
| `APP_ENV` | No | `development` (def.) / `production`. En producción desactiva el stub de desarrollo |
| `SESSION_INACTIVITY_MINUTES` / `SESSION_MAX_HOURS` | No | 30 / 12 por defecto |
| `DEV_USER_ID` | No | Usuario que resuelve el stub de desarrollo |
| `SUPABASE_URL` / `SUPABASE_KEY` | No | Cliente Supabase (hoy no usado por los routers) |

No modificar `.env`. Si se necesita configuración, aplicarla manualmente.

## Seguridad y autorización (establecido)
- Autenticación por JWT (`PyJWT`) + sesión en `sesion_usuario`: se guarda el
  **hash SHA-256** del token, se valida expiración e inactividad en SQL y se
  actualiza `ultima_actividad`.
- Dos módulos RBAC coexisten (deuda técnica documentada por sus autores):
  - `app/deps.py` → routers de **negocio** (visitas, sillas, qr, accesos).
    Contrato `CurrentUser` (dataclass). Helpers: `get_current_user`,
    `require_role(...)`, `ComercialUser`, `require_tecnico_owns_visita`.
  - `app/dependencies.py` → routers de **seguridad** (auth, usuarios).
    Contrato `UsuarioPublico` (Pydantic).
- Para mis historias (negocio) usar **`app/deps.py`**. No unificar ambos módulos
  dentro de mis historias.
- Columnas generadas por la BD (`codigo_qr`, `token_publico`, `numero_qr`) se
  marcan `FetchedValue()` en el modelo; no las fija el backend.
- Los triggers son garantías de integridad, **no** sustituyen las validaciones
  de autorización, entradas, OTP y transacciones que corresponden al backend.

## Convenciones observadas
- Routers delgados; esquemas Pydantic definidos en el propio router.
- `IntegrityError` → `HTTPException` (409/400) con mensaje de dominio.
- Un modelo por tabla; `__table_args__ = {"schema": settings.db_schema}`.
- Nombres de dominio en español; docstrings mixtos español/inglés.
- `config.is_production` controla comportamientos de producción (`production`/`prod`).

## Decisiones pendientes
- Python 3.13 vs 3.14 a nivel de equipo (se mantiene 3.14 por `.python-version`).
- Uso real de `app/supabase_client.py` (hoy sin consumir en los routers).
- Proveedor de correo/OTP para HU-13/HU-15.
- HU-10 almacenamiento de fotos: elegir la alternativa **más sencilla y
  suficiente** para el MVP (carpeta de archivos persistente o Supabase Storage).
  No es obligatorio Supabase Storage. Una sola implementación, sin abstracción de
  proveedores; validaciones de archivo, autorización y consistencia de datos
  esenciales; sin miniaturas, compresión ni colas. Justificar en `design.md`.

## Riesgos y restricciones
- **Stub de desarrollo** `X-Dev-User-Id` en `deps.py`: `get_current_user` lo
  acepta cuando `app_env` **no** es `production`/`prod`. Si un despliegue no fija
  `APP_ENV`, el stub quedaría activo y permitiría actuar como cualquier usuario
  sin token. Es solo mecanismo de desarrollo/pruebas; documentarlo, no usarlo en
  producción.
- `app/routers/usuarios.py` no aplica guardas de rol en sus endpoints. Pertenece
  a otro desarrollador: documentar el riesgo, no corregir.
- `conftest.py` ejecuta `DROP SCHEMA mansillas CASCADE` sobre `TEST_DATABASE_URL`.
  Prohibido apuntarlo a Supabase/producción o a cualquier BD compartida. No
  modificar `conftest.py` para evadir esta protección. No se usa Docker.
- No modificar el esquema SQL ni ejecutar migraciones sin aprobación.
- No conectar a bases de datos remotas sin autorización explícita. Queda prohibido
  ejecutar pruebas destructivas contra la base de datos compartida de Supabase.
