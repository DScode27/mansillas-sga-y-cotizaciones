/* Redirección de la ruta raíz (`/`) al portal principal de cada rol.
 *
 * Ya no hay pestaña "Inicio" en la navegación; tras iniciar sesión, cada rol
 * aterriza directamente en la pantalla que le corresponde en vez de una página
 * de bienvenida vacía. Si el rol no tiene un destino claro, cae a Visitas (la
 * ruta más común) y, en último caso, muestra un aviso mínimo.
 */
import { Navigate } from 'react-router-dom'
import { ROLES } from '../auth/roles'
import { useAuth } from '../context/auth-context'

const DESTINO_POR_ROL = {
  [ROLES.COMERCIAL_MANSILLAS]: '/comercial',
  [ROLES.TECNICO]: '/levantamiento',
  [ROLES.ADMIN_CLIENTE]: '/cliente',
}

export default function HomeRedirect() {
  const { user } = useAuth()
  const destino = DESTINO_POR_ROL[user?.rol] ?? '/visitas'
  return <Navigate to={destino} replace />
}
