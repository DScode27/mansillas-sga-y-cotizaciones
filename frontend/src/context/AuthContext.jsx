/* Provider de autenticación (tarea 3).
 *
 * Guarda el usuario (con su rol) en estado de React y persiste sesión
 * (token + usuario) en el almacén de `src/api/`. Expone:
 *   - `user`           usuario autenticado o null.
 *   - `isAuthenticated`
 *   - `signIn(correo, password)`  llama al endpoint real /auth/login.
 *   - `signOut()`      limpia la sesión local.
 *   - `hasRole(roles)` helper para la navegación/guards por rol (R3).
 *
 * El hook `useAuth` y el objeto de contexto viven en `auth-context.js`
 * (separados para cumplir la regla de fast-refresh).
 */
import { useCallback, useMemo, useState } from 'react'
import { login as loginRequest } from '../api/auth'
import { clearSession, getStoredUser, saveSession } from '../api/token-store'
import { AuthContext } from './auth-context'

export function AuthProvider({ children }) {
  // Rehidrata la sesión al arrancar: si hay usuario guardado, seguimos dentro.
  const [user, setUser] = useState(getStoredUser)

  const signIn = useCallback(async (correo, password) => {
    const data = await loginRequest(correo, password)
    saveSession(data.access_token, data.usuario)
    setUser(data.usuario)
    return data.usuario
  }, [])

  const signOut = useCallback(() => {
    clearSession()
    setUser(null)
  }, [])

  const hasRole = useCallback(
    (roles) => {
      if (!user) {
        return false
      }
      if (!roles || roles.length === 0) {
        return true
      }
      return roles.includes(user.rol)
    },
    [user],
  )

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      signIn,
      signOut,
      hasRole,
    }),
    [user, signIn, signOut, hasRole],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
