/* Layout base: cabecera + navegación lateral + área de contenido.
 *
 * La navegación es un placeholder; en la tarea 5 (RBAC) se ocultan/muestran
 * las opciones según el rol del usuario. El logo es un marcador hasta la
 * identidad visual real (tarea 13, HU-27).
 */
import { NavLink, Outlet } from 'react-router-dom'
import logoMansillas from '../assets/logoMansillas.jpg'

const NAV_ITEMS = [
  { to: '/', label: 'Inicio', end: true },
  { to: '/usuarios', label: 'Usuarios' },
  { to: '/empresas', label: 'Empresas' },
  { to: '/visitas', label: 'Visitas' },
]

function navLinkClass({ isActive }) {
  return isActive ? 'app-nav__link is-active' : 'app-nav__link'
}

export default function AppLayout() {
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
          {NAV_ITEMS.map((item) => (
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
      </header>

      <main className="app-main">
        <div className="app-content">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
