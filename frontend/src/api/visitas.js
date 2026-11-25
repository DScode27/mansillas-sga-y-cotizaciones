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
