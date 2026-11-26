/* Página 404 (tarea 1).
 *
 * Es la ruta catch-all (`*`), que vive fuera del layout con sidebar. Por eso
 * usa el mismo marco centrado a pantalla completa que el login y la vista QR,
 * para no quedar pegada a la esquina del viewport. */
import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="login-screen">
      <section className="card login-card">
        <h1>404</h1>
        <p>La página que buscas no existe.</p>
        <Link to="/">Volver al inicio</Link>
      </section>
    </div>
  )
}
