# Despliegue de MansillasSIC

Guía para montar el proyecto fuera de localhost. La base de datos ya está en
**Supabase**; falta publicar el **backend** (FastAPI) y el **frontend** (Vite +
React). Todo se configura por variables de entorno; **ningún secreto va al
repositorio**.

Arquitectura:

```
Navegador ──> Frontend (Vercel/Netlify, estático)
                     │  VITE_API_URL
                     ▼
              Backend (Render/Railway, FastAPI/uvicorn)
                     │  DATABASE_URL
                     ▼
              PostgreSQL (Supabase)  ← ya existe
```

---

## 1. Backend (Render o Railway)

El backend es FastAPI servido con uvicorn, gestionado con `uv`.

- **Build:** `uv sync --frozen --no-dev`
- **Start:** `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Directorio raíz del servicio:** `backend/`
- **Runtime:** Python 3.13

### Variables de entorno (backend)

| Variable | Valor / nota |
| --- | --- |
| `DATABASE_URL` | Cadena de conexión de Supabase (usa el *connection pooler*, puerto 5432, con `sslmode=require`). Se acepta `postgresql://...`; el backend fuerza el driver `psycopg`. |
| `APP_ENV` | `production` (desactiva el stub de desarrollo `X-Dev-User-Id`). |
| `JWT_SECRET` | Secreto largo. Generar con `python -c "import secrets;print(secrets.token_urlsafe(48))"`. |
| `FRONTEND_URL` | URL pública del frontend (p. ej. `https://mansillas.vercel.app`). Se usa para CORS y para el enlace del QR/propuesta. |
| `OTP_SECRET` | Secreto independiente del JWT (mismo método para generarlo). Necesario para el OTP de aceptación de propuesta. |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_TLS` | Envío de correo. Ver `backend/README.md` (Gmail con contraseña de aplicación es gratis y sin tarjeta). Sin esto, los correos quedan deshabilitados con error controlado. |
| `DB_SCHEMA` | Opcional, por defecto `mansillas`. |

> El `cors_origins` del backend deriva de `FRONTEND_URL` (más los localhost de
> desarrollo), así que basta con poner bien `FRONTEND_URL` para que el frontend
> publicado pueda llamar al backend.

### Comprobación

- `GET /health` debe responder `{"status":"ok"}`.
- `GET /` responde el nombre del servicio.

---

## 2. Frontend (Vercel o Netlify)

Proyecto Vite/React; se compila a estático.

- **Directorio raíz:** `frontend/`
- **Build:** `npm ci && npm run build`
- **Carpeta publicada:** `dist`

### Variables de entorno (frontend)

| Variable | Valor |
| --- | --- |
| `VITE_API_URL` | URL pública del backend (p. ej. `https://mansillas-api.onrender.com`). Sin barra final. |

Tras desplegar el backend, pon su URL en `VITE_API_URL` y **recompila** el
frontend (las variables `VITE_*` se incrustan en el build, no en tiempo de
ejecución).

---

## 3. Orden sugerido

1. Despliega el backend y anota su URL pública.
2. Configura `VITE_API_URL` en el frontend con esa URL y despliega el frontend.
3. Vuelve al backend y pon `FRONTEND_URL` con la URL del frontend (para CORS y
   los enlaces de correo). Redeploy del backend si hiciste el cambio después.
4. Configura las variables SMTP y prueba el envío de una precotización.

---

## 4. Limitación conocida: fotos en disco

Las fotos de las sillas se guardan en disco local del backend
(`photo_storage_dir`, por defecto `backend/var/fotos`). En plataformas PaaS con
**disco efímero** (plan gratis de Render/Railway), ese disco se borra en cada
reinicio o redeploy, así que **las fotos subidas se pierden**. Opciones:

- Para una demo/sustentación: subir las fotos justo antes y evitar reinicios.
- Para persistencia real: adjuntar un disco persistente (si el plan lo permite)
  o migrar el almacenamiento a **Supabase Storage**. Esa migración está **fuera
  del alcance actual**; se documenta como trabajo futuro.

El resto de los datos (sillas, componentes, visitas, usuarios, precotizaciones)
vive en Supabase y **sí persiste**.
