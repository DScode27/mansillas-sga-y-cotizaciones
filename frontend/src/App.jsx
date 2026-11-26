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
import LevantamientoPage from './pages/LevantamientoPage'
import PortalComercialPage from './pages/PortalComercialPage'
import PortalClientePage from './pages/PortalClientePage'
import NotFoundPage from './pages/NotFoundPage'
import PropuestaPublicaPage from './pages/PropuestaPublicaPage'
import QrPublicoPage from './pages/QrPublicoPage'
import UsuariosPage from './pages/UsuariosPage'
import VisitasPage from './pages/VisitasPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* Vista pública por QR (M6, R10): sin login ni OTP. Va fuera de
          RequireAuth para que cualquiera que escanee el QR vea la ficha. */}
      <Route path="/qr/:token" element={<QrPublicoPage />} />

      {/* Página pública de aceptación de precotización (RF-15, HU-15): el
          cliente abre el enlace de su propuesta sin login y la acepta con un
          código enviado por correo. Fuera de RequireAuth y la ruta coincide con
          `settings.proposal_path` (`/propuesta`) del backend. */}
      <Route path="/propuesta/:token" element={<PropuestaPublicaPage />} />

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
            <Route path="visitas" element={<VisitasPage />} />
          </Route>

          {/* Levantamiento móvil (HU-28): trabajo en sitio del TECNICO; el
              COMERCIAL_MANSILLAS también puede entrar para seguimiento. */}
          <Route
            element={
              <RequireRole roles={[ROLES.TECNICO, ROLES.COMERCIAL_MANSILLAS]} />
            }
          >
            <Route path="levantamiento" element={<LevantamientoPage />} />
          </Route>

          {/* Portal comercial (M5): el COMERCIAL_MANSILLAS revisa las sillas
              levantadas y crea precotizaciones en borrador. */}
          <Route element={<RequireRole roles={[ROLES.COMERCIAL_MANSILLAS]} />}>
            <Route path="comercial" element={<PortalComercialPage />} />
          </Route>

          {/* Portal cliente (M7): el ADMIN_CLIENTE consulta en solo lectura las
              sillas y precotizaciones de su propia empresa (aislamiento, R4). */}
          <Route element={<RequireRole roles={[ROLES.ADMIN_CLIENTE]} />}>
            <Route path="cliente" element={<PortalClientePage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
