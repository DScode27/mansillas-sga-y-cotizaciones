/* Conmutación de mocks por recurso.
 *
 * Los endpoints de seguridad (auth, usuarios, RBAC) son míos y existen, así que
 * nunca se mockean: el frontend los consume directo contra mi backend FastAPI.
 *
 * El resto de recursos (empresas, empleados, visitas, sillas, precotizaciones,
 * QR público, portal cliente) los exponen otros devs y aún no existen. Mientras
 * tanto, cada recurso tiene su propia bandera aquí: en `true` usa datos
 * simulados, en `false` pega al endpoint real. Al llegar el endpoint real basta
 * con poner su bandera en `false`, sin tocar las pantallas.
 */
export const USE_MOCK = {
  // Estos recursos NO tienen endpoint todavía en el backend (los exponen otros
  // devs). Mientras no existan su CRUD, siguen en mock: pasarlos a `false`
  // haría fallar las pantallas con 404/Network Error.
  //   - portalCliente: router real `/portal-cliente/*` (GET sillas y
  //     precotizaciones, acotado a la empresa del ADMIN_CLIENTE autenticado).
  portalCliente: false,

  // Estos SÍ tienen endpoint real en el backend; consumen directo.
  //   - empresas: router `/empresas` real (GET/POST) tras el módulo de
  //     catálogo organizacional.
  //   - empleados: ruta anidada real `/empresas/{id}/empleados` (GET listado,
  //     POST alta manual) más la importación por Excel
  //     (`POST /carga-masiva/empleados`). Todo persiste en la base.
  empleados: false,
  empresas: false,
  visitas: false,
  sillas: false,
  precotizaciones: false,
  qrPublico: false,
  qrPdf: false,
  inventario: false,
  permisosQr: false,
  propuesta: false,
}
