/* Vista pública por QR (M6, R10).
 *
 * Ruta pública (fuera de RequireAuth): cualquier persona que escanea el QR ve
 * la ficha básica de la silla por su `token_publico`, sin login ni OTP. Muestra
 * empresa/sede, la identificación de la silla y el estado de sus componentes.
 * Token inválido → 404 (ficha "no encontrada"). Reutiliza la identidad visual
 * (logo sobre blanco, paleta de marca) con el mismo marco centrado del login.
 */
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import logoMansillas from '../assets/logoMansillas.jpg'
import Lightbox from '../components/Lightbox'
import {
  getSillaPublica,
  getFotoPublicaUrl,
  listFotosPublicas,
  solicitarOtpTicket,
  crearTicket,
  TokenNoEncontrado,
} from '../api/qr-publico'

const ESTADO_COMPONENTE_LABEL = {
  BUENO: 'Bueno',
  MANTENIMIENTO: 'Mantenimiento',
  DANADO: 'Dañado',
  NO_APLICA: 'No aplica',
}

// Clase de insignia por estado del componente (reutiliza las de theme/layout).
const ESTADO_COMPONENTE_BADGE = {
  BUENO: 'badge--ok',
  MANTENIMIENTO: 'badge--alerta',
  DANADO: 'badge--alerta',
  NO_APLICA: 'badge--off',
}

// Mensaje legible por código HTTP al solicitar el OTP (paso 1, RF-24, R5). El
// cuerpo crudo del backend nunca se muestra; un fallo de red (sin `response`)
// cae en el genérico.
function mensajeErrorOtp(status) {
  if (status === 404) {
    return 'No encontramos un empleado con ese correo o documento en esta empresa.'
  }
  if (status === 403) return 'El QR de esta silla no permite enviar tickets.'
  return 'No se pudo solicitar el código. Revisa tu conexión e inténtalo de nuevo.'
}

// Mensaje legible por código HTTP al enviar el ticket (paso 2, RF-24, R5). El
// OTP nunca se muestra ni se registra; el 400 solo indica que el código no es
// válido o expiró, sin revelar el valor esperado.
function mensajeErrorTicket(status) {
  if (status === 400) {
    return 'El código no es válido o ya expiró. Solicita uno nuevo e inténtalo otra vez.'
  }
  if (status === 404) {
    return 'No encontramos un empleado con ese correo o documento en esta empresa.'
  }
  if (status === 403) return 'El QR de esta silla no permite enviar tickets.'
  return 'No se pudo enviar el ticket. Revisa tu conexión e inténtalo de nuevo.'
}

