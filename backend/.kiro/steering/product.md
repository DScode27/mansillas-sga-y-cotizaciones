---
inclusion: always
---

# Producto — Mansillas SGA y Cotizaciones (backend)

## Propósito
Backend del SIC de Mansillas: levantamiento de inventario de sillas en sitio,
identificación por QR, precotización y cotización. El objetivo de esta etapa es
un MVP funcional que cumpla los criterios de aceptación, no un rediseño del
sistema. Reutilizar lo existente y elegir la solución más simple que satisfaga
el requisito.

## Usuarios y roles
Roles definidos en el `CHECK` de `usuario.rol` (ver `database/SQLMansillasSIC.sql`):

- `COMERCIAL_MANSILLAS` — interno; agenda visitas, gestiona precotizaciones.
- `TECNICO` — interno; registra sillas dentro de sus visitas asignadas.
- `ADMIN_CLIENTE` — externo; atado a una empresa (`id_empresa`).
- `EMPLEADO_CLIENTE` — externo; puede identificarse en el flujo QR mediante OTP.

Los internos tienen `id_empresa` NULL; los externos están ligados a su empresa.

## Historias a cargo (backend, María Fernanda)
- HU-02: registro de sillas adicionales respecto a `cantidad_estimada`.
- HU-10: registro y consulta de múltiples fotografías por silla.
- HU-12: edición y validación del levantamiento antes de precotizar.
- HU-13: enlace único de la propuesta y envío al cliente.
- HU-15: aceptación de la precotización con validación de identidad y OTP.
- HU-16: habilitación de la cotización solo tras aceptar la precotización.

No ampliar el alcance de estas historias sin autorización.

## Reglas de negocio establecidas
Fuente: sección "REGLAS QUE DEBE APLICAR EL BACKEND" de
`database/SQLMansillasSIC.sql` y las especificaciones de Davidson
(`.kiro/specs/mansillas-backend/`).

- Las sillas **no** se limitan por `cantidad_estimada`; el estimado se preserva
  sin reescribir (RN-04). La cantidad real se obtiene contando las registradas.
- Al crear una silla se envía `codigo_qr` vacío/NULL; el trigger `generar_codigo_qr`
  asigna el consecutivo `SIC-00000001`. El código es permanente, nunca se reasigna.
- `token_publico` (UUID) referencia la silla en URLs públicas; el QR porta
  token/URL, **nunca** datos personales. La vista pública muestra solo datos básicos.
- Precotización: arranca en `BORRADOR`; una vez `ACEPTADA` es inmutable
  (trigger `impedir_edicion_precotizacion_aceptada`).
- Aceptación (HU-15): validar OTP (hash, correo y expiración), marcar
  `codigo_verificacion.utilizado=TRUE` e insertar la aceptación en una **misma
  transacción**. La BD pasa el estado a `ACEPTADA`
  (trigger `registrar_aceptacion_precotizacion`).
- Cotización (HU-16): la BD bloquea cotizar sin precotización `ACEPTADA`
  (trigger `validar_cotizacion_tras_aceptacion`). El backend captura la excepción
  y la traduce a HTTP.
- `empresa.permiso_qr`: 1 consulta; 2 consulta y tickets; 3 tickets solo por
  `ADMIN_CLIENTE`.

## Decisiones pendientes (coordinar con el equipo)
- HU-10: almacenamiento de fotos — se elegirá la **alternativa más sencilla y
  suficiente** para el MVP según el entorno de despliegue previsto (carpeta de
  archivos con almacenamiento persistente, o Supabase Storage si simplifica la
  persistencia/disponibilidad). Supabase Storage **no** es obligatorio. Se usa la
  tabla `fotografia` y su `ruta_archivo`; sin esquema nuevo, sin múltiples
  proveedores ni abstracciones para intercambiarlos. La decisión se justifica
  brevemente en el `design.md` de la spec.
- HU-10: si la ficha pública por QR muestra fotos — **no** exponerlas por QR
  salvo que los criterios de aceptación lo exijan.
- HU-02: contrato de consulta de cantidad real de sillas (`GET /sillas?id_visita=`
  vs. ampliar la respuesta de visita) — se decide en el diseño de la spec.
- Propiedad de `GET/POST /precotizaciones` (HU-13) y del estado de componentes
  (dependencia de HU-12, posible trabajo de Esteban) — confirmar para no duplicar.
- Proveedor de correo/OTP (HU-13/HU-15): no hay integración de correo en el código.

## Fuera de alcance del MVP
Sin sobreingeniería: no microservicios, no colas/mensajería, no cachés
distribuidas, no procesamiento asíncrono de imágenes ni miniaturas, no
abstracciones ni tecnologías no indispensables.
