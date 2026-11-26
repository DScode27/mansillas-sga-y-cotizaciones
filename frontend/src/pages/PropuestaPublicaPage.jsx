/* Página pública de aceptación de precotización (RF-15, HU-15).
 *
 * Ruta pública (fuera de RequireAuth): el cliente abre el enlace de su
 * propuesta (`/propuesta/{token}`) sin login y la acepta con un código (OTP)
 * recibido por correo. Muestra empresa, fecha de envío y la lista de sillas; si
 * la propuesta está ENVIADA ofrece el flujo de dos pasos (solicitar código →
 * aceptar), y si ya está ACEPTADA muestra el estado final sin formulario.
 * Token inválido o propuesta no disponible → 404 ("propuesta no disponible").
 * Reutiliza la identidad visual del login/QR (logo sobre blanco, marco
 * centrado). El código NUNCA se muestra ni se registra: solo se envía al
 * backend para aceptar.
 */
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import logoMansillas from '../assets/logoMansillas.jpg'
import {
  getPropuesta,
  solicitarOtpPropuesta,
  aceptarPropuesta,
  PropuestaNoEncontrada,
} from '../api/propuesta'

// Insignia por estado de la silla (reutiliza las clases de theme/layout).
const ESTADO_SILLA_BADGE = {
  REGISTRADA: 'badge--ok',
  LEVANTADA: 'badge--ok',
  MANTENIMIENTO: 'badge--alerta',
  DANADA: 'badge--alerta',
}

