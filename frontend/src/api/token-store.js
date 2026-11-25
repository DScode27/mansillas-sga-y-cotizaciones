/* Almacén de la sesión (JWT + usuario).
 *
 * Fuente única de verdad de la sesión: la persiste en localStorage (sobrevive
 * recargas) y la expone de forma síncrona para el interceptor HTTP. Se mantiene
 * fuera de React para que `client.js` pueda leer el token sin depender del
 * contexto y así evitar imports circulares (client ↔ AuthContext).
 */
const TOKEN_KEY = 'mansillas.token'
const USER_KEY = 'mansillas.user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getStoredUser() {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) {
    return null
  }
  try {
    return JSON.parse(raw)
  } catch {
    // Dato corrupto: lo descartamos para no romper el arranque.
    localStorage.removeItem(USER_KEY)
    return null
  }
}

export function saveSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
