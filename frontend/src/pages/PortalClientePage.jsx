/* Portal cliente (M7, R11, R4).
 *
 * Vista de SOLO LECTURA para el ADMIN_CLIENTE: consulta las sillas levantadas y
 * las precotizaciones de su propia empresa. No crea, edita ni acepta nada (la
 * aceptación de precotizaciones queda fuera de mi alcance).
 *
 * Aislamiento por empresa (R4): se consulta con el `id_empresa` del usuario
 * autenticado. El backend real impone el aislamiento según el usuario; aquí el
 * id solo acota la vista (y en modo mock filtra el store por esa empresa).
 *
 * Estados de carga, error y vacío en cada listado. Responsive de una columna
 * que escala a escritorio, igual que el resto de pantallas.
 */
import { useEffect, useState } from 'react'
import { listMisSillas, listMisPrecotizaciones } from '../api/portal-cliente'
import { useAuth } from '../context/auth-context'

export default function PortalClientePage() {
  const { user } = useAuth()
  const idEmpresa = user?.id_empresa ?? null

  const [sillas, setSillas] = useState([])
  const [cargandoSillas, setCargandoSillas] = useState(true)
  const [errorSillas, setErrorSillas] = useState('')

  const [precotizaciones, setPrecotizaciones] = useState([])
  const [cargandoPrecot, setCargandoPrecot] = useState(true)
  const [errorPrecot, setErrorPrecot] = useState('')

  async function cargarSillas() {
    setCargandoSillas(true)
    setErrorSillas('')
    try {
      setSillas(await listMisSillas(idEmpresa))
    } catch {
      setErrorSillas('No se pudieron cargar tus sillas.')
    } finally {
      setCargandoSillas(false)
    }
  }

  async function cargarPrecotizaciones() {
    setCargandoPrecot(true)
    setErrorPrecot('')
    try {
      setPrecotizaciones(await listMisPrecotizaciones(idEmpresa))
    } catch {
      setErrorPrecot('No se pudieron cargar tus precotizaciones.')
    } finally {
      setCargandoPrecot(false)
    }
  }

  // Carga inicial de ambos listados. Las dos piden en paralelo y cada una
  // resuelve su propio estado de carga/error.
  useEffect(() => {
    let vigente = true
    Promise.allSettled([
      listMisSillas(idEmpresa),
      listMisPrecotizaciones(idEmpresa),
    ]).then((resultados) => {
      if (!vigente) return
      const [resSillas, resPrecot] = resultados
      if (resSillas.status === 'fulfilled') setSillas(resSillas.value)
      else setErrorSillas('No se pudieron cargar tus sillas.')
      if (resPrecot.status === 'fulfilled') setPrecotizaciones(resPrecot.value)
      else setErrorPrecot('No se pudieron cargar tus precotizaciones.')
      setCargandoSillas(false)
      setCargandoPrecot(false)
    })
    return () => {
      vigente = false
    }
  }, [idEmpresa])

  return (
    <div className="page-stack">
      <section className="card">
        <h1>Portal cliente</h1>
        <p className="state-text">
          Consulta de solo lectura de las sillas levantadas y las
          precotizaciones de tu empresa.
        </p>
      </section>

      <section className="card">
        <h2>Mis sillas</h2>

        {cargandoSillas && <p className="state-text">Cargando sillas…</p>}

        {!cargandoSillas && errorSillas && (
          <div className="state-error" role="alert">
            <p>{errorSillas}</p>
            <button className="btn btn--ghost" type="button" onClick={cargarSillas}>
              Reintentar
            </button>
          </div>
        )}

        {!cargandoSillas && !errorSillas && sillas.length === 0 && (
          <p className="state-text">
            Aún no hay sillas levantadas para tu empresa.
          </p>
        )}

        {!cargandoSillas && !errorSillas && sillas.length > 0 && (
          <ul className="sillas-lista">
            {sillas.map((s) => (
              <li key={s.id_silla} className="sillas-lista__item">
                <div className="sillas-lista__cabecera">
                  <span className="sillas-lista__qr">{s.codigo_qr}</span>
                  {s.sugerir_cambio ? (
                    <span className="badge badge--alerta">Sugerir cambio</span>
                  ) : (
                    <span className="badge badge--ok">En buen estado</span>
                  )}
                </div>
                {s.cargo && <p className="sillas-lista__cargo">{s.cargo}</p>}
                {s.sede && (
                  <p className="sillas-lista__componentes">Sede: {s.sede}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Mis precotizaciones</h2>

        {cargandoPrecot && (
          <p className="state-text">Cargando precotizaciones…</p>
        )}

        {!cargandoPrecot && errorPrecot && (
          <div className="state-error" role="alert">
            <p>{errorPrecot}</p>
            <button
              className="btn btn--ghost"
              type="button"
              onClick={cargarPrecotizaciones}
            >
              Reintentar
            </button>
          </div>
        )}

        {!cargandoPrecot && !errorPrecot && precotizaciones.length === 0 && (
          <p className="state-text">
            Aún no hay precotizaciones para tu empresa.
          </p>
        )}

        {!cargandoPrecot && !errorPrecot && precotizaciones.length > 0 && (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Estado</th>
                  <th>Creada</th>
                  <th>Observaciones</th>
                </tr>
              </thead>
              <tbody>
                {precotizaciones.map((p) => (
                  <tr key={p.id_precotizacion}>
                    <td>{p.id_precotizacion}</td>
                    <td>
                      <span className="badge badge--off">{p.estado}</span>
                    </td>
                    <td>
                      {p.fecha_creacion
                        ? new Date(p.fecha_creacion).toLocaleString()
                        : '—'}
                    </td>
                    <td>{p.observaciones ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
