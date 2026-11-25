/* API de autenticación (recurso propio, sin mock).
 *
 * Consume directo mi backend FastAPI. El login ya existe (HU-21); logout y el
 * manejo de sesión se completan en las tareas 3 y 4.
 */
import { apiClient } from './client'

export async function login(correo, password) {
  const { data } = await apiClient.post('/auth/login', { correo, password })
  return data // { access_token, token_type, usuario: { id_usuario, nombre, correo, rol, id_empresa } }
}

export async function logout() {
  // El interceptor adjunta el JWT; el backend revoca la sesión (marca
  // fecha_cierre) para que el token deje de valer.
  await apiClient.post('/auth/logout')
}
