/* Objeto de contexto y hook de autenticación.
 *
 * Separado del provider para cumplir la regla de fast-refresh (un archivo con
 * componentes solo exporta componentes). El provider vive en AuthContext.jsx.
 */
import { createContext, useContext } from 'react'

export const AuthContext = createContext(null)

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (ctx === null) {
    throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  }
  return ctx
}
