/* Cliente HTTP compartido (axios).
 *
 * Apunta al backend FastAPI de seguridad (login/logout/usuarios/RBAC), que es
 * propio y existe. El interceptor que adjunta el JWT y redirige a login en 401
 * se añade en la tarea 3 (autenticación en el frontend); aquí solo queda la
 * instancia base con la URL configurable por variable de entorno de Vite.
 */
import axios from 'axios'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export const apiClient = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
})
