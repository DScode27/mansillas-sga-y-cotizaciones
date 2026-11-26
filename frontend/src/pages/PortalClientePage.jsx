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
import { getPermisoQr, setPermisoQr } from '../api/permisos-qr'
import { useAuth } from '../context/auth-context'
import SillaCard from '../components/SillaCard'

// Opciones de permiso QR con etiqueta legible (RF-18, R2). El valor es el entero
// que el backend espera (1/2/3); la etiqueta a/b/c es la que ve el admin.
const OPCIONES_PERMISO_QR = [
  { valor: 1, etiqueta: '(a) Solo consulta' },
  { valor: 2, etiqueta: '(b) Consulta y envío de tickets' },
  { valor: 3, etiqueta: '(c) Tickets solo por el administrador' },
]

// Mensaje legible por código HTTP al guardar el permiso QR (RF-18, R4). El
// cuerpo crudo del backend nunca se muestra al usuario.
function mensajeErrorPermisoQr(status) {
  if (status === 422) return 'El nivel debe ser uno de los tres valores (a, b o c).'
  if (status === 403) return 'No tienes permiso para configurar esta empresa.'
  return 'No se pudo guardar el nivel de permiso. Inténtalo de nuevo.'
}

export default function PortalClientePage() {
  const { user } = useAuth()
  const idEmpresa = user?.id_empresa ?? null

  const [sillas, setSillas] = useState([])
  const [cargandoSillas, setCargandoSillas] = useState(true)
  const [errorSillas, setErrorSillas] = useState('')

  const [precotizaciones, setPrecotizaciones] = useState([])
  const [cargandoPrecot, setCargandoPrecot] = useState(true)
  const [errorPrecot, setErrorPrecot] = useState('')

  // Permiso QR (RF-18): única acción de escritura del admin cliente. `nivel` es
  // el nivel actualmente guardado; `seleccion` el elegido en el selector (puede
  // diferir antes de guardar). Estados independientes de carga/guardado/éxito/
  // error para esta sección.
  const [nivelPermiso, setNivelPermiso] = useState(null)
  const [seleccionPermiso, setSeleccionPermiso] = useState('')
  const [cargandoPermiso, setCargandoPermiso] = useState(true)
  const [guardandoPermiso, setGuardandoPermiso] = useState(false)
  const [errorPermiso, setErrorPermiso] = useState('')
  const [exitoPermiso, setExitoPermiso] = useState('')

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

  async function cargarPermiso() {
    setCargandoPermiso(true)
    setErrorPermiso('')
    setExitoPermiso('')
    try {
      const nivel = await getPermisoQr(idEmpresa)
      setNivelPermiso(nivel)
      setSeleccionPermiso(String(nivel))
    } catch (err) {
      setErrorPermiso(mensajeErrorPermisoQr(err.response?.status))
    } finally {
      setCargandoPermiso(false)
    }
  }

  // Guarda el nivel elegido (RF-18, R3). Tras el éxito, fija el nuevo nivel
  // actual y confirma el guardado. El error se mapea por código HTTP (422/403).
  async function handleGuardarPermiso(event) {
    event.preventDefault()
    setErrorPermiso('')
    setExitoPermiso('')
    setGuardandoPermiso(true)
    try {
      const nivel = await setPermisoQr(idEmpresa, Number(seleccionPermiso))
      setNivelPermiso(nivel)
      setSeleccionPermiso(String(nivel))
      const opcion = OPCIONES_PERMISO_QR.find((o) => o.valor === nivel)
      setExitoPermiso(`Nivel guardado: ${opcion?.etiqueta ?? nivel}.`)
    } catch (err) {
      setErrorPermiso(mensajeErrorPermisoQr(err.response?.status))
    } finally {
      setGuardandoPermiso(false)
    }
  }

  // Carga inicial de ambos listados y del nivel de permiso QR. Las tres piden en
  // paralelo y cada una resuelve su propio estado de carga/error.
  useEffect(() => {
    let vigente = true
    Promise.allSettled([
      listMisSillas(idEmpresa),
      listMisPrecotizaciones(idEmpresa),
      getPermisoQr(idEmpresa),
    ]).then((resultados) => {
      if (!vigente) return
      const [resSillas, resPrecot, resPermiso] = resultados
      if (resSillas.status === 'fulfilled') setSillas(resSillas.value)
      else setErrorSillas('No se pudieron cargar tus sillas.')
      if (resPrecot.status === 'fulfilled') setPrecotizaciones(resPrecot.value)
      else setErrorPrecot('No se pudieron cargar tus precotizaciones.')
      if (resPermiso.status === 'fulfilled') {
        setNivelPermiso(resPermiso.value)
        setSeleccionPermiso(String(resPermiso.value))
      } else {
        setErrorPermiso(
          mensajeErrorPermisoQr(resPermiso.reason?.response?.status),
        )
      }
      setCargandoSillas(false)
      setCargandoPrecot(false)
      setCargandoPermiso(false)
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
        <h2>Permisos de acceso por QR</h2>
        <p className="state-text">
          Elige con qué nivel acceden tus empleados al escanear el QR de sus
          sillas. Es la única configuración editable de tu portal.
        </p>

        {cargandoPermiso && <p className="state-text">Cargando nivel…</p>}

        {!cargandoPermiso && errorPermiso && nivelPermiso == null && (
          <div className="state-error" role="alert">
            <p>{errorPermiso}</p>
            <button
              className="btn btn--ghost"
              type="button"
              onClick={cargarPermiso}
            >
              Reintentar
            </button>
          </div>
        )}

        {!cargandoPermiso && nivelPermiso != null && (
          <form className="form-grid" onSubmit={handleGuardarPermiso}>
            <label className="form-field">
              <span className="form-field__label">Nivel de permiso QR</span>
              <select
                className="form-field__input"
                value={seleccionPermiso}
                onChange={(e) => {
                  setSeleccionPermiso(e.target.value)
                  setErrorPermiso('')
                  setExitoPermiso('')
                }}
                disabled={guardandoPermiso}
              >
                {OPCIONES_PERMISO_QR.map((o) => (
                  <option key={o.valor} value={o.valor}>
                    {o.etiqueta}
                  </option>
                ))}
              </select>
            </label>

            {errorPermiso && (
              <p className="form-error" role="alert">
                {errorPermiso}
              </p>
            )}

            {exitoPermiso && (
              <p className="form-success" role="status">
                {exitoPermiso}
              </p>
            )}

            <div className="form-actions">
              <button
                className="btn"
                type="submit"
                disabled={
                  guardandoPermiso ||
                  Number(seleccionPermiso) === nivelPermiso
                }
              >
                {guardandoPermiso ? 'Guardando…' : 'Guardar nivel'}
              </button>
            </div>
          </form>
        )}
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
              <SillaCard
                key={s.id_silla}
                silla={s}
                extra={
                  s.sede ? (
                    <p className="sillas-lista__componentes">Sede: {s.sede}</p>
                  ) : null
                }
              />
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
