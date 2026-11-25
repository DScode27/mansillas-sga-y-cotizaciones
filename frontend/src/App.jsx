/* Rutas de la aplicación.
 *
 * El login vive fuera del layout. Todo lo que cuelga de AppLayout está detrás
 * de RequireAuth (hay que tener sesión). Dentro, las rutas sensibles se acotan
 * por rol con RequireRole (RBAC en el frontend, R3): p. ej. "Usuarios" es solo
 * para COMERCIAL_MANSILLAS. La autorización real la impone el backend (403);
 * esto solo evita mostrar lo que no corresponde.
 */
import { Route, Routes } from 'react-router-dom'
import { ROLES } from './auth/roles'
import RequireAuth from './auth/RequireAuth'
import RequireRole from './auth/RequireRole'
import AppLayout from './components/AppLayout'
import HomePage from './pages/HomePage'
import LoginPage from './pages/LoginPage'
import EmpresasPage from './pages/EmpresasPage'
import NotFoundPage from './pages/NotFoundPage'
import PlaceholderPage from './pages/PlaceholderPage'
import UsuariosPage from './pages/UsuariosPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<HomePage />} />

          {/* Solo COMERCIAL_MANSILLAS gestiona usuarios (HU-20). */}
          <Route element={<RequireRole roles={[ROLES.COMERCIAL_MANSILLAS]} />}>
            <Route path="usuarios" element={<UsuariosPage />} />
          </Route>

          {/* Alta de empresa y empleados (M2): acción de comercial. El portal
              cliente de solo lectura (ADMIN_CLIENTE) llega en su propia tarea. */}
          <Route element={<RequireRole roles={[ROLES.COMERCIAL_MANSILLAS]} />}>
            <Route path="empresas" element={<EmpresasPage />} />
          </Route>

          <Route
            element={
              <RequireRole
                roles={[ROLES.COMERCIAL_MANSILLAS, ROLES.TECNICO, ROLES.ADMIN_CLIENTE]}
              />
            }
          >
            <Route path="visitas" element={<PlaceholderPage title="Visitas" />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
