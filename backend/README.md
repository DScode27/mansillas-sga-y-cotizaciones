# Mansillas SIC - Backend

API FastAPI + SQLAlchemy sobre el esquema PostgreSQL existente `mansillas` (Supabase).
Cubre el alcance del módulo de levantamiento de inventario: visitas, sillas con QR,
descarga de etiquetas QR y trazabilidad de accesos a precotizaciones.

## Requisitos

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 14+ (el esquema vive en la base de Supabase o en una copia local)

## Instalación

```bash
cd backend
uv sync
```

## Variables de entorno

Copia `.env.example` a `.env` y completa los valores:

| Variable | Obligatoria | Descripción |
| --- | --- | --- |
| `DATABASE_URL` | Sí | Cadena SQLAlchemy `postgresql+psycopg://usuario:clave@host:puerto/basedatos` |
| `DB_SCHEMA` | No | Esquema de trabajo. Por defecto `mansillas` |
| `FRONTEND_URL` | Sí | URL pública del frontend; se usa para CORS y para la URL codificada en cada QR (`{FRONTEND_URL}/silla/{token_publico}`) |
| `APP_ENV` | No | `development` (por defecto) o `production` |
| `DEV_USER_ID` | No | Id del usuario que resuelve el stub de autenticación de desarrollo |
| `SUPABASE_URL` / `SUPABASE_KEY` | No | Cliente Supabase para los módulos de otros compañeros |

Ningún secreto se guarda en el código: todo se lee de variables de entorno.

## Autenticación (stub de desarrollo)

La autenticación real es responsabilidad de otro módulo. Mientras tanto `app/deps.py`
resuelve el usuario actual a partir de un identificador y lee el rol y la empresa
**siempre** de la tabla `usuario`:

```http
X-Dev-User-Id: 6
```

Con `APP_ENV=production` el stub se desactiva (`501`) hasta que se integre el
resolvedor definitivo.

### Datos de desarrollo

```bash
uv run python database/seed_dev.py
```

Crea una empresa, una sede, un departamento, un empleado y dos usuarios
(`comercial@mansillas.test`, `tecnico@mansillas.test`) e imprime sus ids.

## Endpoints

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| `POST` | `/visitas` | COMERCIAL | Crea una visita (empresa, sede, técnico, `cantidad_estimada`) |
| `GET` | `/visitas` | COMERCIAL / TECNICO | Comercial ve todas; técnico solo las asignadas a él |
| `GET` | `/visitas/{id}` | COMERCIAL / TECNICO | Técnico solo sus visitas (403 si es ajena) |
| `PUT` | `/visitas/{id}` | COMERCIAL | Actualiza la visita; `cantidad_estimada` nunca se reescribe (RN-04) |
| `DELETE` | `/visitas/{id}` | COMERCIAL | 204, o 409 si la visita ya tiene sillas |
| `POST` | `/visitas/{id}/sillas` | TECNICO | Registra una silla en una visita propia |
| `GET` | `/sillas/{id}` | COMERCIAL / TECNICO | Ficha de la silla (técnico solo de sus visitas) |
| `GET` | `/sillas/token/{token}` | Público | Datos públicos de la silla a partir de su `token_publico` |
| `PUT` | `/sillas/{id}` | TECNICO | Actualiza `serial_antiguo` y `observaciones` |
| `POST` | `/qr/pdf` | COMERCIAL / TECNICO | PDF con las etiquetas QR (`{"ids": [...]}`) |
| `GET` | `/precotizaciones/{id}/accesos` | COMERCIAL | Accesos al enlace público de la precotización |

Funciones internas que consumen otros módulos:

- `app.routers.sillas.get_silla_by_token(db, token)` → `Silla | None`
- `app.routers.accesos.registrar_acceso(db, precotizacion_id, user_agent)` → `AccesoPrecotizacion`

## El esquema lo genera la base de datos

- `silla.numero_qr` usa la secuencia `secuencia_qr` y el trigger `generar_codigo_qr`
  produce `codigo_qr` con formato `SIC-00000001`.
- `silla.token_publico` usa `gen_random_uuid()`.

El backend inserta `codigo_qr = ''` y luego lee el valor asignado. Nunca calcula
códigos ni tokens.

## Pruebas

La suite necesita una base PostgreSQL descartable: `TEST_DATABASE_URL` se usa para
recrear el esquema `mansillas` desde `database/SQLMansillasSIC.sql` antes de correr.

```bash
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres@127.0.0.1:55432/mansillas_test"  # PowerShell
uv run pytest -q
```

Cobertura de las tres reglas críticas (≥100 iteraciones cada una):

1. Un técnico solo ve sus propias visitas.
2. Los códigos QR nunca se reutilizan, ni siquiera tras eliminar sillas.
3. Un serial antiguo duplicado dentro de la misma empresa se rechaza con `409`.

## Despliegue piloto

Render o Railway funcionan con la misma configuración por variables de entorno:

- Build: `uv sync --frozen --no-dev`
- Start: `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Antes de desplegar: aplicar `database/SQLMansillasSIC.sql` sobre la base destino,
definir `DATABASE_URL`, `FRONTEND_URL`, `APP_ENV=production` e integrar la
autenticación real (el stub devuelve `501` en producción).
