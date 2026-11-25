/* Contexto de autenticación (esqueleto de la tarea 1).
 *
 * De momento solo expone el hook y un provider vacío para que el layout y las
 * rutas puedan leerlo sin romperse. La lógica real (guardar usuario/rol/token,
 * login, logout, 401) se implementa en la tarea 3.
 */
import { useMemo, useState } from 'react'
import { AuthContext } from './auth-context'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)

  const value = useMemo(
    () => ({
      user,
      setUser,
      isAuthenticated: Boolean(user),
    }),
    [user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
