/* Portal comercial (M5, R9).
 *
 * El comercial, sobre una visita ya levantada, prepara la propuesta:
 *   1. Elige empresa y visita (recursos de otros devs, mockeables). El filtro
 *      por empresa solo acota la vista; el aislamiento real lo impone el
 *      backend según el usuario (R4).
 *   2. Ve las sillas levantadas con el estado de sus componentes y cuáles se
 *      sugiere cambiar (`sugerir_cambio`, según `vista_estado_mantenimiento`).
 *   3. Crea precotizaciones en estado `BORRADOR` y ve las ya creadas. La
 *      aceptación (ENVIADA→ACEPTADA) queda fuera de mi alcance.
 *
 * Estados de carga, error y vacío en cada listado. Responsive de una columna
 * que escala a escritorio, igual que el resto del portal.
 */
import { useEffect, useMemo, useState } from 'react'
import { listEmpresas } from '../api/empresas'
import { listVisitas } from '../api/visitas'
import { listSillas, COMPONENTES } from '../api/sillas'
import {
  listPrecotizaciones,
  createPrecotizacion,
} from '../api/precotizaciones'
import { useAuth } from '../context/auth-context'

const COMPONENTE_NOMBRE = new Map(
  COMPONENTES.map((c) => [c.id_componente, c.nombre]),
)

// Componentes a cambiar según el levantamiento: los marcados como DANADO.
function componentesSugeridos(silla) {
  return (silla.componentes ?? [])
    .filter((c) => c.estado === 'DANADO')
    .map((c) => COMPONENTE_NOMBRE.get(c.id_componente) ?? `#${c.id_componente}`)
}

