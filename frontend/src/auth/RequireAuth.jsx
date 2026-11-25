/* Guard de sesión: protege rutas que requieren estar autenticado.
 *
 * Si no hay sesión, redirige a /login recordando la ruta pedida (`state.from`)
 * para volver a ella tras iniciar sesión. Envuelve rutas con <Outlet/>.
 */
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function RequireAuth() {
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}