// Bloque de envío de ticket por QR (RF-24). Solo se renderiza cuando la ficha
// trae `permiso_qr = 2`; los niveles 1 y 3 muestran un aviso sin formulario y
// se resuelven en el componente padre. Flujo de dos pasos: identificación →
// solicitar código (204) y redacción → enviar ticket (201). Vista anónima: el
// código solo se envía al backend, nunca se muestra ni se registra en claro.
function BloqueTicket({ token }) {
  // 'identificacion' (paso 1) | 'redaccion' (paso 2) | 'enviado' (confirmación).
  const [paso, setPaso] = useState('identificacion')

  // Identificación del empleado: correo o documento (al menos uno).
  const [correo, setCorreo] = useState('')
  const [documento, setDocumento] = useState('')

  // Redacción del ticket. `codigo` es el OTP recibido por correo; se mantiene en
  // estado solo para enviarlo y nunca se muestra fuera de su propio input.
  const [asunto, setAsunto] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [codigo, setCodigo] = useState('')

  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState('')
  const [ticketCreado, setTicketCreado] = useState(null)

  const puedeSolicitar = correo.trim() !== '' || documento.trim() !== ''

  async function handleSolicitarCodigo(event) {
    event.preventDefault()
    setError('')
    setEnviando(true)
    try {
      await solicitarOtpTicket(token, {
        correo: correo.trim() || null,
        documento: documento.trim() || null,
      })
      setPaso('redaccion')
    } catch (err) {
      setError(mensajeErrorOtp(err.response?.status))
    } finally {
      setEnviando(false)
    }
  }

  async function handleEnviarTicket(event) {
    event.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const ticket = await crearTicket(token, {
        asunto: asunto.trim(),
        descripcion: descripcion.trim(),
        correo: correo.trim() || null,
        documento: documento.trim() || null,
        codigo: codigo.trim(),
      })
      setTicketCreado(ticket)
      setPaso('enviado')
    } catch (err) {
      setError(mensajeErrorTicket(err.response?.status))
    } finally {
      setEnviando(false)
    }
  }

  if (paso === 'enviado') {
    return (
      <section className="qr-publico__ticket">
        <h2>Reportar un problema</h2>
        <p className="form-success" role="status">
          Ticket enviado correctamente. Tu número de ticket es{' '}
          <strong>#{ticketCreado?.id_ticket}</strong>.
        </p>
      </section>
    )
  }

  return (
    <section className="qr-publico__ticket">
      <h2>Reportar un problema</h2>

      {paso === 'identificacion' && (
        <form className="form-grid" onSubmit={handleSolicitarCodigo}>
          <p className="state-text qr-publico__ticket-ayuda">
            Identifícate con tu correo o tu documento y te enviaremos un código
            para validar el ticket.
          </p>

          <label className="form-field">
            <span className="form-field__label">Correo</span>
            <input
              className="form-field__input"
              type="email"
              value={correo}
              onChange={(e) => {
                setCorreo(e.target.value)
                setError('')
              }}
              disabled={enviando}
              autoComplete="email"
            />
          </label>

          <label className="form-field">
            <span className="form-field__label">Documento</span>
            <input
              className="form-field__input"
              type="text"
              value={documento}
              onChange={(e) => {
                setDocumento(e.target.value)
                setError('')
              }}
              disabled={enviando}
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
              disabled={enviando || !puedeSolicitar}
            >
              {enviando ? 'Solicitando…' : 'Solicitar código'}
            </button>
          </div>
        </form>
      )}

      {paso === 'redaccion' && (
        <form className="form-grid" onSubmit={handleEnviarTicket}>
          <p className="state-text qr-publico__ticket-ayuda">
            Te enviamos un código a tu correo. Revísalo y escríbelo abajo junto
            con tu reporte.
          </p>

          <label className="form-field">
            <span className="form-field__label">Asunto</span>
            <input
              className="form-field__input"
              type="text"
              value={asunto}
              onChange={(e) => {
                setAsunto(e.target.value)
                setError('')
              }}
              disabled={enviando}
              required
            />
          </label>

          <label className="form-field">
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

          <label className="form-field form-field--full">
            <span className="form-field__label">Descripción</span>
            <textarea
              className="form-field__input"
              rows={4}
              value={descripcion}
              onChange={(e) => {
                setDescripcion(e.target.value)
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
                asunto.trim() === '' ||
                descripcion.trim() === '' ||
                codigo.trim() === ''
              }
            >
              {enviando ? 'Enviando…' : 'Enviar ticket'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

// Aviso para los niveles que NO habilitan el envío de tickets (RF-24, R2):
// nivel 1 (solo consulta) y nivel 3 (tickets solo por el administrador).
function AvisoSinTicket({ permisoQr }) {
  const mensaje =
    permisoQr === 3
      ? 'El envío de tickets de esta empresa está reservado a su administrador.'
      : 'Esta silla solo permite consultar su ficha; no admite el envío de tickets.'

  return (
    <section className="qr-publico__ticket">
      <h2>Reportar un problema</h2>
      <p className="state-text">{mensaje}</p>
    </section>
  )
}

export default function QrPublicoPage() {
  const { token } = useParams()
  const [silla, setSilla] = useState(null)
  const [cargando, setCargando] = useState(true)
  // 'no-encontrado' (token inválido, 404) | 'generico' (fallo de red/servidor).
  const [error, setError] = useState('')

  // Fotos públicas de la silla: cada una es un object URL que se revoca al
  // desmontar o al cambiar de token, para no filtrar memoria. Si la carga de
  // fotos falla (o no hay), la ficha se muestra igual sin sección de fotos.
  const [fotos, setFotos] = useState([])
  // Foto abierta en el lightbox (su url) o null.
  const [fotoAmpliada, setFotoAmpliada] = useState(null)

  // Las llamadas a setState van dentro del flujo asíncrono (como en las demás
  // pantallas) para no disparar renders en cascada desde el propio efecto.
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setCargando(true)
        setError('')
        setSilla(null)
        return getSillaPublica(token)
      })
      .then((data) => {
        if (vigente && data) setSilla(data)
      })
      .catch((err) => {
        if (!vigente) return
        setError(err instanceof TokenNoEncontrado ? 'no-encontrado' : 'generico')
      })
      .finally(() => {
        if (vigente) setCargando(false)
      })
    return () => {
      vigente = false
    }
  }, [token])

  // Carga las fotos tras resolver el token: lista los ids y baja cada imagen
  // como object URL. Se revocan todas al desmontar o al cambiar de token.
  useEffect(() => {
    let vigente = true
    const urls = []
    // El reset va dentro del flujo asíncrono (como el resto de efectos de esta
    // pantalla) para no disparar un render en cascada desde el efecto.
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setFotos([])
        return listFotosPublicas(token)
      })
      .then(async (lista) => {
        if (!lista) return
        for (const foto of lista) {
          if (!vigente) return
          try {
            const url = await getFotoPublicaUrl(token, foto.id_fotografia)
            if (!vigente) {
              if (url.startsWith('blob:')) URL.revokeObjectURL(url)
              return
            }
            urls.push(url)
            setFotos((prev) => [...prev, { id: foto.id_fotografia, url }])
          } catch {
            // Una foto que no baja no rompe la ficha; se omite.
          }
        }
      })
      .catch(() => {
        // Sin fotos o token inválido: la ficha se encarga del error de token.
      })
    return () => {
      vigente = false
      urls.forEach((u) => {
        if (u.startsWith('blob:')) URL.revokeObjectURL(u)
      })
    }
  }, [token])

  return (
    <div className="qr-publico">
      <section className="card qr-publico__card">
        <div className="qr-publico__brand">
          <img className="qr-publico__logo" src={logoMansillas} alt="Mansillas" />
          <span className="qr-publico__marca">MansillasSIC</span>
        </div>

        {cargando && <p className="state-text">Cargando ficha de la silla…</p>}

        {!cargando && error === 'no-encontrado' && (
          <div className="qr-publico__estado">
            <h1>Silla no encontrada</h1>
            <p className="state-text">
              El código QR no corresponde a ninguna silla registrada.
            </p>
          </div>
        )}

        {!cargando && error === 'generico' && (
          <div className="qr-publico__estado">
            <h1>No se pudo cargar la ficha</h1>
            <p className="state-text">
              Ocurrió un problema al consultar la silla. Inténtalo de nuevo más
              tarde.
            </p>
          </div>
        )}

        {!cargando && !error && silla && (
          <article className="qr-publico__ficha">
            <header className="qr-publico__cabecera">
              <span className="qr-publico__qr">{silla.codigo_qr}</span>
              {silla.estado && (
                <span className="badge badge--off">{silla.estado}</span>
              )}
            </header>

            <dl className="qr-publico__datos">
              <div className="qr-publico__dato">
                <dt>Empresa</dt>
                <dd>{silla.empresa ?? '—'}</dd>
              </div>
              <div className="qr-publico__dato">
                <dt>Sede</dt>
                <dd>{silla.sede ?? '—'}</dd>
              </div>
              {silla.cargo && (
                <div className="qr-publico__dato">
                  <dt>Puesto</dt>
                  <dd>{silla.cargo}</dd>
                </div>
              )}
              {silla.serial_antiguo && (
                <div className="qr-publico__dato">
                  <dt>Serial antiguo</dt>
                  <dd>{silla.serial_antiguo}</dd>
                </div>
              )}
            </dl>

            {(silla.componentes?.length ?? 0) > 0 && (
              <section className="qr-publico__componentes">
                <h2>Estado de componentes</h2>
                <ul className="qr-publico__lista">
                  {silla.componentes.map((comp) => (
                    <li key={comp.nombre} className="qr-publico__componente">
                      <span>{comp.nombre}</span>
                      <span
                        className={`badge ${ESTADO_COMPONENTE_BADGE[comp.estado] ?? 'badge--off'}`}
                      >
                        {ESTADO_COMPONENTE_LABEL[comp.estado] ?? comp.estado}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {fotos.length > 0 && (
              <section className="qr-publico__fotos">
                <h2>Fotos de la silla</h2>
                <ul className="qr-publico__fotos-lista">
                  {fotos.map((f) => (
                    <li key={f.id} className="qr-publico__foto">
                      <button
                        type="button"
                        className="foto-thumb-btn"
                        onClick={() => setFotoAmpliada(f.url)}
                        aria-label={`Ampliar foto ${f.id} de la silla ${silla.codigo_qr}`}
                      >
                        <img
                          src={f.url}
                          alt={`Foto ${f.id} de la silla ${silla.codigo_qr}`}
                          className="qr-publico__foto-img"
                        />
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {silla.permiso_qr === 2 && <BloqueTicket token={token} />}
            {(silla.permiso_qr === 1 || silla.permiso_qr === 3) && (
              <AvisoSinTicket permisoQr={silla.permiso_qr} />
            )}
          </article>
        )}

        {fotoAmpliada && (
          <Lightbox
            url={fotoAmpliada}
            alt={`Foto de la silla ${silla?.codigo_qr ?? ''}`}
            onClose={() => setFotoAmpliada(null)}
          />
        )}
      </section>
    </div>
  )
}
