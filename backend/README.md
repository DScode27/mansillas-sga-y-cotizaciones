# Mansillas SIC — Backend

API **FastAPI + SQLAlchemy 2.0 + psycopg 3** sobre el esquema PostgreSQL
existente `mansillas` (Supabase). Cubre autenticación con sesiones, el
levantamiento de inventario (visitas y sillas con QR), el checklist de
componentes y fotos, la descarga de etiquetas QR en PDF, la exportación del
inventario (CSV/XLSX), las precotizaciones con aceptación por OTP, el catálogo
organizacional (empresas → sedes → departamentos → empleados) y la trazabilidad
de accesos a precotizaciones.

> **Documentación relacionada**
> - Arquitectura completa, diagramas y modelo de datos: [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
> - Despliegue: [`../DEPLOY.md`](../DEPLOY.md)
> - Requisitos, reglas de negocio y matriz RBAC: [`../ERS_Mansillas_secciones.md`](../ERS_Mansillas_secciones.md)
> - Visión de toda la aplicación: [`../README.md`](../README.md)

## Requisitos

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL 14+ (el esquema vive en la base de Supabase o en una copia local)

## Instalación

```bash
cd backend
uv sync
```

## Estructura del proyecto

```
backend/
├── app/
│   ├── main.py            # App FastAPI: CORS y registro de routers
│   ├── config.py          # Settings desde entorno (.env); sin secretos en código
│   ├── db.py              # Engine y sesión SQLAlchemy (get_db)
│   ├── security.py        # bcrypt, JWT (HS256), hash SHA-256 del token
│   ├── deps.py            # RBAC y sesión para routers de negocio (CurrentUser)
│   ├── dependencies.py    # RBAC y sesión para routers de seguridad (UsuarioPublico)
│   ├── schemas.py         # Esquemas Pydantic compartidos
│   ├── models/            # Modelos SQLAlchemy (una tabla por archivo)
│   ├── routers/           # Capa HTTP: valida, aplica RBAC, delega en services
│   └── services/          # Lógica de negocio, SQL, reglas, OTP, correo, export
├── database/
│   ├── SQLMansillasSIC.sql # Esquema completo (tablas, triggers, vistas, seed)
│   ├── seed_dev.py         # Datos de desarrollo
│   └── migrations/
├── scripts/               # Utilidades de CLI (crear usuario, etc.)
├── tests/                 # Suite pytest + hypothesis
├── var/fotos/             # Almacenamiento local de fotos (efímero en PaaS)
└── pyproject.toml
```

La separación **routers → services → models** mantiene los routers enfocados en
HTTP y RBAC, y concentra las reglas en los servicios. Ver el diagrama de
componentes del backend más abajo.

## Variables de entorno

Copia `.env.example` a `.env` y completa los valores:

| Variable | Obligatoria | Descripción |
| --- | --- | --- |
| `DATABASE_URL` | Sí | Cadena SQLAlchemy `postgresql+psycopg://usuario:clave@host:puerto/basedatos` (se normaliza el driver si viene como `postgresql://`) |
| `JWT_SECRET` | Sí en producción | Secreto de firma del JWT. Generar con `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `OTP_SECRET` | Sí para OTP | Secreto **independiente** de `JWT_SECRET` para el OTP de aceptación (HU-15). Vacío por defecto: la app arranca, pero las operaciones OTP fallan con error controlado |
| `FRONTEND_URL` | Sí | URL del frontend Vite; se usa para CORS y para la URL codificada en cada QR (`{FRONTEND_URL}/qr/{token_publico}`) y el enlace de propuesta (`{FRONTEND_URL}/propuesta/{token}`) |
| `DB_SCHEMA` | No | Esquema de trabajo. Por defecto `mansillas` |
| `APP_ENV` | No | `development` (por defecto) o `production` |
| `JWT_ALGORITHM` | No | `HS256` por defecto |
| `SESSION_INACTIVITY_MINUTES` | No | Minutos de inactividad antes de cerrar la sesión. Por defecto `30` (HU-25) |
| `SESSION_MAX_HOURS` | No | Vida máxima absoluta de la sesión. Por defecto `12` |
| `PHOTO_STORAGE_DIR` | No | Carpeta de fotos; por defecto `var/fotos` (relativa a `backend/`) |
| `DEV_USER_ID` | No | Id del usuario que resuelve el stub de desarrollo (ignorado en producción) |
| `SUPABASE_URL` / `SUPABASE_KEY` | No | Cliente Supabase para módulos auxiliares |

Ningún secreto se guarda en el código: todo se lee de variables de entorno.

### Envío de correo (SMTP)

El sistema envía correos en tres flujos: el enlace de la precotización (HU-13),
el código OTP para aceptar la propuesta (HU-15) y el código OTP para enviar un
ticket desde el QR (HU-24). El transporte es SMTP estándar (`smtplib` + TLS);
no hace falta instalar nada. Sin configurar SMTP la app arranca igual: el envío
queda deshabilitado con un error controlado (503) y, en desarrollo, los códigos
OTP se escriben al log.

Para que el correo sea **funcional y gratis** (proyecto universitario), la
opción más simple es **Gmail con contraseña de aplicación**:

1. En tu cuenta de Gmail activa la **Verificación en 2 pasos**.
2. Ve a <https://myaccount.google.com/apppasswords> y genera una **contraseña
   de aplicación** de 16 caracteres (no cuesta nada ni pide tarjeta).
3. En `backend/.env` pon:

   ```env
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=tucuenta@gmail.com
   SMTP_PASSWORD=la-contraseña-de-aplicacion-de-16-caracteres
   SMTP_FROM=tucuenta@gmail.com
   SMTP_TLS=true
   ```

Usa la contraseña de aplicación como `SMTP_PASSWORD`, **nunca** tu contraseña
normal de Gmail. Alternativa sin tarjeta: **Brevo** (300 correos/día gratis);
ver los valores comentados en `backend/.env.example`.

## Componentes del backend

```mermaid
flowchart LR
    cliente["Cliente HTTP"]
    subgraph App["app.main"]
        routers["Routers<br/>(HTTP + RBAC)"]
        deps["deps / dependencies<br/>get_current_user, require_role"]
        services["Services<br/>(reglas, SQL, OTP, correo, export)"]
        models["Models (SQLAlchemy)"]
    end
    db[("PostgreSQL mansillas")]
    disco[("var/fotos")]
    smtp["SMTP"]

    cliente -->|Bearer JWT| deps
    cliente --> routers
    routers --> deps
    routers --> services
    services --> models --> db
    services --> disco
    services --> smtp
```

El detalle (modelo de datos, flujos de secuencia y decisiones de diseño) está en
[`../ARCHITECTURE.md`](../ARCHITECTURE.md).

## Autenticación

`POST /auth/login` con `{"correo": ..., "password": ...}` devuelve un JWT y los
datos públicos del usuario (`id_usuario`, `nombre`, `correo`, `rol`,
`id_empresa`). Solo `COMERCIAL_MANSILLAS`, `TECNICO` y `ADMIN_CLIENTE` inician
por contraseña; el empleado del cliente entra por el flujo QR con OTP.

El token se envía como `Authorization: Bearer <jwt>`. Cada petición autenticada:

1. Verifica la firma y la expiración del JWT.
2. Busca el `SHA-256` del token en `sesion_usuario` (nunca se guarda el token en claro).
3. Rechaza sesiones cerradas o expiradas.
4. Cierra la sesión si superó `SESSION_INACTIVITY_MINUTES` sin uso (HU-25).
5. Actualiza `ultima_actividad` y resuelve el usuario **desde la tabla
   `usuario`**, nunca desde el token ni desde cabeceras.

Fuera de producción también se acepta el stub de desarrollo (`X-Dev-User-Id: <id>`
o `DEV_USER_ID`) para scripts de CLI y tests; con `APP_ENV=production` el stub se
desactiva.

> **Nota de diseño:** existen dos módulos de dependencias que validan la sesión
> con contratos distintos: `app/dependencies.py` (`UsuarioPublico`, para
> `auth`/`usuarios`) y `app/deps.py` (`CurrentUser`, para el resto). Documentado
> como deuda técnica a unificar.

### Crear el primer usuario

```bash
uv run python scripts/create_user.py \
    --nombre "Comercial Mansillas" --correo comercial@mansillas.com \
    --password "Secreta123" --rol COMERCIAL_MANSILLAS
```

Para roles de cliente añadir `--empresa <id_empresa>`.

### Datos de desarrollo

```bash
uv run python database/seed_dev.py
```

Crea empresa, sede, departamento, empleado y dos usuarios (comercial y técnico)
e imprime sus ids.

## Endpoints

Resumen por router. Los códigos de estado completos están documentados en el
OpenAPI que genera FastAPI (`/docs`).

### Autenticación y usuarios

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| `POST` | `/auth/login` | Público | Inicia sesión y devuelve el JWT |
| `GET` | `/auth/me` | Autenticado | Usuario de la sesión actual |
| `POST` | `/auth/logout` | Autenticado | Revoca la sesión (marca `fecha_cierre`) |
| `GET` | `/usuarios` | COMERCIAL | Lista usuarios |
| `POST` | `/usuarios` | COMERCIAL | Crea un usuario (contraseña hasheada) |
| `PUT` | `/usuarios/{id}/rol` | COMERCIAL | Asigna rol (y empresa si aplica) |

### Catálogo organizacional (RF-26 a RF-28)

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| `GET` | `/empresas` | Internos / ADMIN_CLIENTE | Internos ven todas; ADMIN_CLIENTE solo la suya |
| `POST` | `/empresas` | COMERCIAL | Crea empresa (NIT único → 409 si repetido) |
| `GET` | `/empresas/{id}/sedes` | Internos / ADMIN_CLIENTE | Sedes de la empresa (alcance por rol) |
| `POST` | `/empresas/{id}/sedes` | COMERCIAL / ADMIN_CLIENTE | Crea sede (nombre único por empresa) |
| `GET` | `/sedes/{id}/departamentos` | Internos / ADMIN_CLIENTE | Departamentos de la sede |
| `POST` | `/sedes/{id}/departamentos` | COMERCIAL / ADMIN_CLIENTE | Crea departamento (nombre único por sede) |
| `GET` | `/empresas/{id}/empleados` | Internos / ADMIN_CLIENTE | Empleados de la empresa |
| `POST` | `/empresas/{id}/empleados` | COMERCIAL / ADMIN_CLIENTE | Crea empleado (documento único por empresa) |
| `POST` | `/carga-masiva/empleados` | ADMIN_CLIENTE | Carga masiva de empleados por `.xlsx` (HU-19) |

### Visitas, sillas, componentes y fotos

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| `POST` | `/visitas` | COMERCIAL | Crea una visita (empresa, sede, técnico, `cantidad_estimada`) |
| `GET` | `/visitas` | COMERCIAL / TECNICO | Comercial ve todas; técnico solo las asignadas |
| `GET` | `/visitas/{id}` | COMERCIAL / TECNICO | Técnico solo sus visitas (403 si es ajena) |
| `PUT` | `/visitas/{id}` | COMERCIAL | Actualiza; `cantidad_estimada` nunca se reescribe (RN-04) |
| `PUT` | `/visitas/{id}/finalizar` | TECNICO | El técnico dueño marca la visita `FINALIZADA` (HU-28) |
| `DELETE` | `/visitas/{id}` | COMERCIAL | 204, o 409 si la visita ya tiene sillas |
| `POST` | `/visitas/{id}/sillas` | TECNICO | Registra una silla en una visita propia |
| `GET` | `/sillas?id_visita=` | COMERCIAL / TECNICO | Lista las sillas de una visita |
| `GET` | `/sillas/{id}` | COMERCIAL / TECNICO | Ficha de la silla (técnico solo de sus visitas) |
| `GET` | `/sillas/token/{token}` | Público | Datos públicos de la silla por `token_publico` |
| `PUT` | `/sillas/{id}` | TECNICO | Actualiza `serial_antiguo` y `observaciones` |
| `PUT` | `/sillas/{id}/comercial` | COMERCIAL | Edición del levantamiento antes de la precotización (HU-12) |
| `GET` | `/sillas/{id}/componentes` | COMERCIAL / TECNICO | Checklist + `sugerir_cambio` |
| `PUT` | `/sillas/{id}/componentes` | TECNICO | Guarda el estado de los componentes (RF-08) |
| `POST` | `/sillas/{id}/fotos` | TECNICO | Sube una foto (multipart) |
| `GET` | `/sillas/{id}/fotos` | COMERCIAL / TECNICO / ADMIN_CLIENTE | Lista fotos de la silla |
| `GET` | `/sillas/{id}/fotos/{idFoto}` | Según silla | Sirve los bytes de la foto |

### QR, inventario y portal cliente

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| `GET` | `/qr/silla/{token}` | Público | Ficha pública de la silla + `permiso_qr` (HU-17) |
| `GET` | `/qr/silla/{token}/fotos` | Público | Ids de fotos de la silla |
| `GET` | `/qr/silla/{token}/fotos/{id}` | Público | Bytes de una foto (por token) |
| `POST` | `/qr/silla/{token}/otp` | Público | OTP para el empleado (correo o documento, HU-24) |
| `POST` | `/qr/silla/{token}/ticket` | Público | Crea ticket según `permiso_qr` y OTP (HU-24) |
| `POST` | `/qr/pdf` | COMERCIAL / TECNICO | PDF con las etiquetas QR (`{"ids": [...]}`) |
| `GET` | `/qr/empresas/{id}/permiso-qr` | ADMIN_CLIENTE | Lee el nivel de permiso QR (HU-18) |
| `PUT` | `/qr/empresas/{id}/permiso-qr` | ADMIN_CLIENTE | Cambia el nivel 1/2/3 |
| `GET` | `/inventario/` | COMERCIAL / ADMIN_CLIENTE | Inventario con alcance por rol (HU-11) |
| `GET` | `/inventario/exportar?formato=` | COMERCIAL / ADMIN_CLIENTE | Exporta `csv` o `xlsx` |
| `GET` | `/portal-cliente/sillas` | ADMIN_CLIENTE | Sillas de su empresa (solo lectura, R4) |
| `GET` | `/portal-cliente/precotizaciones` | ADMIN_CLIENTE | Precotizaciones de su empresa |

### Precotizaciones y accesos

| Método | Ruta | Rol | Descripción |
| --- | --- | --- | --- |
| `GET` | `/visitas/{id}/levantamiento` | COMERCIAL | Revisión del levantamiento para precotizar (HU-12) |
| `POST` | `/precotizaciones` | COMERCIAL | Crea `BORRADOR` con `confirmar_validacion=true` |
| `GET` | `/precotizaciones?id_visita=` | COMERCIAL | Lista precotizaciones de la visita |
| `POST` | `/precotizaciones/{id}/enviar` | COMERCIAL | Envía el enlace por correo; pasa a `ENVIADA` (HU-13) |
| `GET` | `/precotizaciones/{id}/habilitacion-cotizacion` | COMERCIAL | Si está habilitada la cotización (HU-16) |
| `GET` | `/precotizaciones/{id}/accesos` | COMERCIAL | Accesos al enlace público (HU-14) |
| `GET` | `/propuesta/{token}` | Público | Propuesta `ENVIADA`/`ACEPTADA`; registra el acceso |
| `POST` | `/propuesta/{token}/otp` | Público | Solicita OTP al correo almacenado (HU-15) |
| `POST` | `/propuesta/{token}/aceptar` | Público | Acepta con nombre, cargo y OTP; bloquea la propuesta (RN-09) |

Funciones internas que consumen otros módulos:

- `app.routers.sillas.get_silla_by_token(db, token)` → `Silla | None`
- `app.routers.accesos.registrar_acceso(db, precotizacion_id, user_agent)` → `AccesoPrecotizacion`

## Modelo de datos y reglas de negocio

El esquema completo (18 tablas, secuencia, 4 *triggers* y la vista
`vista_estado_mantenimiento`) está en
[`database/SQLMansillasSIC.sql`](database/SQLMansillasSIC.sql) y el diagrama ER
en [`../ARCHITECTURE.md`](../ARCHITECTURE.md#6-modelo-de-datos). Reglas que el
backend (y la base) imponen:

- **RN-02 — QR único y consecutivo.** `silla.numero_qr` usa la secuencia
  `secuencia_qr` y el *trigger* `generar_codigo_qr` produce `codigo_qr` con
  formato `SIC-00000001`. El backend inserta `codigo_qr = ''` y lee el valor;
  nunca calcula códigos ni tokens (`token_publico` usa `gen_random_uuid()`).
- **RN-03 — Serial antiguo único por empresa.** `UNIQUE (id_empresa,
  serial_antiguo)`; un duplicado responde `409`.
- **RN-04 — Cantidad estimada inmutable.** La cantidad de sillas puede superar
  lo estimado; `cantidad_estimada` nunca se reescribe al actualizar la visita.
- **RN-09 — Precotización aceptada bloqueada.** El *trigger*
  `impedir_edicion_precotizacion_aceptada` rechaza modificar o borrar una
  precotización `ACEPTADA`; la edición del levantamiento se rechaza con `409`
  cuando la propuesta está `ENVIADA`/`ACEPTADA` (`precotizacion_rules`).
- **RN-13 — Aislamiento multiempresa.** Alcance derivado de `empresa_id` del
  usuario y FK compuestas `(id_empresa, id_*)`.
- **HU-16 — Habilitación de cotización.** Solo si la precotización está
  `ACEPTADA` y existe su fila de aceptación
  (`estado_habilitacion_cotizacion`).

## Pruebas

La suite necesita una base PostgreSQL descartable: `TEST_DATABASE_URL` se usa
para recrear el esquema `mansillas` desde `database/SQLMansillasSIC.sql` antes de
correr. **Nunca apuntes esa variable a la base real: las pruebas hacen
`DROP SCHEMA`.**

```bash
export TEST_DATABASE_URL="postgresql+psycopg://postgres@127.0.0.1:55432/mansillas_test"
uv run pytest -q
```

Cobertura de las reglas críticas (≥100 iteraciones cada una):

1. Un técnico solo ve sus propias visitas.
2. Los códigos QR nunca se reutilizan, ni siquiera tras eliminar sillas.
3. Un serial antiguo duplicado dentro de la misma empresa se rechaza con `409`.

Más la autenticación: login válido e inválido, token sin sesión, sesión cerrada,
sesión expirada, cierre por inactividad y actualización de `ultima_actividad`.

## Frontend

El frontend está en [`../frontend/`](../frontend/README.md) (Vite + React):

```bash
cd frontend
npm ci
npm run dev
```

Consume `VITE_API_URL` (por defecto `http://127.0.0.1:8000`).

## Despliegue piloto

Render o Railway funcionan con la misma configuración por variables de entorno:

- Build: `uv sync --frozen --no-dev`
- Start: `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Antes de desplegar: aplicar `database/SQLMansillasSIC.sql` sobre la base destino
y definir `DATABASE_URL`, `JWT_SECRET`, `OTP_SECRET`, `FRONTEND_URL` y
`APP_ENV=production`. Guía completa en [`../DEPLOY.md`](../DEPLOY.md).