export default function PortalComercialPage() {
  const { user } = useAuth()

  const [empresas, setEmpresas] = useState([])
  const [cargandoEmpresas, setCargandoEmpresas] = useState(true)
  const [errorEmpresas, setErrorEmpresas] = useState('')
  const [empresaSel, setEmpresaSel] = useState('')

  const [visitas, setVisitas] = useState([])
  const [cargandoVisitas, setCargandoVisitas] = useState(false)
  const [errorVisitas, setErrorVisitas] = useState('')
  const [visitaSel, setVisitaSel] = useState('')

  const [sillas, setSillas] = useState([])
  const [cargandoSillas, setCargandoSillas] = useState(false)
  const [errorSillas, setErrorSillas] = useState('')

  const [precotizaciones, setPrecotizaciones] = useState([])
  const [cargandoPrecot, setCargandoPrecot] = useState(false)
  const [errorPrecot, setErrorPrecot] = useState('')

  const [observaciones, setObservaciones] = useState('')
  const [creando, setCreando] = useState(false)
  const [errorCrear, setErrorCrear] = useState('')
  const [exito, setExito] = useState('')

  const idEmpresaSel = empresaSel ? Number(empresaSel) : null
  const idVisitaSel = visitaSel ? Number(visitaSel) : null

  // Empresas para el selector (mock conmutable).
  useEffect(() => {
    let vigente = true
    listEmpresas()
      .then((data) => {
        if (vigente) setEmpresas(data)
      })
      .catch(() => {
        if (vigente) setErrorEmpresas('No se pudieron cargar las empresas.')
      })
      .finally(() => {
        if (vigente) setCargandoEmpresas(false)
      })
    return () => {
      vigente = false
    }
  }, [])

  // Al cambiar de empresa, se recargan sus visitas y se limpia la selección.
  // Las llamadas a setState van dentro del flujo asíncrono (como en las demás
  // pantallas) para no disparar renders en cascada desde el efecto.
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setVisitaSel('')
        setVisitas([])
        if (!idEmpresaSel) return null
        setCargandoVisitas(true)
        setErrorVisitas('')
        return listVisitas(idEmpresaSel)
      })
      .then((data) => {
        if (vigente && data) setVisitas(data)
      })
      .catch(() => {
        if (vigente) setErrorVisitas('No se pudieron cargar las visitas.')
      })
      .finally(() => {
        if (vigente && idEmpresaSel) setCargandoVisitas(false)
      })
    return () => {
      vigente = false
    }
  }, [idEmpresaSel])

  // Al elegir visita, se cargan sus sillas y sus precotizaciones, y se limpia
  // el formulario de creación.
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setObservaciones('')
        setErrorCrear('')
        setExito('')
        setSillas([])
        setPrecotizaciones([])
        if (!idVisitaSel) return null
        setCargandoSillas(true)
        setErrorSillas('')
        setCargandoPrecot(true)
        setErrorPrecot('')
        return Promise.allSettled([
          listSillas(idVisitaSel),
          listPrecotizaciones(idVisitaSel),
        ])
      })
      .then((resultados) => {
        if (!vigente || !resultados) return
        const [resSillas, resPrecot] = resultados
        if (resSillas.status === 'fulfilled') setSillas(resSillas.value)
        else setErrorSillas('No se pudieron cargar las sillas.')
        if (resPrecot.status === 'fulfilled') setPrecotizaciones(resPrecot.value)
        else setErrorPrecot('No se pudieron cargar las precotizaciones.')
      })
      .finally(() => {
        if (vigente && idVisitaSel) {
          setCargandoSillas(false)
          setCargandoPrecot(false)
        }
      })
    return () => {
      vigente = false
    }
  }, [idVisitaSel])

  async function recargarSillas() {
    if (!idVisitaSel) return
    setCargandoSillas(true)
    setErrorSillas('')
    try {
      setSillas(await listSillas(idVisitaSel))
    } catch {
      setErrorSillas('No se pudieron cargar las sillas.')
    } finally {
      setCargandoSillas(false)
    }
  }

  async function recargarPrecotizaciones() {
    if (!idVisitaSel) return
    setCargandoPrecot(true)
    setErrorPrecot('')
    try {
      setPrecotizaciones(await listPrecotizaciones(idVisitaSel))
    } catch {
      setErrorPrecot('No se pudieron cargar las precotizaciones.')
    } finally {
      setCargandoPrecot(false)
    }
  }

  async function handleCrear(event) {
    event.preventDefault()
    setErrorCrear('')
    setExito('')
    if (!idVisitaSel) {
      setErrorCrear('Elige una visita para crear la precotización.')
      return
    }
    setCreando(true)
    try {
      const precot = await createPrecotizacion({
        id_empresa: idEmpresaSel,
        id_visita: idVisitaSel,
        creada_por: user.id_usuario,
        observaciones,
      })
      setExito(`Precotización #${precot.id_precotizacion} creada en borrador.`)
      setObservaciones('')
      await recargarPrecotizaciones()
    } catch (err) {
      const status = err.response?.status
      if (status === 400) {
        setErrorCrear(err.response?.data?.detail ?? 'Datos inválidos.')
      } else if (status === 403) {
        setErrorCrear('No tienes permiso para crear precotizaciones.')
      } else {
        setErrorCrear('No se pudo crear la precotización. Inténtalo de nuevo.')
      }
    } finally {
      setCreando(false)
    }
  }

  // Resumen para el encabezado: cuántas sillas y cuántas con sugerencia.
  const resumenSillas = useMemo(() => {
    const total = sillas.length
    const sugeridas = sillas.filter((s) => s.sugerir_cambio).length
    return { total, sugeridas }
  }, [sillas])

  return (
    <div className="page-stack">
      <section className="card">
        <h1>Portal comercial</h1>
        <p className="state-text">
          Elige la empresa y la visita para revisar las sillas levantadas y
          preparar precotizaciones en borrador.
        </p>

        {cargandoEmpresas && <p className="state-text">Cargando empresas…</p>}

        {!cargandoEmpresas && errorEmpresas && (
          <p className="form-error" role="alert">
            {errorEmpresas}
          </p>
        )}

        {!cargandoEmpresas && !errorEmpresas && (
          <div className="levantamiento__selectores">
            <label className="form-field">
              <span className="form-field__label">Empresa</span>
              <select
                className="form-field__input"
                value={empresaSel}
                onChange={(e) => setEmpresaSel(e.target.value)}
                disabled={empresas.length === 0}
              >
                <option value="">— Seleccionar —</option>
                {empresas.map((e) => (
                  <option key={e.id_empresa} value={e.id_empresa}>
                    {e.nombre}
                  </option>
                ))}
              </select>
            </label>

            {idEmpresaSel && (
              <label className="form-field">
                <span className="form-field__label">Visita</span>
                {cargandoVisitas ? (
                  <span className="state-text">Cargando visitas…</span>
                ) : errorVisitas ? (
                  <span className="form-error" role="alert">
                    {errorVisitas}
                  </span>
                ) : (
                  <select
                    className="form-field__input"
                    value={visitaSel}
                    onChange={(e) => setVisitaSel(e.target.value)}
                    disabled={visitas.length === 0}
                  >
                    <option value="">
                      {visitas.length === 0 ? '— Sin visitas —' : '— Seleccionar —'}
                    </option>
                    {visitas.map((v) => (
                      <option key={v.id_visita} value={v.id_visita}>
                        Visita #{v.id_visita}
                        {v.fecha_programada
                          ? ` · ${new Date(v.fecha_programada).toLocaleDateString()}`
                          : ''}
                      </option>
                    ))}
                  </select>
                )}
              </label>
            )}
          </div>
        )}
      </section>

      {idVisitaSel && (
        <section className="card">
          <h2>Sillas levantadas</h2>

          {cargandoSillas && <p className="state-text">Cargando sillas…</p>}

          {!cargandoSillas && errorSillas && (
            <div className="state-error" role="alert">
              <p>{errorSillas}</p>
              <button className="btn btn--ghost" type="button" onClick={recargarSillas}>
                Reintentar
              </button>
            </div>
          )}

          {!cargandoSillas && !errorSillas && sillas.length === 0 && (
            <p className="state-text">
              Esta visita aún no tiene sillas levantadas.
            </p>
          )}

          {!cargandoSillas && !errorSillas && sillas.length > 0 && (
            <>
              <p className="state-text">
                {resumenSillas.total} silla
                {resumenSillas.total === 1 ? '' : 's'} ·{' '}
                {resumenSillas.sugeridas} con sugerencia de cambio.
              </p>
              <ul className="sillas-lista">
                {sillas.map((s) => {
                  const sugeridos = componentesSugeridos(s)
                  return (
                    <li key={s.id_silla} className="sillas-lista__item">
                      <div className="sillas-lista__cabecera">
                        <span className="sillas-lista__qr">{s.codigo_qr}</span>
                        {s.sugerir_cambio ? (
                          <span className="badge badge--alerta">Sugerir cambio</span>
                        ) : (
                          <span className="badge badge--ok">En buen estado</span>
                        )}
                      </div>
                      <p className="sillas-lista__cargo">{s.cargo}</p>
                      {sugeridos.length > 0 && (
                        <p className="sillas-lista__componentes">
                          Componentes a cambiar: {sugeridos.join(', ')}.
                        </p>
                      )}
                    </li>
                  )
                })}
              </ul>
            </>
          )}
        </section>
      )}

      {idVisitaSel && (
        <section className="card">
          <h2>Precotizaciones</h2>

          <form className="form-grid" onSubmit={handleCrear}>
            <label className="form-field" style={{ gridColumn: '1 / -1' }}>
              <span className="form-field__label">Observaciones (opcional)</span>
              <textarea
                className="form-field__input"
                rows={2}
                value={observaciones}
                onChange={(e) => setObservaciones(e.target.value)}
                disabled={creando}
                placeholder="Notas para preparar la propuesta"
              />
            </label>

            {errorCrear && (
              <p className="form-error" role="alert">
                {errorCrear}
              </p>
            )}
            {exito && (
              <p className="form-success" role="status">
                {exito}
              </p>
            )}

            <div className="form-actions">
              <button className="btn" type="submit" disabled={creando}>
                {creando ? 'Creando…' : 'Crear precotización en borrador'}
              </button>
            </div>
          </form>

          {cargandoPrecot && <p className="state-text">Cargando precotizaciones…</p>}

          {!cargandoPrecot && errorPrecot && (
            <div className="state-error" role="alert">
              <p>{errorPrecot}</p>
              <button
                className="btn btn--ghost"
                type="button"
                onClick={recargarPrecotizaciones}
              >
                Reintentar
              </button>
            </div>
          )}

          {!cargandoPrecot && !errorPrecot && precotizaciones.length === 0 && (
            <p className="state-text">
              Esta visita aún no tiene precotizaciones.
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
      )}
    </div>
  )
}
