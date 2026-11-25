# Mansillas SIC - Backend

API FastAPI + SQLAlchemy sobre el esquema PostgreSQL existente `mansillas` (Supabase).
Cubre autenticación con sesiones, el levantamiento de inventario (visitas y sillas con QR),
la descarga de etiquetas QR y la trazabilidad de accesos a precotizaciones.

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
| `DATABASE_URL` | Sí | Cadena SQLAlchemy `postgresql+psycopg://usuario:clave@host:puerto/basedatos` (se normaliza el driver si viene como `postgresql://`) |
| `JWT_SECRET` | Sí en producción | Secreto de firma del JWT. Generar con `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `FRONTEND_URL` | Sí | URL del frontend Vite; se usa para CORS y para la URL codificada en cada QR (`{FRONTEND_URL}/silla/{token_publico}`) |
| `DB_SCHEMA` | No | Esquema de trabajo. Por defecto `mansillas` |
| `APP_ENV` | No | `development` (por defecto) o `production` |
| `JWT_ALGORITHM` | No | `HS256` por defecto |
| `SESSION_INACTIVITY_MINUTES` | No | Minutos de inactividad antes de cerrar la sesión. Por defecto `30` (HU-25) |
| `SESSION_MAX_HOURS` | No | Vida máxima absoluta de la sesión. Por defecto `12` |
| `DEV_USER_ID` | No | Id del usuario que resuelve el stub de desarrollo (ignorado en producción) |
| `SUPABASE_URL` / `SUPABASE_KEY` | No | Cliente Supabase para los módulos de otros compañeros |

Ningún secreto se guarda en el código: todo se lee de variables de entorno.

## Autenticación

`POST /auth/login` con `{"correo": ..., "password": ...}` devuelve un JWT y los datos
públicos del usuario (`id_usuario`, `nombre`, `correo`, `rol`, `id_empresa`).
Solo `COMERCIAL_MANSILLAS`, `TECNICO` y `ADMIN_CLIENTE` inician por contraseña; el
empleado del cliente entra por el flujo QR con OTP.

El token se envía como `Authorization: Bearer <jwt>`. Cada petición autenticada:

1. Verifica la firma y la expiración del JWT.
2. Busca el `SHA-256` del token en `sesion_usuario` (nunca se guarda el token en claro).
3. Rechaza sesiones cerradas o expiradas.
4. Cierra la sesión si superó `SESSION_INACTIVITY_MINUTES` sin uso (HU-25).
5. Actualiza `ultima_actividad` y resuelve `CurrentUser(id, rol, empresa_id)` **desde la
   tabla `usuario`**, nunca desde el token ni desde cabeceras.

Fuera de producción también se acepta el stub de desarrollo (`X-Dev-User-Id: <id>` o
`DEV_USER_ID`) para scripts de CLI y tests; con `APP_ENV=production` el stub se desactiva.

### Crear el primer usuario

```bash
uv run python create_user.py \
    --nombre "Comercial Mansillas" --correo comercial@mansillas.com \
    --password "Secreta123" --rol COMERCIAL_MANSILLAS
```

Para roles de cliente añadir `--empresa <id_empresa>`.

### Datos de desarrollo

```bash
uv run python database/seed_dev.py
```

Crea empresa, sede, departamento, empleado y dos usuarios (comercial y técnico) e imprime sus ids.

## Endpoints

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| `POST` | `/auth/login` | Público | Inicia sesión y devuelve el JWT |
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
**Nunca apuntes esa variable a la base real: las pruebas hacen `DROP SCHEMA`.**

```bash
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres@127.0.0.1:55432/mansillas_test"  # PowerShell
uv run pytest -q
```

Cobertura de las tres reglas críticas (≥100 iteraciones cada una):

1. Un técnico solo ve sus propias visitas.
2. Los códigos QR nunca se reutilizan, ni siquiera tras eliminar sillas.
3. Un serial antiguo duplicado dentro de la misma empresa se rechaza con `409`.

Más la autenticación: login válido e inválido, token sin sesión, sesión cerrada,
sesión expirada, cierre por inactividad y actualización de `ultima_actividad`.

## Frontend

El frontend está en `frontend/` (Vite + React):

```bash
cd frontend
npm ci
npm run dev
```

Consume `VITE_API_URL` (por defecto `http://127.0.0.1:8000`). Los recursos que todavía
no tienen endpoint se sirven desde `src/api/mocks.js`.

## Despliegue piloto

Render o Railway funcionan con la misma configuración por variables de entorno:

- Build: `uv sync --frozen --no-dev`
- Start: `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Antes de desplegar: aplicar `database/SQLMansillasSIC.sql` sobre la base destino y definir
`DATABASE_URL`, `JWT_SECRET`, `FRONTEND_URL` y `APP_ENV=production`.
