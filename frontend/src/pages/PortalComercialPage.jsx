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
import { Fragment, useEffect, useMemo, useState } from 'react'
import { listEmpresas } from '../api/empresas'
import { listVisitas } from '../api/visitas'
import { listSillas, COMPONENTES } from '../api/sillas'
import {
  listPrecotizaciones,
  createPrecotizacion,
  enviarPrecotizacion,
  listAccesos,
} from '../api/precotizaciones'
import { descargarQrPdf } from '../api/qr'
import { exportarInventario } from '../api/inventario'
import { descargarBlob } from '../utils/descargarBlob'
import SillaCard from '../components/SillaCard'

// Mensaje legible por código HTTP al bajar el PDF de QR (RF-05). El cuerpo crudo
// del backend nunca se muestra al usuario.
function mensajeErrorQrPdf(status) {
  if (status === 400) return 'Selecciona al menos una silla.'
  if (status === 403) return 'No tienes permiso para estas sillas.'
  if (status === 404) return 'Alguna silla no existe.'
  return 'No se pudo generar el PDF de QR. Inténtalo de nuevo.'
}

// Mensaje legible por código HTTP al exportar el inventario (RF-11). El backend
// acota el alcance por rol; aquí solo se mapean los errores a un texto claro.
function mensajeErrorInventario(status) {
  if (status === 400) return 'Formato de exportación no admitido.'
  return 'No se pudo exportar el inventario. Inténtalo de nuevo.'
}

