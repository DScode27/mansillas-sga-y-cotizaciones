/* Levantamiento móvil (M4, HU-28, R8).
 *
 * El técnico, en sitio y desde el móvil, levanta las sillas de una visita:
 *   1. Elige la visita. Para un TECNICO (RF-01) se omite el paso de empresa y
 *      se listan directamente sus visitas asignadas (`listVisitas()` sin filtro;
 *      el backend ya acota por `id_tecnico`). Para otros roles se mantiene el
 *      flujo empresa → visita. El filtro por empresa solo acota la vista; el
 *      aislamiento real lo impone el backend según el usuario (R4).
 *   2. Registra una silla con sus datos (empleado, sede, departamento, cargo,
 *      serial) y el estado de los 5 componentes; el `codigo_qr` lo genera la BD.
 *   3. Sube fotos de la silla.
 *   4. Ve el listado de sillas levantadas con la insignia `sugerir_cambio`
 *      (>70% de componentes dañados, según `vista_estado_mantenimiento`).
 *
 * La vista es de una sola columna pensada para viewport móvil y escala a
 * escritorio. Estados de carga, error y vacío en cada listado.
 */
import { useEffect, useMemo, useState } from 'react'
import { listEmpresas } from '../api/empresas'
import { listVisitas } from '../api/visitas'
import {
  COMPONENTES,
  ESTADOS_COMPONENTE,
  calcularSugerirCambio,
  createSilla,
  listSillas,
  uploadFotoSilla,
} from '../api/sillas'
import { descargarQrPdf } from '../api/qr'
import { descargarBlob } from '../utils/descargarBlob'
import { ROLES } from '../auth/roles'
import { useAuth } from '../context/auth-context'

// Mensaje legible por código HTTP al bajar el PDF de QR (RF-05). El cuerpo crudo
// del backend nunca se muestra al usuario.
function mensajeErrorQrPdf(status) {
  if (status === 400) return 'Selecciona al menos una silla.'
  if (status === 403) return 'No tienes permiso para estas sillas.'
  if (status === 404) return 'Alguna silla no existe.'
  return 'No se pudo generar el PDF de QR. Inténtalo de nuevo.'
}
const ESTADO_COMPONENTE_LABEL = {
  BUENO: 'Bueno',
  MANTENIMIENTO: 'Mantenimiento',
  DANADO: 'Dañado',
  NO_APLICA: 'No aplica',
}

function componentesIniciales() {
  // Cada silla arranca con sus 5 componentes en BUENO; el técnico ajusta.
  return COMPONENTES.map((c) => ({
    id_componente: c.id_componente,
    nombre: c.nombre,
    estado: 'BUENO',
    observacion: '',
  }))
}

function formInicial() {
  return {
    id_sede: '',
    id_departamento: '',
    id_empleado: '',
    cargo: '',
    serial_antiguo: '',
    observaciones: '',
    componentes: componentesIniciales(),
  }
}

