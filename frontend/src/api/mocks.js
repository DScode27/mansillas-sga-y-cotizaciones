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
  empresas: true,
  empleados: true,
  visitas: true,
  sillas: true,
  precotizaciones: true,
  qrPublico: true,
  portalCliente: true,
}
