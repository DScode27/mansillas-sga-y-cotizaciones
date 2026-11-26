/* API de precotizaciones (recurso de otro dev, mockeable).
 *
 * Mismo patrón que `visitas.js`/`sillas.js`: con `USE_MOCK.precotizaciones` en
 * `true` trabaja sobre un store en memoria; en `false` pega al backend real sin
 * tocar las pantallas. Cubre el portal comercial (R9, M5): el comercial ve las
 * sillas levantadas de una visita y crea precotizaciones en estado `BORRADOR`.
 *
 * Reglas del SQL que respetamos aquí:
 *   - El estado arranca en `BORRADOR` (DEFAULT de `precotizacion`). La
 *     aceptación (`ENVIADA`/`ACEPTADA`) queda fuera de mi alcance.
 *   - `creada_por` es el usuario comercial autenticado; `token` lo genera la BD.
 *
 * El listado acepta `id_visita` para pedir solo las precotizaciones de esa
 * visita; el aislamiento real por empresa lo impone el backend según el usuario
 * autenticado (R4), esto solo es el filtro de la pantalla.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

// Store en memoria para el mock. Se reinicia al recargar.
const precotizacionesMock = []
let proximoIdMock = 1

export async function listPrecotizaciones(idVisita) {
  if (USE_MOCK.precotizaciones) {
    if (idVisita == null || idVisita === '') {
      return [...precotizacionesMock]
    }
    return precotizacionesMock.filter((p) => p.id_visita === Number(idVisita))
  }
  const { data } = await apiClient.get('/precotizaciones', {
    params: idVisita ? { id_visita: idVisita } : undefined,
  })
  return data
}

export async function createPrecotizacion({
  id_empresa,
  id_visita,
  creada_por,
  observaciones,
}) {
  const payload = {
    id_empresa: Number(id_empresa),
    id_visita: Number(id_visita),
    creada_por: Number(creada_por),
    observaciones: observaciones?.trim() || null,
  }

  if (USE_MOCK.precotizaciones) {
    const precotizacion = {
      id_precotizacion: proximoIdMock++,
      // El estado arranca en BORRADOR (DEFAULT del SQL); el token lo da la BD.
      estado: 'BORRADOR',
      token: `mock-token-${proximoIdMock}`,
      correo_cliente: null,
      fecha_envio: null,
      fecha_aceptacion: null,
      fecha_creacion: new Date().toISOString(),
      ...payload,
    }
    precotizacionesMock.push(precotizacion)
    return precotizacion
  }

  const { data } = await apiClient.post('/precotizaciones', payload)
  return data
}

/* Lista los accesos registrados al enlace público de una precotización
 * (GET /precotizaciones/{id_precotizacion}/accesos).
 *
 * El backend devuelve la lista de accesos (fecha, navegador, sistema operativo)
 * o, cuando no hay ninguno, un objeto `{ mensaje: 'Sin accesos registrados' }`.
 * Aquí se normaliza siempre a un arreglo para que la pantalla no distinga los
 * dos formatos: lista vacía == sin accesos. Solo el comercial lo consulta, así
 * que va autenticado por `apiClient`. */
export async function listAccesos(idPrecotizacion) {
  if (USE_MOCK.precotizaciones) {
    return []
  }
  const { data } = await apiClient.get(
    `/precotizaciones/${idPrecotizacion}/accesos`,
  )
  return Array.isArray(data) ? data : []
}
