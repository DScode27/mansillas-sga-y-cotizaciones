/* Cliente HTTP compartido (axios).
 *
 * Apunta al backend FastAPI de seguridad (login/logout/usuarios/RBAC), que es
 * propio y existe. Dos interceptores:
 *   - Request: adjunta el JWT como `Authorization: Bearer <token>` cuando hay
 *     sesión, para que toda petición autenticada viaje con el token.
 *   - Response: ante un 401 (token ausente/expirado/revocado) limpia la sesión
 *     y redirige a /login. No redirige si el 401 vino del propio /auth/login
 *     (ahí el 401 son credenciales malas y lo maneja la pantalla de login).
 */
import axios from 'axios'
import { clearSession, getToken } from './token-store'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export const apiClient = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const url = error.config?.url ?? ''
    const isLoginRequest = url.includes('/auth/login')

    if (status === 401 && !isLoginRequest) {
      clearSession()
      // Redirección dura: el cliente vive fuera de React Router, así que no
      // tiene acceso a `navigate`. Evita el bucle si ya estamos en /login.
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }

    return Promise.reject(error)
  },
)
