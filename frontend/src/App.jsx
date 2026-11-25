/* Rutas de la aplicación (tarea 1).
 *
 * Rutas base, en su mayoría placeholders. La protección por sesión/rol
 * (RequireRole) se añade en las tareas 3 y 5; la vista pública por QR y el
 * portal cliente llegan en tareas posteriores. El login vive fuera del layout
 * con sidebar.
 */
import { Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import HomePage from './pages/HomePage'
import LoginPage from './pages/LoginPage'
import NotFoundPage from './pages/NotFoundPage'
import PlaceholderPage from './pages/PlaceholderPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<AppLayout />}>
        <Route index element={<HomePage />} />
        <Route path="usuarios" element={<PlaceholderPage title="Usuarios" />} />
        <Route path="empresas" element={<PlaceholderPage title="Empresas" />} />
        <Route path="visitas" element={<PlaceholderPage title="Visitas" />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
