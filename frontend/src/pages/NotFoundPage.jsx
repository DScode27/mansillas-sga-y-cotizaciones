/* Página 404 (tarea 1). */
import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <section className="card">
      <h1>404</h1>
      <p>La página que buscas no existe.</p>
      <Link to="/">Volver al inicio</Link>
    </section>
  )
}
