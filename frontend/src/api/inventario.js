/* API de inventario de sillas y su exportación (RF-11, recurso del backend).
 *
 * El backend (router `/inventario`) acota el alcance por rol a partir del
 * usuario autenticado: el comercial ve todas las empresas y el admin cliente
 * solo la suya (R5). El frontend no decide el alcance; solo consume lo que el
 * backend devuelve. Por eso ambas llamadas van por `apiClient` con el JWT.
 *
 * Mismo patrón de mock conmutable que el resto: con `USE_MOCK.inventario` en
 * `true` trabaja con datos simulados (sin tocar la red); en `false` pega al
 * backend real. Al llegar/estar listo el endpoint basta con poner su bandera en
 * `false`, sin cambiar las pantallas.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

// Formatos de exportación admitidos por el backend (Literal["csv", "xlsx"]).
export const FORMATOS_EXPORTACION = ['csv', 'xlsx']

// Inventario simulado para el modo mock: una lista no vacía con la forma de
// `InventarioItemOut` (silla unida a empresa/sede/departamento/empleado).
const inventarioMock = [
  {
    id_silla: 1,
    empresa: 'Empresa Demo S.A.',
    sede: 'Sede Principal',
    departamento: 'Administración',
    empleado: 'Ana Pérez',
    cargo: 'Analista',
    codigo_qr: 'SIC-00000001',
    estado: 'REGISTRADA',
  },
  {
    id_silla: 2,
    empresa: 'Empresa Demo S.A.',
    sede: 'Sede Principal',
    departamento: 'Ventas',
    empleado: 'Luis Gómez',
    cargo: 'Ejecutivo',
    codigo_qr: 'SIC-00000002',
    estado: 'REGISTRADA',
  },
]

/* Lista el inventario dentro del alcance del rol (GET /inventario/).
 *
 * Devuelve la lista de ítems; el backend responde 200 con lista vacía cuando no
 * hay sillas en el alcance. */
export async function listInventario() {
  if (USE_MOCK.inventario) {
    return [...inventarioMock]
  }
  const { data } = await apiClient.get('/inventario/')
  return data
}

/* Exporta el inventario como `csv` o `xlsx` (GET /inventario/exportar).
 *
 * Devuelve el `Blob` del archivo; la pantalla decide cómo bajarlo (con
 * `descargarBlob`). El backend responde 400 si el formato no está admitido;
 * ese y cualquier otro error HTTP se propagan tal cual para que la pantalla los
 * mapee a un mensaje legible. */
export async function exportarInventario(formato) {
  if (USE_MOCK.inventario) {
    if (!FORMATOS_EXPORTACION.includes(formato)) {
      // Imita el 400 (formato no admitido) del backend para cubrir esa rama
      // también en modo mock, sin tocar la red.
      throw { response: { status: 400 } }
    }
    const mediaType =
      formato === 'csv'
        ? 'text/csv'
        : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return new Blob([`inventario mock (${formato})`], { type: mediaType })
  }

  const { data } = await apiClient.get('/inventario/exportar', {
    params: { formato },
    responseType: 'blob',
  })
  return data
}
