/* API de listado de sedes por empresa (Fase 4, R9/RF-01-03-06).
 *
 * Consumo directo del backend real (sin mock): el endpoint
 * `GET /empresas/{id_empresa}/sedes` existe tras la tarea 9. El interceptor de
 * `apiClient` adjunta el JWT; el backend impone el RBAC y el aislamiento por
 * empresa (los roles internos ven cualquier empresa; el ADMIN_CLIENTE solo la
 * suya). Los errores HTTP se propagan tal cual para que la pantalla los mapee
 * y, si falla, degrade a input de ID.
 */
import { apiClient } from './client'

/* Lista las sedes de una empresa.
 *
 * Devuelve [{ id_sede, id_empresa, nombre, direccion, ciudad }] (SedeOut). Una
 * empresa sin sedes devuelve lista vacía. */
export async function listSedes(idEmpresa) {
  const { data } = await apiClient.get(`/empresas/${idEmpresa}/sedes`)
  return data
}
