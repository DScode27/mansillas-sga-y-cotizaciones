/* API del nivel de permiso QR por empresa (RF-18, HU-18).
 *
 * ÚNICA acción de ESCRITURA del ADMIN_CLIENTE en el MVP: su portal es, por lo
 * demás, de solo lectura (consulta de sillas y precotizaciones). Aquí configura
 * con qué nivel acceden sus empleados por QR, es decir, si pueden enviar tickets.
 *
 * Las dos llamadas van por `apiClient` con el JWT, contra el router `/qr` del
 * backend (que ya existe):
 *   - getPermisoQr(idEmpresa) → GET  /qr/empresas/{id}/permiso-qr
 *   - setPermisoQr(idEmpresa, permisoQr) → PUT /qr/empresas/{id}/permiso-qr
 *     con body { permiso_qr }.
 *
 * Aislamiento multiempresa (R5): el ADMIN_CLIENTE solo opera sobre su propia
 * empresa; ese aislamiento lo impone el backend según el usuario autenticado
 * (403 si la empresa objetivo no es la suya). La pantalla usa `user.id_empresa`.
 *
 * Mismo patrón de mock conmutable que el resto: con `USE_MOCK.permisosQr` en
 * `true` trabaja sobre un store en memoria (get devuelve el nivel guardado; set
 * persiste y rechaza valores ≠ {1,2,3} simulando el 422 del backend); en `false`
 * pega al backend real sin tocar la pantalla.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

// Niveles válidos de permiso QR (el backend valida Literal 1/2/3 → 422 si no).
export const NIVELES_PERMISO_QR = [1, 2, 3]

// Store en memoria para el mock: nivel por empresa. Se reinicia al recargar.
// Sin entrada previa, una empresa arranca en 1 (a: solo consulta), el nivel más
// restrictivo, coherente con el DEFAULT del backend.
const nivelesMock = new Map()
const NIVEL_POR_DEFECTO = 1

/* Lee el nivel de permiso QR de una empresa (GET /qr/empresas/{id}/permiso-qr).
 *
 * Devuelve el entero del nivel (1/2/3). Los errores HTTP se propagan tal cual
 * (403 si la empresa no es la del usuario) para que la pantalla los mapee. */
export async function getPermisoQr(idEmpresa) {
  if (USE_MOCK.permisosQr) {
    const clave = Number(idEmpresa)
    return nivelesMock.get(clave) ?? NIVEL_POR_DEFECTO
  }
  const { data } = await apiClient.get(`/qr/empresas/${idEmpresa}/permiso-qr`)
  return data.permiso_qr
}

/* Guarda el nivel de permiso QR de una empresa (PUT /qr/empresas/{id}/permiso-qr).
 *
 * Devuelve el entero del nivel ya guardado. Un valor fuera de {1,2,3} es
 * inválido (el backend responde 422 "permiso_qr debe ser 1, 2 o 3"); en modo
 * mock se reproduce ese 422 sin tocar la red. El resto de errores HTTP (p. ej.
 * 403) se propagan tal cual para que la pantalla los mapee. */
export async function setPermisoQr(idEmpresa, permisoQr) {
  const nivel = Number(permisoQr)

  if (USE_MOCK.permisosQr) {
    if (!NIVELES_PERMISO_QR.includes(nivel)) {
      // Imita el 422 (valor fuera de 1/2/3) del backend para cubrir esa rama
      // también en modo mock, sin tocar la red.
      const error = new Error('permiso_qr debe ser 1, 2 o 3')
      error.response = {
        status: 422,
        data: { detail: 'permiso_qr debe ser 1, 2 o 3' },
      }
      throw error
    }
    nivelesMock.set(Number(idEmpresa), nivel)
    return nivel
  }

  const { data } = await apiClient.put(
    `/qr/empresas/${idEmpresa}/permiso-qr`,
    { permiso_qr: nivel },
  )
  return data.permiso_qr
}