// Formatea una fecha ISO a algo legible; ante un valor ausente/ inválido cae en
// un guion para no romper la vista.
function formatearFecha(iso) {
  if (!iso) return '—'
  const fecha = new Date(iso)
  if (Number.isNaN(fecha.getTime())) return '—'
  return fecha.toLocaleString('es-CO', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

// Mensaje legible por código HTTP al solicitar el código (paso 1, RF-15). El
// cuerpo crudo del backend nunca se muestra; un fallo de red (sin `response`)
// cae en el genérico.
function mensajeErrorOtp(status) {
  if (status === 429) {
    return 'Has solicitado demasiados códigos. Espera un momento e inténtalo de nuevo.'
  }
  if (status === 503) {
    return 'El servicio de verificación no está disponible por ahora. Inténtalo más tarde.'
  }
  if (status === 502) {
    return 'No fue posible enviar el código por correo. Inténtalo de nuevo en unos minutos.'
  }
  if (status === 404) return 'Esta propuesta ya no está disponible.'
  return 'No se pudo solicitar el código. Revisa tu conexión e inténtalo de nuevo.'
}

// Mensaje legible por código HTTP al aceptar la propuesta (paso 2, RF-15). El
// código nunca se muestra ni se registra; el 400 solo indica que no es válido o
// expiró, sin revelar el valor esperado.
function mensajeErrorAceptar(status) {
  if (status === 400) {
    return 'El código no es válido o ya expiró. Solicita uno nuevo e inténtalo otra vez.'
  }
  if (status === 409) {
    return 'Esta propuesta ya fue aceptada o no está disponible para aceptación.'
  }
  if (status === 422) {
    return 'Revisa tu nombre, cargo y código: alguno de los datos no es válido.'
  }
  if (status === 503) {
    return 'El servicio de verificación no está disponible por ahora. Inténtalo más tarde.'
  }
  return 'No se pudo aceptar la propuesta. Revisa tu conexión e inténtalo de nuevo.'
}

// Confirmación de aceptación (estado final). Se muestra tanto cuando la
// propuesta llega ya ACEPTADA como tras aceptarla en esta sesión; en ambos
// casos la UI queda bloqueada (sin formulario).
function BloqueAceptada({ fechaAceptacion }) {
  return (
    <section className="qr-publico__ticket">
      <h2>Propuesta aceptada</h2>
      <p className="form-success" role="status">
        Esta propuesta ya fue aceptada
        {fechaAceptacion ? ` el ${formatearFecha(fechaAceptacion)}` : ''}. No es
        necesario hacer nada más.
      </p>
    </section>
  )
}

// Flujo de aceptación en dos pasos para una propuesta ENVIADA (RF-15). Paso 1:
// solicitar el código (202 → "revisa tu correo"). Paso 2: nombre, cargo y
// código → aceptar (200 → confirmación y bloqueo de la UI). Vista anónima: el
// código solo se envía al backend, nunca se muestra ni se registra en claro.
function BloqueAceptacion({ token, onAceptada }) {
  // 'solicitar' (paso 1) | 'aceptar' (paso 2).
  const [paso, setPaso] = useState('solicitar')

  const [nombre, setNombre] = useState('')
  const [cargo, setCargo] = useState('')
  // `codigo` es el OTP recibido por correo; se mantiene en estado solo para
  // enviarlo y nunca se muestra fuera de su propio input.
  const [codigo, setCodigo] = useState('')

  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState('')

  async function handleSolicitarCodigo(event) {
    event.preventDefault()
    setError('')
    setEnviando(true)
    try {
      await solicitarOtpPropuesta(token)
      setPaso('aceptar')
    } catch (err) {
      setError(mensajeErrorOtp(err.response?.status))
    } finally {
      setEnviando(false)
    }
  }

  async function handleAceptar(event) {
    event.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const resultado = await aceptarPropuesta(token, {
        nombre_aceptante: nombre.trim(),
        cargo_aceptante: cargo.trim(),
        codigo: codigo.trim(),
      })
      onAceptada(resultado?.fecha_aceptacion ?? null)
    } catch (err) {
      setError(mensajeErrorAceptar(err.response?.status))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section className="qr-publico__ticket">
      <h2>Aceptar la propuesta</h2>

      {paso === 'solicitar' && (
        <form className="form-grid" onSubmit={handleSolicitarCodigo}>
          <p className="state-text qr-publico__ticket-ayuda">
            Para aceptar esta propuesta te enviaremos un código de verificación
            al correo registrado.
          </p>

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <div className="form-actions">
            <button className="btn" type="submit" disabled={enviando}>
              {enviando ? 'Solicitando…' : 'Solicitar código'}
            </button>
          </div>
        </form>
      )}

      {paso === 'aceptar' && (
        <form className="form-grid" onSubmit={handleAceptar}>
          <p className="state-text qr-publico__ticket-ayuda">
            Te enviamos un código a tu correo. Revísalo y escríbelo abajo junto
            con tu nombre y cargo para aceptar la propuesta.
          </p>

          <label className="form-field">
            <span className="form-field__label">Nombre</span>
            <input
              className="form-field__input"
              type="text"
              value={nombre}
              onChange={(e) => {
                setNombre(e.target.value)
                setError('')
              }}
              disabled={enviando}
              required
            />
          </label>

          <label className="form-field">
            <span className="form-field__label">Cargo</span>
            <input
              className="form-field__input"
              type="text"
              value={cargo}
              onChange={(e) => {
                setCargo(e.target.value)
                setError('')
              }}
              disabled={enviando}
              required
            />
          </label>

          <label className="form-field form-field--full">
            <span className="form-field__label">Código</span>
            <input
              className="form-field__input"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={codigo}
              onChange={(e) => {
                setCodigo(e.target.value)
                setError('')
              }}
              disabled={enviando}
              required
            />
          </label>

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <div className="form-actions">
            <button
              className="btn"
              type="submit"
              disabled={
                enviando ||
                nombre.trim() === '' ||
                cargo.trim() === '' ||
                codigo.trim() === ''
              }
            >
              {enviando ? 'Aceptando…' : 'Aceptar propuesta'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

export default function PropuestaPublicaPage() {
  const { token } = useParams()
  const [propuesta, setPropuesta] = useState(null)
  const [cargando, setCargando] = useState(true)
  // 'no-encontrado' (token inválido / no disponible, 404) | 'generico'.
  const [error, setError] = useState('')
  // Fecha de aceptación confirmada en esta sesión (tras aceptar). Al fijarse,
  // la vista pasa al estado aceptado y bloquea el formulario.
  const [fechaAceptada, setFechaAceptada] = useState(null)

  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setCargando(true)
        setError('')
        setPropuesta(null)
        setFechaAceptada(null)
        return getPropuesta(token)
      })
      .then((data) => {
        if (vigente && data) setPropuesta(data)
      })
      .catch((err) => {
        if (!vigente) return
        setError(
          err instanceof PropuestaNoEncontrada ? 'no-encontrado' : 'generico',
        )
      })
      .finally(() => {
        if (vigente) setCargando(false)
      })
    return () => {
      vigente = false
    }
  }, [token])

  // La propuesta está aceptada si llegó así del backend o si se aceptó aquí.
  const aceptada =
    fechaAceptada !== null || propuesta?.estado === 'ACEPTADA'
  const fechaAceptacion = fechaAceptada ?? propuesta?.fecha_aceptacion ?? null

  return (
    <div className="qr-publico">
      <section className="card qr-publico__card">
        <div className="qr-publico__brand">
          <img className="qr-publico__logo" src={logoMansillas} alt="Mansillas" />
          <span className="qr-publico__marca">MansillasSIC</span>
        </div>

        {cargando && <p className="state-text">Cargando propuesta…</p>}

        {!cargando && error === 'no-encontrado' && (
          <div className="qr-publico__estado">
            <h1>Propuesta no disponible</h1>
            <p className="state-text">
              El enlace no corresponde a ninguna propuesta disponible. Es posible
              que haya caducado o aún no se haya enviado.
            </p>
          </div>
        )}

        {!cargando && error === 'generico' && (
          <div className="qr-publico__estado">
            <h1>No se pudo cargar la propuesta</h1>
            <p className="state-text">
              Ocurrió un problema al consultar la propuesta. Inténtalo de nuevo
              más tarde.
            </p>
          </div>
        )}

        {!cargando && !error && propuesta && (
          <article className="qr-publico__ficha">
            <header className="qr-publico__cabecera">
              <span className="qr-publico__qr">{propuesta.empresa_nombre}</span>
              <span className="badge badge--off">{propuesta.estado}</span>
            </header>

            <dl className="qr-publico__datos">
              <div className="qr-publico__dato">
                <dt>Empresa</dt>
                <dd>{propuesta.empresa_nombre || '—'}</dd>
              </div>
              <div className="qr-publico__dato">
                <dt>Fecha de envío</dt>
                <dd>{formatearFecha(propuesta.fecha_envio)}</dd>
              </div>
            </dl>

            {(propuesta.sillas?.length ?? 0) > 0 && (
              <section className="qr-publico__componentes">
                <h2>Sillas incluidas</h2>
                <ul className="qr-publico__lista">
                  {propuesta.sillas.map((silla) => (
                    <li key={silla.codigo_qr} className="qr-publico__componente">
                      <span>
                        {silla.codigo_qr}
                        {silla.cargo ? ` · ${silla.cargo}` : ''}
                      </span>
                      <span
                        className={`badge ${ESTADO_SILLA_BADGE[silla.estado] ?? 'badge--off'}`}
                      >
                        {silla.estado}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {aceptada ? (
              <BloqueAceptada fechaAceptacion={fechaAceptacion} />
            ) : (
              <BloqueAceptacion token={token} onAceptada={setFechaAceptada} />
            )}
          </article>
        )}
      </section>
    </div>
  )
}
