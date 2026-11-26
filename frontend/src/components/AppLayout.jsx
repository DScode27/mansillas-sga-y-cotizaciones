/* Layout base: cabecera + navegación lateral + área de contenido.
 *
 * La navegación oculta las opciones no permitidas por rol (R3, RBAC en la UI):
 * cada entrada declara los roles que pueden verla y se filtra con `hasRole`.
 * La cabecera muestra el usuario y su rol y ofrece el botón de cerrar sesión.
 * El logo va SIEMPRE sobre fondo blanco (HU-27).
 */
import { useCallback } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import logoMansillas from '../assets/logoMansillas.jpg'
import { ROLES } from '../auth/roles'
import { useInactivityLogout } from '../auth/useInactivityLogout'
import { useAuth } from '../context/auth-context'

const NAV_ITEMS = [
  { to: '/', label: 'Inicio', end: true, roles: [] },
  { to: '/usuarios', label: 'Usuarios', roles: [ROLES.COMERCIAL_MANSILLAS] },
  { to: '/empresas', label: 'Empresas', roles: [ROLES.COMERCIAL_MANSILLAS] },
  {
    to: '/visitas',
    label: 'Visitas',
    roles: [ROLES.COMERCIAL_MANSILLAS, ROLES.TECNICO, ROLES.ADMIN_CLIENTE],
  },
  {
    to: '/levantamiento',
    label: 'Levantamiento',
    roles: [ROLES.TECNICO, ROLES.COMERCIAL_MANSILLAS],
  },
  {
    to: '/comercial',
    label: 'Portal comercial',
    roles: [ROLES.COMERCIAL_MANSILLAS],
  },
  {
    to: '/cliente',
    label: 'Portal cliente',
    roles: [ROLES.ADMIN_CLIENTE],
  },
]

function navLinkClass({ isActive }) {
  return isActive ? 'app-nav__link is-active' : 'app-nav__link'
}

export default function AppLayout() {
  const { user, isAuthenticated, hasRole, signOut } = useAuth()
  const navigate = useNavigate()

  const visibleItems = NAV_ITEMS.filter((item) => hasRole(item.roles))

  function handleLogout() {
    signOut()
    navigate('/login', { replace: true })
  }

  // Cierre de sesión por inactividad (HU-25). Al expirar, avisamos en /login.
  const handleInactivity = useCallback(() => {
    signOut()
    navigate('/login', {
      replace: true,
      state: { reason: 'inactividad' },
    })
  }, [signOut, navigate])

  useInactivityLogout(isAuthenticated, handleInactivity)

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-sidebar__brand">
          <img
            className="app-sidebar__logo"
            src={logoMansillas}
            alt="Mansillas"
          />
          <span>MansillasSIC</span>
        </div>
        <nav className="app-nav">
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={navLinkClass}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <header className="app-header">
        <span className="app-header__title">
          Sistema de Inventario y Cotizaciones
        </span>
        {user && (
          <div className="app-header__user">
            <span className="app-header__user-info">
              <span className="app-header__user-name">{user.nombre}</span>
              <span className="app-header__user-role">{user.rol}</span>
            </span>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={handleLogout}
            >
              Cerrar sesión
            </button>
          </div>
        )}
      </header>

      <main className="app-main">
        <div className="app-content">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
