# Integración de endpoints — frontend ↔ backend

Estado del cableado entre la capa `src/api/` del frontend y los endpoints del
backend. Dos tipos de backend:

- **Seguridad (mío):** existe y se consume directo (sin mock): `auth`, `usuarios`.
- **Recursos de otros devs:** aún no existen del todo; el frontend los consume
  con **mock conmutable** por recurso en `src/api/mocks.js` (`USE_MOCK.*`). Cuando
  el endpoint real exista, se pone su bandera en `false` sin tocar las pantallas.

## Endpoints del backend y su función en el frontend

| Endpoint backend | Función en `src/api/` | Pantalla conectada | Estado |
|---|---|---|---|
| `POST /auth/login` | `login` (`auth.js`) | `LoginPage` | Conectado (directo) |
| `POST /auth/logout` | `logout` (`auth.js`) | `AppLayout` | Conectado (directo) |
| `GET /auth/me` | — | — | **Sin usar** (ver pendientes) |
| `GET /usuarios` | `listUsuarios` (`usuarios.js`) | `UsuariosPage`, `VisitasPage` | Conectado (directo) |
| `POST /usuarios` | `createUsuario` (`usuarios.js`) | `UsuariosPage` | Conectado (directo) |
| `PUT /usuarios/{id}/rol` | `updateRol` (`usuarios.js`) | `UsuariosPage` | Conectado (directo) |
| `GET /visitas` | `listVisitas` (`visitas.js`) | `VisitasPage`, `PortalComercialPage`, `LevantamientoPage` | Conectado (mock) |
| `POST /visitas` | `createVisita` (`visitas.js`) | `VisitasPage` | Conectado (mock) |
| `GET /visitas/{id}` | `getVisita` (`visitas.js`) | — | **Disponible, sin pantalla** |
| `PUT /visitas/{id}` | `updateVisita` (`visitas.js`) | `VisitasPage` (cambio de estado) | Conectado (mock) |
| `DELETE /visitas/{id}` | `deleteVisita` (`visitas.js`) | `VisitasPage` (eliminar) | Conectado (mock) |
| `POST /visitas/{id}/sillas` | `createSilla` (`sillas.js`) | `LevantamientoPage` | Conectado (mock), ver nota 1 |
| `GET /sillas/{id}` | `getSilla` (`sillas.js`) | — | **Disponible, sin pantalla** |
| `PUT /sillas/{id}` | `updateSilla` (`sillas.js`) | — | **Disponible, sin pantalla** |
| `GET /sillas/token/{token}` | `getSillaPublica` (`qr-publico.js`) | `QrPublicoPage` | Conectado (mock), ver nota 2 |
| `POST /qr/pdf` | `descargarQrPdf` (`qr.js`) | — | **Disponible, sin pantalla**, ver nota 3 |
| `GET /precotizaciones/{id}/accesos` | `listAccesos` (`precotizaciones.js`) | `PortalComercialPage` | Conectado (mock) |

## Qué se conectó en esta iteración

- **`PUT /visitas/{id}`** y **`DELETE /visitas/{id}`** → `VisitasPage`: el
  comercial cambia el estado de una visita desde un selector por fila y la
  elimina con confirmación. El 409 (visita con sillas) se muestra como mensaje.
- **`GET /precotizaciones/{id}/accesos`** → `PortalComercialPage`: botón
  "Ver accesos" por precotización que despliega los accesos al enlace público.

## Pendientes

### 1. Sillas: componentes y fotos no tienen endpoint
`POST /visitas/{id}/sillas` (`SillaCreadaOut`) solo persiste datos básicos
(`id_empleado`, `cargo`, `serial_antiguo`, `observaciones`). **No** acepta el
estado de los 5 componentes ni devuelve fotos. Hoy `LevantamientoPage` captura
componentes y fotos; eso vive **solo en el mock**.

- **Pendiente de backend (otro dev):** endpoint para el estado de componentes de
  una silla y endpoint de subida de fotos (`fotografia`).
- **Luego en el frontend:** en `createSilla` enviar los componentes al endpoint
  correspondiente; en `uploadFotoSilla` apuntar a la ruta real (hoy asume
  `POST /sillas/{id}/fotos` con multipart, sin confirmar).

### 2. Ficha pública (QR): el backend no da empresa/sede/componentes
`GET /sillas/token/{token}` devuelve ids, `cargo`, `codigo_qr` y `token_publico`,
pero **no** el nombre de empresa/sede ni el estado de los componentes que la
ficha muestra. `getSillaPublica` mapea de forma tolerante (campos ausentes caen a
`—` o no se renderizan).

- **Pendiente de backend (otro dev):** ampliar el contrato público con
  empresa/sede y componentes (solo datos básicos, sin OTP ni precotización).

### 3. PDF de QR (`POST /qr/pdf`): falta el disparador en pantalla
`descargarQrPdf(ids)` está lista en `api/qr.js` (devuelve el PDF como `Blob`,
bandera `USE_MOCK.qrPdf`), pero **ninguna pantalla la invoca** todavía. Depende
de poder seleccionar sillas reales, y el listado de sillas (`GET /sillas`) aún no
existe en el backend (ver punto 5).

- **Pendiente de frontend:** botón "Descargar QR" en `LevantamientoPage` o
  `PortalComercialPage` que recoja los `id_silla` seleccionados, llame a
  `descargarQrPdf` y dispare la descarga del blob.

### 4. Detalle/edición individual sin pantalla
`getVisita`, `getSilla` y `updateSilla` están listas y apuntan a su ruta real,
pero no hay pantalla de **detalle de visita** ni de **edición de silla**. Se
dejaron disponibles en la capa `api/` para cuando se diseñe ese flujo. No se
inventó UI para no ampliar el alcance.

### 5. Endpoints que el frontend necesita y el backend aún no expone
Estas llamadas existen en `src/api/` (en modo mock) pero **ningún router las
define**; hay que pedirlas a los otros devs:

- `GET /sillas` (listado de sillas, opcional `?id_visita=`) — lo usan
  `LevantamientoPage` y `PortalComercialPage`.
- `GET /precotizaciones` (listado, opcional `?id_visita=`) — `PortalComercialPage`.
- `POST /precotizaciones` (crear en `BORRADOR`) — `PortalComercialPage`.
- `GET /empresas`, `POST /empresas` — `EmpresasPage`, selectores de empresa.
- `GET /empleados`, import Excel y CRUD — `EmpresasPage`.
- `GET /portal-cliente/sillas`, `GET /portal-cliente/precotizaciones` —
  `PortalClientePage`.

### 6. `GET /auth/me` sin usar
Es mío y existe. Hoy el cliente rehidrata la sesión desde el token guardado, sin
llamarlo. Útil si más adelante se quiere revalidar el usuario al refrescar la
página. Mantenerlo o retirarlo es decisión de diseño, no está roto.

## Cómo apagar un mock

En `src/api/mocks.js`, poner en `false` la bandera del recurso cuando su endpoint
real exista y esté alineado con el contrato de arriba. No hace falta tocar las
pantallas.
