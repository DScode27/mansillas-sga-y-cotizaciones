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

/* Registra un departamento en una sede (`POST /sedes/{idSede}/departamentos`).
 *
 * La sede va en la ruta y el backend deriva de ella la empresa: el usuario
 * elige empresa y sede de desplegables encadenados y no digita ningún ID. Solo
 * se envía `nombre` (obligatorio). El backend impone el RBAC (comercial
 * cualquier empresa; ADMIN_CLIENTE solo la suya) y responde 404 (sede
 * inexistente) o 409 (nombre duplicado en la sede); los errores se propagan
 * tal cual para que la pantalla los mapee.
 *
 * Devuelve { id_departamento, id_empresa, id_sede, nombre } (DepartamentoOut). */
export async function createDepartamento(idSede, { nombre }) {
  const { data } = await apiClient.post(`/sedes/${idSede}/departamentos`, {
    nombre: nombre.trim(),
  })
  return data
}
