/* API de listado de departamentos por sede (Fase 4, R9/RF-01-03-06).
 *
 * Consumo directo del backend real (sin mock): el endpoint
 * `GET /sedes/{id_sede}/departamentos` existe tras la tarea 9. Un departamento
 * cuelga de una sede (FK compuesta `(id_empresa, id_sede)`), por eso la lista se
 * pide por `id_sede`. El backend resuelve la empresa dueña de la sede, aplica el
 * aislamiento (404 si la sede no existe, 403 fuera de alcance) y el interceptor
 * de `apiClient` adjunta el JWT. Los errores HTTP se propagan tal cual para que
 * la pantalla los mapee y, si falla, degrade a input de ID.
 */
import { apiClient } from './client'

/* Lista los departamentos de una sede.
 *
 * Devuelve [{ id_departamento, id_empresa, id_sede, nombre }] (DepartamentoOut).
 * Una sede sin departamentos devuelve lista vacía. */
export async function listDepartamentos(idSede) {
  const { data } = await apiClient.get(`/sedes/${idSede}/departamentos`)
  return data
}
