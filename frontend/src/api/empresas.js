/* API de empresas (recurso de otro dev, mockeable).
 *
 * Plantilla del patrón de mock conmutable: mientras `USE_MOCK.empresas` sea
 * `true`, devuelve datos simulados; al poner la bandera en `false` pega al
 * endpoint real sin cambiar las pantallas que lo consumen. Los demás recursos
 * de otros devs (empleados, visitas, sillas, etc.) seguirán este mismo molde en
 * su propia tarea.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

const EMPRESAS_MOCK = [
  { id_empresa: 1, nombre: 'Empresa Demo S.A.', nit: '900123456-7' },
]

export async function listEmpresas() {
  if (USE_MOCK.empresas) {
    return EMPRESAS_MOCK
  }
  const { data } = await apiClient.get('/empresas')
  return data
}
