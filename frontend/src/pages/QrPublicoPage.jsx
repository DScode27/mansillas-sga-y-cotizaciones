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
import { getSillaPublica, TokenNoEncontrado } from '../api/qr-publico'

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

export default function QrPublicoPage() {
  const { token } = useParams()
  const [silla, setSilla] = useState(null)
  const [cargando, setCargando] = useState(true)
  // 'no-encontrado' (token inválido, 404) | 'generico' (fallo de red/servidor).
  const [error, setError] = useState('')

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
          </article>
        )}
      </section>
    </div>
  )
}
