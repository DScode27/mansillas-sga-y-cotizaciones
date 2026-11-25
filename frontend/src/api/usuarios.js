/* API de gestión de usuarios (recurso propio, sin mock).
 *
 * Consume directo mi backend FastAPI (router /usuarios), que existe y solo
 * acepta a COMERCIAL_MANSILLAS (HU-20). El interceptor del cliente adjunta el
 * JWT; el backend impone el RBAC (403 si el rol no corresponde).
 */
import { apiClient } from './client'

export async function listUsuarios() {
  const { data } = await apiClient.get('/usuarios')
  return data // [{ id_usuario, nombre, correo, rol, id_empresa, activo }]
}

export async function createUsuario({ nombre, correo, password, rol, id_empresa }) {
  const { data } = await apiClient.post('/usuarios', {
    nombre,
    correo,
    password,
    rol,
    // El backend exige id_empresa para roles de cliente y lo quiere nulo para
    // internos; enviamos null cuando no aplica.
    id_empresa: id_empresa ?? null,
  })
  return data
}

export async function asignarRol(idUsuario, { rol, id_empresa }) {
  const { data } = await apiClient.put(`/usuarios/${idUsuario}/rol`, {
    rol,
    id_empresa: id_empresa ?? null,
  })
  return data
}