export default function LevantamientoPage() {
  const { user } = useAuth()
  // RF-01: el técnico no elige empresa; ve directamente sus visitas asignadas.
  const esTecnico = user?.rol === ROLES.TECNICO

  const [empresas, setEmpresas] = useState([])
  // El técnico no carga empresas (RF-01), así que arranca sin estado de carga.
  const [cargandoEmpresas, setCargandoEmpresas] = useState(!esTecnico)
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

  const [form, setForm] = useState(formInicial)
  const [fotos, setFotos] = useState([])
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')
  const [exito, setExito] = useState('')

  const idEmpresaSel = empresaSel ? Number(empresaSel) : null
  const idVisitaSel = visitaSel ? Number(visitaSel) : null

  // Empresas para el selector (mock conmutable). El técnico no usa el selector
  // de empresa (RF-01), así que ni se cargan.
  useEffect(() => {
    if (esTecnico) return
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
  }, [esTecnico])

  // El técnico carga sus visitas al montar (RF-01, sin empresa); los demás al
  // elegir empresa. En ambos casos se limpia la selección de visita antes de
  // recargar. Las llamadas a setState van dentro del flujo asíncrono (como en
  // VisitasPage) para no disparar renders en cascada desde el efecto.
  const cargarVisitasTecnico = esTecnico
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setVisitaSel('')
        setVisitas([])
        if (!cargarVisitasTecnico && !idEmpresaSel) return null
        setCargandoVisitas(true)
        setErrorVisitas('')
        return listVisitas(cargarVisitasTecnico ? undefined : idEmpresaSel)
      })
      .then((data) => {
        if (vigente && data) setVisitas(data)
      })
      .catch(() => {
        if (vigente) setErrorVisitas('No se pudieron cargar las visitas.')
      })
      .finally(() => {
        if (vigente && (cargarVisitasTecnico || idEmpresaSel)) {
          setCargandoVisitas(false)
        }
      })
    return () => {
      vigente = false
    }
  }, [cargarVisitasTecnico, idEmpresaSel])

  // Al elegir visita, se cargan sus sillas y se reinicia el formulario.
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setForm(formInicial())
        setFotos([])
        setErrorForm('')
        setExito('')
        setSillas([])
        if (!idVisitaSel) return null
        setCargandoSillas(true)
        setErrorSillas('')
        return listSillas(idVisitaSel)
      })
      .then((data) => {
        if (vigente && data) setSillas(data)
      })
      .catch(() => {
        if (vigente) setErrorSillas('No se pudieron cargar las sillas.')
      })
      .finally(() => {
        if (vigente && idVisitaSel) setCargandoSillas(false)
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

  function actualizarCampo(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }))
  }

  function actualizarComponente(idComponente, cambios) {
    setForm((prev) => ({
      ...prev,
      componentes: prev.componentes.map((c) =>
        c.id_componente === idComponente ? { ...c, ...cambios } : c,
      ),
    }))
  }

  // Previsualización en vivo de la sugerencia mientras el técnico marca estados.
  const sugerirCambioPreview = useMemo(
    () => calcularSugerirCambio(form.componentes),
    [form.componentes],
  )

  function agregarFotos(event) {
    const nuevas = Array.from(event.target.files ?? []).map((archivo) => ({
      id: `${archivo.name}-${archivo.lastModified}-${archivo.size}`,
      archivo,
      url: URL.createObjectURL(archivo),
    }))
    setFotos((prev) => [...prev, ...nuevas])
    // Permite volver a elegir el mismo archivo si se quitó antes.
    event.target.value = ''
  }

  function quitarFoto(id) {
    setFotos((prev) => {
      const foto = prev.find((f) => f.id === id)
      if (foto) URL.revokeObjectURL(foto.url)
      return prev.filter((f) => f.id !== id)
    })
  }

  // Libera las URLs de previsualización al desmontar la pantalla.
  useEffect(() => {
    return () => {
      fotos.forEach((f) => URL.revokeObjectURL(f.url))
    }
    // Solo al desmontar: no queremos revocar en cada cambio de `fotos`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()
    setErrorForm('')
    setExito('')
    if (!idVisitaSel) {
      setErrorForm('Elige una visita para levantar la silla.')
      return
    }
    setEnviando(true)
    try {
      const silla = await createSilla({
        id_empresa: idEmpresaSel,
        id_visita: idVisitaSel,
        ...form,
      })
      // Las fotos se suben una vez que la silla existe (necesitan su id).
      for (const foto of fotos) {
        await uploadFotoSilla({ id_silla: silla.id_silla, archivo: foto.archivo })
      }
      fotos.forEach((f) => URL.revokeObjectURL(f.url))
      setExito(`Silla ${silla.codigo_qr} registrada.`)
      setForm(formInicial())
      setFotos([])
      await recargarSillas()
    } catch (err) {
      const status = err.response?.status
      if (status === 400) {
        setErrorForm(err.response?.data?.detail ?? 'Datos inválidos.')
      } else if (status === 403) {
        setErrorForm('No tienes permiso para registrar sillas en esta visita.')
      } else if (status === 409) {
        setErrorForm('Ya existe una silla con ese serial en la empresa.')
      } else {
        setErrorForm('No se pudo registrar la silla. Inténtalo de nuevo.')
      }
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="page-stack levantamiento">
      <section className="card">
        <h1>Levantamiento en sitio</h1>
        <p className="state-text">
          {esTecnico
            ? 'Elige una de tus visitas asignadas para registrar sus sillas.'
            : 'Elige la empresa y la visita para registrar sus sillas.'}
        </p>

        {!esTecnico && cargandoEmpresas && (
          <p className="state-text">Cargando empresas…</p>
        )}

        {!esTecnico && !cargandoEmpresas && errorEmpresas && (
          <p className="form-error" role="alert">
            {errorEmpresas}
          </p>
        )}

        {(esTecnico || (!cargandoEmpresas && !errorEmpresas)) && (
          <div className="levantamiento__selectores">
            {!esTecnico && (
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
            )}

            {(esTecnico || idEmpresaSel) && (
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
                      {visitas.length === 0
                        ? esTecnico
                          ? '— No tienes visitas asignadas —'
                          : '— Sin visitas —'
                        : '— Seleccionar —'}
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
          <h2>Registrar silla</h2>
          <form className="form-grid" onSubmit={handleSubmit}>
            <label className="form-field">
              <span className="form-field__label">ID de sede</span>
              <input
                className="form-field__input"
                type="number"
                min={1}
                value={form.id_sede}
                onChange={(e) => actualizarCampo('id_sede', e.target.value)}
                required
                disabled={enviando}
              />
            </label>

            <label className="form-field">
              <span className="form-field__label">ID de departamento</span>
              <input
                className="form-field__input"
                type="number"
                min={1}
                value={form.id_departamento}
                onChange={(e) => actualizarCampo('id_departamento', e.target.value)}
                required
                disabled={enviando}
              />
            </label>

            <label className="form-field">
              <span className="form-field__label">ID de empleado</span>
              <input
                className="form-field__input"
                type="number"
                min={1}
                value={form.id_empleado}
                onChange={(e) => actualizarCampo('id_empleado', e.target.value)}
                required
                disabled={enviando}
              />
            </label>

            <label className="form-field">
              <span className="form-field__label">Cargo del puesto</span>
              <input
                className="form-field__input"
                type="text"
                value={form.cargo}
                onChange={(e) => actualizarCampo('cargo', e.target.value)}
                required
                disabled={enviando}
              />
            </label>

            <label className="form-field">
              <span className="form-field__label">Serial antiguo (opcional)</span>
              <input
                className="form-field__input"
                type="text"
                value={form.serial_antiguo}
                onChange={(e) => actualizarCampo('serial_antiguo', e.target.value)}
                disabled={enviando}
              />
            </label>

            <label className="form-field" style={{ gridColumn: '1 / -1' }}>
              <span className="form-field__label">Observaciones (opcional)</span>
              <textarea
                className="form-field__input"
                rows={2}
                value={form.observaciones}
                onChange={(e) => actualizarCampo('observaciones', e.target.value)}
                disabled={enviando}
              />
            </label>

            <fieldset className="componentes" style={{ gridColumn: '1 / -1' }}>
              <legend className="componentes__legend">Estado de componentes</legend>
              {form.componentes.map((comp) => (
                <div key={comp.id_componente} className="componente">
                  <span className="componente__nombre">{comp.nombre}</span>
                  <div
                    className="componente__estados"
                    role="radiogroup"
                    aria-label={`Estado de ${comp.nombre}`}
                  >
                    {ESTADOS_COMPONENTE.map((estado) => (
                      <label key={estado} className="componente__opcion">
                        <input
                          type="radio"
                          name={`comp-${comp.id_componente}`}
                          value={estado}
                          checked={comp.estado === estado}
                          onChange={() =>
                            actualizarComponente(comp.id_componente, { estado })
                          }
                          disabled={enviando}
                        />
                        <span>{ESTADO_COMPONENTE_LABEL[estado]}</span>
                      </label>
                    ))}
                  </div>
                  <input
                    className="form-field__input componente__obs"
                    type="text"
                    placeholder="Observación (opcional)"
                    value={comp.observacion}
                    onChange={(e) =>
                      actualizarComponente(comp.id_componente, {
                        observacion: e.target.value,
                      })
                    }
                    disabled={enviando}
                  />
                </div>
              ))}
              {sugerirCambioPreview && (
                <p className="componentes__sugerencia" role="status">
                  Más del 70% de los componentes están dañados: se sugerirá cambio.
                </p>
              )}
            </fieldset>

            <div className="fotos" style={{ gridColumn: '1 / -1' }}>
              <span className="form-field__label">Fotos de la silla</span>
              <input
                type="file"
                accept="image/*"
                capture="environment"
                multiple
                onChange={agregarFotos}
                disabled={enviando}
              />
              {fotos.length > 0 && (
                <ul className="fotos__lista">
                  {fotos.map((f) => (
                    <li key={f.id} className="fotos__item">
                      <img src={f.url} alt={f.archivo.name} className="fotos__thumb" />
                      <button
                        type="button"
                        className="btn btn--ghost fotos__quitar"
                        onClick={() => quitarFoto(f.id)}
                        disabled={enviando}
                      >
                        Quitar
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {errorForm && (
              <p className="form-error" role="alert">
                {errorForm}
              </p>
            )}
            {exito && (
              <p className="form-success" role="status">
                {exito}
              </p>
            )}

            <div className="form-actions">
              <button className="btn" type="submit" disabled={enviando}>
                {enviando ? 'Registrando…' : 'Registrar silla'}
              </button>
            </div>
          </form>
        </section>
      )}

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
            <p className="state-text">Esta visita aún no tiene sillas registradas.</p>
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
                  <p className="sillas-lista__cargo">{s.cargo}</p>
                  {(s.fotos?.length ?? 0) > 0 && (
                    <span className="sillas-lista__fotos">
                      {s.fotos.length} foto{s.fotos.length === 1 ? '' : 's'}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
