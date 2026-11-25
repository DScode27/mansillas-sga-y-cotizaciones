/* API de generación de PDF de códigos QR (recurso de otro dev, mockeable).
 *
 * El backend arma un PDF con los QR de las sillas seleccionadas
 * (POST /qr/pdf, cuerpo { ids: [...] }) y lo devuelve como `application/pdf`.
 * Cada QR codifica la URL pública de la silla (su `token_publico`), nunca datos
 * personales. Lo consume un usuario autenticado (comercial o el técnico dueño
 * de la visita), así que va por `apiClient` con el JWT.
 *
 * Mismo patrón de mock conmutable que el resto: con `USE_MOCK.qrPdf` en `true`
 * no llama al backend (devuelve un blob trivial para no romper la descarga en
 * modo demo); en `false` pide el PDF real. Al llegar el endpoint real basta con
 * poner su bandera en `false`, sin tocar la pantalla.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

/* Descarga el PDF de QR de las sillas indicadas por sus ids.
 *
 * Devuelve el `Blob` del PDF; la pantalla decide si lo abre o lo baja. El
 * backend responde 400 si `ids` va vacío y 403/404 según permisos y existencia;
 * esos errores se propagan tal cual para que la pantalla los muestre. */
export async function descargarQrPdf(ids) {
  const idsNumericos = (ids ?? []).map(Number).filter((n) => Number.isInteger(n))
  if (idsNumericos.length === 0) {
    // Mismo 400 que impone el backend ("al menos una silla"), para cubrir esa
    // rama también sin llamar al servidor.
    throw { response: { status: 400 } }
  }

  if (USE_MOCK.qrPdf) {
    // Marcador de posición: un PDF vacío solo para que la descarga no falle en
    // modo demo. El contenido real lo produce el backend.
    return new Blob([`%PDF-1.4 mock (${idsNumericos.join(',')})`], {
      type: 'application/pdf',
    })
  }

  const { data } = await apiClient.post(
    '/qr/pdf',
    { ids: idsNumericos },
    { responseType: 'blob' },
  )
  return data
}
