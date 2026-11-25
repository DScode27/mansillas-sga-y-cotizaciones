/* Guard de rol (RBAC en el frontend, R3): protege rutas por rol.
 *
 * Supone sesión ya validada (se anida bajo RequireAuth). Si el rol del usuario
 * no está entre los permitidos, muestra un aviso de acceso denegado en vez de
 * la página. Es el espejo en UI del 403 del backend; la autorización real la
 * impone el servidor.
 *
 * Uso:
 *   <Route element={<RequireRole roles={[ROLES.COMERCIAL_MANSILLAS]} />}>
 *     <Route path="usuarios" element={<UsuariosPage />} />
 *   </Route>
 */
import { Outlet } from 'react-router-dom'
import { useAuth } from '../context/auth-context'

export default function RequireRole({ roles }) {
  const { hasRole } = useAuth()

  if (!hasRole(roles)) {
    return (
      <section className="card">
        <h1>Acceso denegado</h1>
        <p className="form-error">
          Tu rol no tiene permiso para ver esta sección.
        </p>
      </section>
    )
  }

  return <Outlet />
}
