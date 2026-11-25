/* Página de login (tarea 3, R1).
 *
 * Formulario real contra POST /auth/login (consumo directo de mi backend, sin
 * mock). En éxito guarda la sesión vía AuthContext y vuelve a la ruta pedida
 * (o a Inicio). En 401 muestra un mensaje único, sin revelar si falló el correo
 * o la contraseña. Maneja estados de carga y error. El logo va sobre blanco.
 */
import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import logoMansillas from '../assets/logoMansillas.jpg'
import { useAuth } from '../context/auth-context'

export default function LoginPage() {
  const { isAuthenticated, signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [correo, setCorreo] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Si ya hay sesión, no mostramos el login.
  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  const destino = location.state?.from?.pathname ?? '/'

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      await signIn(correo.trim(), password)
      navigate(destino, { replace: true })
    } catch (err) {
      // 401 → credenciales inválidas (mensaje único). Otros → fallo genérico.
      if (err.response?.status === 401) {
        setError('Correo o contraseña incorrectos.')
      } else {
        setError('No se pudo iniciar sesión. Inténtalo de nuevo.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-screen">
      <section className="card login-card">
        <div className="login-brand">
          <img
            className="login-brand__logo"
            src={logoMansillas}
            alt="Mansillas"
          />
          <h1 className="login-brand__title">MansillasSIC</h1>
          <p className="login-brand__subtitle">
            Sistema de Inventario y Cotizaciones
          </p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label className="form-field">
            <span className="form-field__label">Correo</span>
            <input
              className="form-field__input"
              type="email"
              name="correo"
              autoComplete="username"
              value={correo}
              onChange={(e) => setCorreo(e.target.value)}
              required
              disabled={loading}
            />
          </label>

          <label className="form-field">
            <span className="form-field__label">Contraseña</span>
            <input
              className="form-field__input"
              type="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={loading}
            />
          </label>

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button className="btn login-form__submit" type="submit" disabled={loading}>
            {loading ? 'Entrando…' : 'Iniciar sesión'}
          </button>
        </form>
      </section>
    </div>
  )
}
