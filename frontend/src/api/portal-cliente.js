/* API del portal cliente (recurso de otro dev, mockeable).
 *
 * Portal de solo lectura para el ADMIN_CLIENTE (M7, R11): consulta las sillas
 * levantadas y las precotizaciones de SU empresa. Mismo patrón de mock
 * conmutable que el resto: con `USE_MOCK.portalCliente` en `true` trabaja sobre
 * un store en memoria; en `false` pega al backend real sin tocar la pantalla.
 *
 * Aislamiento por empresa (R4): el cliente solo ve lo suyo. En el backend real
 * ese aislamiento lo impone el servidor según el usuario autenticado; aquí se
 * pasa `id_empresa` como filtro de la vista y, en modo mock, se filtra el store
 * por esa empresa para reproducir el mismo comportamiento.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

/* Datos de demostración para el mock, atados a una empresa (id_empresa). El
 * cliente de prueba (ADMIN_CLIENTE) debe tener el mismo id_empresa para verlos;
 * una empresa distinta devuelve listas vacías, que es justo el aislamiento. */
const sillasMock = [
  {
    id_silla: 1,
    id_empresa: 1,
    codigo_qr: 'SIC-00000001',
    cargo: 'Analista contable',
    sede: 'Sede principal',
    estado: 'REGISTRADA',
    sugerir_cambio: false,
    componentes: [
      { nombre: 'Cilindros', estado: 'BUENO' },
      { nombre: 'Ruedas', estado: 'MANTENIMIENTO' },
      { nombre: 'Bases', estado: 'BUENO' },
      { nombre: 'Asiento / Espaldar', estado: 'BUENO' },
      { nombre: 'Malla', estado: 'BUENO' },
    ],
  },
  {
    id_silla: 2,
    id_empresa: 1,
    codigo_qr: 'SIC-00000002',
    cargo: 'Recepción',
    sede: 'Sede principal',
    estado: 'REGISTRADA',
    sugerir_cambio: true,
    componentes: [
      { nombre: 'Cilindros', estado: 'DANADO' },
      { nombre: 'Ruedas', estado: 'DANADO' },
      { nombre: 'Bases', estado: 'DANADO' },
      { nombre: 'Asiento / Espaldar', estado: 'DANADO' },
      { nombre: 'Malla', estado: 'MANTENIMIENTO' },
    ],
  },
]

const precotizacionesMock = [
  {
    id_precotizacion: 1,
    id_empresa: 1,
    estado: 'BORRADOR',
    fecha_creacion: '2025-01-20T10:30:00',
    observaciones: 'Propuesta inicial tras el levantamiento.',
  },
]

function soloDeEmpresa(coleccion, idEmpresa) {
  // Sin empresa no se devuelve nada: un ADMIN_CLIENTE siempre tiene empresa, así
  // que no tenerla significa que no hay a qué aislar y no debe ver datos ajenos.
  if (idEmpresa == null || idEmpresa === '') return []
  return coleccion.filter((item) => item.id_empresa === Number(idEmpresa))
}

export async function listMisSillas(idEmpresa) {
  if (USE_MOCK.portalCliente) {
    return soloDeEmpresa(sillasMock, idEmpresa)
  }
  // El backend deduce la empresa del usuario autenticado; el filtro va igual por
  // claridad, pero el aislamiento real lo garantiza el servidor.
  const { data } = await apiClient.get('/portal-cliente/sillas')
  return data
}

export async function listMisPrecotizaciones(idEmpresa) {
  if (USE_MOCK.portalCliente) {
    return soloDeEmpresa(precotizacionesMock, idEmpresa)
  }
  const { data } = await apiClient.get('/portal-cliente/precotizaciones')
  return data
}