// Mensaje legible por código HTTP al enviar la precotización al cliente (RF-13).
// El cuerpo crudo del backend nunca se muestra al usuario.
function mensajeErrorEnviar(status) {
  if (status === 422) return 'Correo inválido o falta confirmar la validación.'
  if (status === 409)
    return 'La precotización no se puede enviar a ese destinatario en su estado actual.'
  if (status === 503) return 'El envío de correo no está configurado.'
  if (status === 502) return 'No fue posible enviar el correo. Inténtalo de nuevo.'
  if (status === 404) return 'La precotización ya no existe.'
  return 'No se pudo enviar la precotización. Inténtalo de nuevo.'
}

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
  const [descargando, setDescargando] = useState(false)
  const [errorDescarga, setErrorDescarga] = useState('')

  const [precotizaciones, setPrecotizaciones] = useState([])
  const [cargandoPrecot, setCargandoPrecot] = useState(false)
  const [errorPrecot, setErrorPrecot] = useState('')

  // Exportación de inventario (RF-11): formato en curso ('' si ninguno) y error.
  const [exportando, setExportando] = useState('')
  const [errorInventario, setErrorInventario] = useState('')

  const [observaciones, setObservaciones] = useState('')
  const [creando, setCreando] = useState(false)
  const [errorCrear, setErrorCrear] = useState('')
  const [exito, setExito] = useState('')

  // Accesos del enlace público por precotización: id abierta, lista cargada,
  // carga en curso y error. Se consultan bajo demanda (GET .../accesos).
  const [accesosAbiertos, setAccesosAbiertos] = useState(null)
  const [accesos, setAccesos] = useState([])
  const [cargandoAccesos, setCargandoAccesos] = useState(false)
  const [errorAccesos, setErrorAccesos] = useState('')

  // Envío de la precotización al cliente (RF-13). `envioAbierto` guarda el id de
  // la fila BORRADOR con el formulario desplegado; `correoEnvio`/`confirmoEnvio`
  // son los campos del form inline. `enviandoId` es el id en curso (deshabilita
  // controles durante la petición) y `errorEnvio` el mensaje mapeado por código.
  const [envioAbierto, setEnvioAbierto] = useState(null)
  const [correoEnvio, setCorreoEnvio] = useState('')
  const [confirmoEnvio, setConfirmoEnvio] = useState(false)
  const [enviandoId, setEnviandoId] = useState(null)
  const [errorEnvio, setErrorEnvio] = useState('')
  // Id de la fila cuyo envío falló, para mostrar el error solo bajo esa fila.
  const [errorEnvioId, setErrorEnvioId] = useState(null)

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

  // Baja el PDF de QR de las sillas levantadas (RF-05). `descargarQrPdf`
  // propaga el error HTTP tal cual; aquí se mapea a un mensaje legible.
  async function handleDescargarQr() {
    setErrorDescarga('')
    setDescargando(true)
    try {
      const blob = await descargarQrPdf(sillas.map((s) => s.id_silla))
      descargarBlob(blob, 'qr_sillas.pdf')
    } catch (err) {
      setErrorDescarga(mensajeErrorQrPdf(err.response?.status))
    } finally {
      setDescargando(false)
    }
  }

  // Exporta el inventario a CSV o XLSX (RF-11). `exportarInventario` devuelve el
  // Blob y propaga el error HTTP tal cual; `descargarBlob` baja el archivo. El
  // alcance de los datos lo limita el backend por rol; aquí no se filtra nada.
  async function handleExportarInventario(formato) {
    setErrorInventario('')
    setExportando(formato)
    try {
      const blob = await exportarInventario(formato)
      descargarBlob(blob, `inventario.${formato}`)
    } catch (err) {
      setErrorInventario(mensajeErrorInventario(err.response?.status))
    } finally {
      setExportando('')
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
        id_visita: idVisitaSel,
        observaciones,
      })
      setExito(`Precotización #${precot.id_precotizacion} creada en borrador.`)
      setObservaciones('')
      await recargarPrecotizaciones()
    } catch (err) {
      const status = err.response?.status
      if (status === 400 || status === 422) {
        setErrorCrear(err.response?.data?.detail ?? 'Datos inválidos.')
      } else if (status === 403) {
        setErrorCrear('No tienes permiso para crear precotizaciones.')
      } else if (status === 404) {
        setErrorCrear('La visita ya no existe.')
      } else if (status === 409) {
        setErrorCrear('La visita ya tiene una precotización activa.')
      } else {
        setErrorCrear('No se pudo crear la precotización. Inténtalo de nuevo.')
      }
    } finally {
      setCreando(false)
    }
  }

  // Abre o cierra el detalle de accesos de una precotización. Al abrir, consulta
  // GET /precotizaciones/{id}/accesos; una lista vacía significa "sin accesos".
  async function toggleAccesos(idPrecotizacion) {
    if (accesosAbiertos === idPrecotizacion) {
      setAccesosAbiertos(null)
      return
    }
    setAccesosAbiertos(idPrecotizacion)
    setAccesos([])
    setErrorAccesos('')
    setCargandoAccesos(true)
    try {
      setAccesos(await listAccesos(idPrecotizacion))
    } catch {
      setErrorAccesos('No se pudieron cargar los accesos.')
    } finally {
      setCargandoAccesos(false)
    }
  }

  // Abre/cierra el formulario inline de "Enviar al cliente" de una fila BORRADOR
  // y limpia los campos y el error al alternar.
  function toggleEnvio(idPrecotizacion) {
    setErrorEnvio('')
    setErrorEnvioId(null)
    if (envioAbierto === idPrecotizacion) {
      setEnvioAbierto(null)
      return
    }
    setEnvioAbierto(idPrecotizacion)
    setCorreoEnvio('')
    setConfirmoEnvio(false)
  }

  // Envía por primera vez una precotización BORRADOR con el correo capturado y
  // la confirmación de validación del levantamiento (HU-12). Tras el éxito,
  // cierra el formulario y recarga la lista para reflejar ENVIADA y su fecha.
  async function handleEnviar(event, idPrecotizacion) {
    event.preventDefault()
    setErrorEnvio('')
    setErrorEnvioId(null)
    setEnviandoId(idPrecotizacion)
    try {
      await enviarPrecotizacion({
        id: idPrecotizacion,
        correo_cliente: correoEnvio,
        confirmar_validacion: true,
      })
      setEnvioAbierto(null)
      setCorreoEnvio('')
      setConfirmoEnvio(false)
      await recargarPrecotizaciones()
    } catch (err) {
      setErrorEnvio(mensajeErrorEnviar(err.response?.status))
      setErrorEnvioId(idPrecotizacion)
    } finally {
      setEnviandoId(null)
    }
  }

  // Reenvía una precotización ENVIADA reusando el correo guardado, sin pedir de
  // nuevo la confirmación ni cambiar el destinatario. Recarga tras el éxito.
  async function handleReenviar(precotizacion) {
    setErrorEnvio('')
    setErrorEnvioId(null)
    setEnviandoId(precotizacion.id_precotizacion)
    try {
      await enviarPrecotizacion({
        id: precotizacion.id_precotizacion,
        correo_cliente: precotizacion.correo_cliente,
        confirmar_validacion: false,
      })
      await recargarPrecotizaciones()
    } catch (err) {
      setErrorEnvio(mensajeErrorEnviar(err.response?.status))
      setErrorEnvioId(precotizacion.id_precotizacion)
    } finally {
      setEnviandoId(null)
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

      <section className="card">
        <h2>Exportar inventario</h2>
        <p className="state-text">
          Descarga el inventario levantado para analizarlo fuera del sistema. El
          alcance de los datos depende de tu rol.
        </p>

        {errorInventario && (
          <p className="form-error" role="alert">
            {errorInventario}
          </p>
        )}

        <div className="form-actions">
          <button
            className="btn btn--ghost"
            type="button"
            onClick={() => handleExportarInventario('csv')}
            disabled={exportando !== ''}
          >
            {exportando === 'csv' ? 'Exportando…' : 'Exportar CSV'}
          </button>
          <button
            className="btn btn--ghost"
            type="button"
            onClick={() => handleExportarInventario('xlsx')}
            disabled={exportando !== ''}
          >
            {exportando === 'xlsx' ? 'Exportando…' : 'Exportar XLSX'}
          </button>
        </div>
      </section>

      {idVisitaSel && (
        <section className="card">
          <div className="card__encabezado">
            <h2>Sillas levantadas</h2>
            <button
              className="btn btn--ghost"
              type="button"
              onClick={handleDescargarQr}
              disabled={descargando || sillas.length === 0}
            >
              {descargando ? 'Generando PDF…' : 'Descargar QR (PDF)'}
            </button>
          </div>

          {errorDescarga && (
            <p className="form-error" role="alert">
              {errorDescarga}
            </p>
          )}

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
                    <SillaCard
                      key={s.id_silla}
                      silla={s}
                      extra={
                        sugeridos.length > 0 ? (
                          <p className="sillas-lista__componentes">
                            Componentes a cambiar: {sugeridos.join(', ')}.
                          </p>
                        ) : null
                      }
                    />
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
                    <th>Enviada</th>
                    <th>Observaciones</th>
                    <th>Envío</th>
                    <th>Accesos</th>
                  </tr>
                </thead>
                <tbody>
                  {precotizaciones.map((p) => {
                    const abierta = accesosAbiertos === p.id_precotizacion
                    const formEnvioAbierto = envioAbierto === p.id_precotizacion
                    const enviando = enviandoId === p.id_precotizacion
                    return (
                      <Fragment key={p.id_precotizacion}>
                        <tr>
                          <td>{p.id_precotizacion}</td>
                          <td>
                            <span
                              className={
                                p.estado === 'ENVIADA'
                                  ? 'badge badge--ok'
                                  : 'badge badge--off'
                              }
                            >
                              {p.estado}
                            </span>
                          </td>
                          <td>
                            {p.fecha_creacion
                              ? new Date(p.fecha_creacion).toLocaleString()
                              : '—'}
                          </td>
                          <td>
                            {p.fecha_envio
                              ? new Date(p.fecha_envio).toLocaleString()
                              : '—'}
                          </td>
                          <td>{p.observaciones ?? '—'}</td>
                          <td>
                            {p.estado === 'BORRADOR' && (
                              <button
                                className="btn btn--ghost"
                                type="button"
                                onClick={() => toggleEnvio(p.id_precotizacion)}
                                aria-expanded={formEnvioAbierto}
                                disabled={enviando}
                              >
                                {formEnvioAbierto ? 'Cancelar' : 'Enviar al cliente'}
                              </button>
                            )}
                            {p.estado === 'ENVIADA' && (
                              <button
                                className="btn btn--ghost"
                                type="button"
                                onClick={() => handleReenviar(p)}
                                disabled={enviando}
                              >
                                {enviando ? 'Reenviando…' : 'Reenviar'}
                              </button>
                            )}
                            {p.estado !== 'BORRADOR' && p.estado !== 'ENVIADA' && '—'}
                          </td>
                          <td>
                            <button
                              className="btn btn--ghost"
                              type="button"
                              onClick={() => toggleAccesos(p.id_precotizacion)}
                              aria-expanded={abierta}
                            >
                              {abierta ? 'Ocultar' : 'Ver accesos'}
                            </button>
                          </td>
                        </tr>
                        {formEnvioAbierto && (
                          <tr className="data-table__detalle">
                            <td colSpan={7}>
                              <form
                                className="form-grid"
                                onSubmit={(e) => handleEnviar(e, p.id_precotizacion)}
                              >
                                <label className="form-field">
                                  <span className="form-field__label">
                                    Correo del cliente
                                  </span>
                                  <input
                                    className="form-field__input"
                                    type="email"
                                    required
                                    value={correoEnvio}
                                    onChange={(e) => setCorreoEnvio(e.target.value)}
                                    disabled={enviando}
                                    placeholder="cliente@empresa.com"
                                  />
                                </label>

                                <label className="form-field form-field--inline">
                                  <input
                                    type="checkbox"
                                    checked={confirmoEnvio}
                                    onChange={(e) =>
                                      setConfirmoEnvio(e.target.checked)
                                    }
                                    disabled={enviando}
                                  />
                                  <span className="form-field__label">
                                    Confirmo que validé el levantamiento.
                                  </span>
                                </label>

                                {errorEnvio &&
                                  errorEnvioId === p.id_precotizacion && (
                                    <p className="form-error" role="alert">
                                      {errorEnvio}
                                    </p>
                                  )}

                                <div className="form-actions">
                                  <button
                                    className="btn"
                                    type="submit"
                                    disabled={enviando || !confirmoEnvio}
                                  >
                                    {enviando ? 'Enviando…' : 'Enviar al cliente'}
                                  </button>
                                </div>
                              </form>
                            </td>
                          </tr>
                        )}
                        {p.estado === 'ENVIADA' &&
                          errorEnvio &&
                          errorEnvioId === p.id_precotizacion && (
                            <tr className="data-table__detalle">
                              <td colSpan={7}>
                                <p className="form-error" role="alert">
                                  {errorEnvio}
                                </p>
                              </td>
                            </tr>
                          )}
                        {abierta && (
                          <tr className="data-table__detalle">
                            <td colSpan={7}>
                              {cargandoAccesos && (
                                <p className="state-text">Cargando accesos…</p>
                              )}
                              {!cargandoAccesos && errorAccesos && (
                                <p className="form-error" role="alert">
                                  {errorAccesos}
                                </p>
                              )}
                              {!cargandoAccesos && !errorAccesos && accesos.length === 0 && (
                                <p className="state-text">
                                  Sin accesos registrados al enlace público.
                                </p>
                              )}
                              {!cargandoAccesos && !errorAccesos && accesos.length > 0 && (
                                <ul className="accesos-lista">
                                  {accesos.map((a) => (
                                    <li key={a.id_acceso}>
                                      {a.fecha_acceso
                                        ? new Date(a.fecha_acceso).toLocaleString()
                                        : '—'}
                                      {' · '}
                                      {a.navegador ?? 'Navegador desconocido'}
                                      {' · '}
                                      {a.sistema_operativo ?? 'SO desconocido'}
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
