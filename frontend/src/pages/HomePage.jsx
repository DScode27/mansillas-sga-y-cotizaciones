/* Página de inicio (página protegida de ejemplo, tarea 3).
 *
 * Solo visible con sesión (cuelga de RequireAuth). Muestra quién inició sesión
 * y su rol, para la demo de autenticación.
 */
import { useAuth } from '../context/auth-context'

export default function HomePage() {
  const { user } = useAuth()

  return (
    <section className="card">
      <h1>MansillasSIC</h1>
      <p>
        Sesión iniciada como <strong>{user?.nombre}</strong> (
        {user?.correo}) con rol <strong>{user?.rol}</strong>.
      </p>
      <p>
        Esta es una página protegida: solo se ve con sesión activa. La
        navegación lateral muestra únicamente las opciones permitidas por tu
        rol.
      </p>
    </section>
  )
}
