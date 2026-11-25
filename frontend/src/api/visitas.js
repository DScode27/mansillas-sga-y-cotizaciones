/* API de visitas (recurso de otro dev, mockeable).
 *
 * Mismo patrón que `empresas.js`/`empleados.js`: con `USE_MOCK.visitas` en
 * `true` trabaja sobre un store en memoria; en `false` pega al backend real sin
 * tocar las pantallas. Una visita se asocia a empresa, sede, comercial y
 * técnico (R7); el estado arranca en `PROGRAMADA` (como en el SQL) y el listado
 * se filtra por empresa.
 *
 * El listado acepta `id_empresa` para pedir solo las visitas de esa empresa; el
 * aislamiento real lo impone el backend según el usuario autenticado (R4), esto
 * solo es el filtro de la pantalla.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

// Store en memoria para el mock. Se reinicia al recargar.
const visitasMock = [
  {
    id_visita: 1,
    id_empresa: 1,
    id_sede: 1,
    id_comercial: 1,
    id_tecnico: 2,
    fecha_programada: '2025-01-15T09:00',
    cantidad_estimada: 10,
    estado: 'PROGRAMADA',
    observaciones: 'Visita inicial de levantamiento.',
  },
]
let proximoIdMock = 2

export async function listVisitas(idEmpresa) {
  if (USE_MOCK.visitas) {
    if (idEmpresa == null || idEmpresa === '') {
      return [...visitasMock]
    }
    return visitasMock.filter((v) => v.id_empresa === Number(idEmpresa))
  }
  const { data } = await apiClient.get('/visitas', {
    params: idEmpresa ? { id_empresa: idEmpresa } : undefined,
  })
  return data
}

export async function createVisita({
  id_empresa,
  id_sede,
  id_comercial,
  id_tecnico,
  fecha_programada,
  cantidad_estimada,
  observaciones,
}) {
  const payload = {
    id_empresa: Number(id_empresa),
    id_sede: Number(id_sede),
    id_comercial: Number(id_comercial),
    id_tecnico: Number(id_tecnico),
    // El input datetime-local da '' cuando está vacío; el campo es opcional.
    fecha_programada: fecha_programada || null,
    cantidad_estimada: Number(cantidad_estimada),
    observaciones: observaciones?.trim() || null,
  }

  if (USE_MOCK.visitas) {
    const visita = {
      id_visita: proximoIdMock++,
      estado: 'PROGRAMADA',
      ...payload,
    }
    visitasMock.push(visita)
    return visita
  }

  const { data } = await apiClient.post('/visitas', payload)
  return data
}

// Busca una visita en el store del mock; lanza un 404 imitado si no existe, para
// que la pantalla ejercite esa rama igual que contra el backend real.
function buscarVisitaMock(idVisita) {
  const visita = visitasMock.find((v) => v.id_visita === Number(idVisita))
  if (!visita) {
    throw { response: { status: 404 } }
  }
  return visita
}

/* Trae una visita por su id (GET /visitas/{id_visita}). */
export async function getVisita(idVisita) {
  if (USE_MOCK.visitas) {
    return { ...buscarVisitaMock(idVisita) }
  }
  const { data } = await apiClient.get(`/visitas/${idVisita}`)
  return data
}

/* Actualiza una visita (PUT /visitas/{id_visita}).
 *
 * Solo se envían los campos presentes en `cambios`. El backend ignora
 * `cantidad_estimada` (RN-04 conserva la estimación original), así que no se
 * incluye aquí. Campos editables: id_sede, id_tecnico, fecha_programada, estado,
 * observaciones. */
export async function updateVisita(idVisita, cambios) {
  const payload = {}
  if ('id_sede' in cambios) payload.id_sede = Number(cambios.id_sede)
  if ('id_tecnico' in cambios) payload.id_tecnico = Number(cambios.id_tecnico)
  if ('fecha_programada' in cambios) {
    payload.fecha_programada = cambios.fecha_programada || null
  }
  if ('estado' in cambios) payload.estado = cambios.estado
  if ('observaciones' in cambios) {
    payload.observaciones = cambios.observaciones?.trim() || null
  }

  if (USE_MOCK.visitas) {
    const visita = buscarVisitaMock(idVisita)
    Object.assign(visita, payload)
    return { ...visita }
  }
  const { data } = await apiClient.put(`/visitas/${idVisita}`, payload)
  return data
}

/* Elimina una visita (DELETE /visitas/{id_visita}).
 *
 * El backend responde 409 si la visita tiene sillas registradas; en mock se
 * imita ese conflicto para que la pantalla cubra esa rama. */
export async function deleteVisita(idVisita) {
  if (USE_MOCK.visitas) {
    const visita = buscarVisitaMock(idVisita)
    visitasMock.splice(visitasMock.indexOf(visita), 1)
    return
  }
  await apiClient.delete(`/visitas/${idVisita}`)
}
