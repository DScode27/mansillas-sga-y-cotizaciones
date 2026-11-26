/* Visitas (M3, R7, RF-01).
 *
 * Una visita se asocia a empresa, sede, comercial y técnico, y organiza el
 * levantamiento. La pantalla tiene dos partes:
 *   1. Alta (solo COMERCIAL_MANSILLAS): elige empresa, sede y técnico, y
 *      programa la visita. El comercial es el usuario autenticado.
 *   2. Listado filtrado por la empresa elegida. ADMIN_CLIENTE entra en modo
 *      consulta (ve el listado por empresa, no el alta).
 *
 * TECNICO — "Mis visitas" (RF-01): se omite el paso de elegir empresa y se
 * listan directamente sus visitas asignadas con `listVisitas()` sin filtro; el
 * backend ya acota por `id_tecnico`. Estado vacío: "no tienes visitas
 * asignadas". Para COMERCIAL_MANSILLAS / ADMIN_CLIENTE se mantiene el flujo por
 * empresa.
 *
 * Empresas y visitas son recursos de otros devs: se consumen con mocks
 * conmutables (src/api). Los técnicos se piden a mi endpoint propio /usuarios
 * (existe) y se filtran por rol; si no se pueden cargar, se cae a un input de
 * id para no bloquear el alta. El aislamiento real por empresa lo impone el
 * backend (R4); aquí el selector solo acota la vista. Estados de carga, error y
 * vacío en cada listado.
 */
import { useEffect, useMemo, useState } from 'react'
import { listEmpresas } from '../api/empresas'
import { listUsuarios } from '../api/usuarios'
import { listSedes } from '../api/sedes'
import { listVisitas, createVisita, updateVisita, deleteVisita } from '../api/visitas'
import { ROLES } from '../auth/roles'
import { useAuth } from '../context/auth-context'

const ESTADO_LABEL = {
  PROGRAMADA: 'Programada',
  EN_CURSO: 'En curso',
  FINALIZADA: 'Finalizada',
  CANCELADA: 'Cancelada',
}

// Estados que el comercial puede asignar desde el listado (PUT /visitas/{id}).
const ESTADOS_VISITA = ['PROGRAMADA', 'EN_CURSO', 'FINALIZADA', 'CANCELADA']

function formInicial() {
  return {
    id_sede: '',
    id_tecnico: '',
    fecha_programada: '',
    cantidad_estimada: '',
    observaciones: '',
  }
}

export default function VisitasPage() {
  const { user, hasRole } = useAuth()
  const puedeCrear = hasRole([ROLES.COMERCIAL_MANSILLAS])
  // RF-01: el técnico no elige empresa; ve directamente sus visitas asignadas.
  const esTecnico = user?.rol === ROLES.TECNICO

  const [empresas, setEmpresas] = useState([])
  // El técnico no carga empresas (RF-01), así que arranca sin estado de carga.
  const [cargandoEmpresas, setCargandoEmpresas] = useState(!esTecnico)
  const [errorEmpresas, setErrorEmpresas] = useState('')
  const [empresaSel, setEmpresaSel] = useState('')

  const [tecnicos, setTecnicos] = useState([])
  const [tecnicosDisponibles, setTecnicosDisponibles] = useState(true)

  // Sedes de la empresa elegida, para el selector por nombre del alta (RF-01).
  // Si el listado falla, se degrada a input de ID (como los técnicos).
  const [sedes, setSedes] = useState([])
  const [sedesDisponibles, setSedesDisponibles] = useState(true)
  const [cargandoSedes, setCargandoSedes] = useState(false)

  const [visitas, setVisitas] = useState([])
  const [cargandoVisitas, setCargandoVisitas] = useState(false)
  const [errorVisitas, setErrorVisitas] = useState('')

  const [form, setForm] = useState(formInicial)
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')
  const [exito, setExito] = useState('')

  // id_visita cuya acción (cambio de estado o borrado) está en curso, para
  // deshabilitar sus controles. Y mensajes de resultado del listado.
  const [accionEnCurso, setAccionEnCurso] = useState(null)
  const [errorAccion, setErrorAccion] = useState('')

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

  // Técnicos para asignar (endpoint propio /usuarios). Solo tiene sentido
  // cargarlos para quien puede crear visitas; si falla, se usa un input de id.
  useEffect(() => {
    if (!puedeCrear) return
    let vigente = true
    listUsuarios()
      .then((data) => {
        if (!vigente) return
        setTecnicos(data.filter((u) => u.rol === ROLES.TECNICO && u.activo))
      })
      .catch(() => {
        if (vigente) setTecnicosDisponibles(false)
      })
    return () => {
      vigente = false
    }
  }, [puedeCrear])

  const idEmpresaSel = empresaSel ? Number(empresaSel) : null
  // El listado se muestra cuando hay una empresa elegida o cuando es técnico
  // (que ve sus visitas sin elegir empresa, RF-01).
  const mostrarListado = esTecnico || Boolean(idEmpresaSel)

  // Sedes de la empresa elegida para el selector por nombre del alta. Solo se
  // cargan para quien puede crear visitas y con una empresa elegida; al cambiar
  // de empresa se limpia la sede del formulario para no arrastrar una ajena. Si
  // el listado falla, se marca no disponible y la UI cae a input de ID.
  useEffect(() => {
    let vigente = true
    // Los setState van dentro del flujo asíncrono (como el resto de efectos de
    // esta pantalla) para no disparar renders en cascada desde el efecto.
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setSedes([])
        setSedesDisponibles(true)
        setForm((prev) => ({ ...prev, id_sede: '' }))
        if (!puedeCrear || !idEmpresaSel) {
          setCargandoSedes(false)
          return null
        }
        setCargandoSedes(true)
        return listSedes(idEmpresaSel)
      })
      .then((data) => {
        if (vigente && data) setSedes(data)
      })
      .catch(() => {
        if (vigente) setSedesDisponibles(false)
      })
      .finally(() => {
        if (vigente && puedeCrear && idEmpresaSel) setCargandoSedes(false)
      })
    return () => {
      vigente = false
    }
  }, [puedeCrear, idEmpresaSel])

  async function cargarVisitas() {
    if (!mostrarListado) {
      setVisitas([])
      return
    }
    setCargandoVisitas(true)
    setErrorVisitas('')
    try {
      // El técnico pide sin filtro de empresa; el backend ya acota por técnico.
      const data = await listVisitas(esTecnico ? undefined : idEmpresaSel)
      setVisitas(data)
    } catch {
      setErrorVisitas('No se pudieron cargar las visitas.')
    } finally {
      setCargandoVisitas(false)
    }
  }

  // Recarga el listado al cambiar de empresa (o al montar, si es técnico). Sin
  // empresa y sin ser técnico no se dispara ni se muestra nada (la sección del
  // listado está acotada por `mostrarListado`), así que el estado anterior no
  // llega a verse. Las llamadas a setState van dentro del flujo asíncrono para
  // no disparar renders en cascada desde el efecto.
  useEffect(() => {
    if (!mostrarListado) return
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return
        setCargandoVisitas(true)
        setErrorVisitas('')
        return listVisitas(esTecnico ? undefined : idEmpresaSel)
      })
      .then((data) => {
        if (vigente && data) setVisitas(data)
      })
      .catch(() => {
        if (vigente) setErrorVisitas('No se pudieron cargar las visitas.')
      })
      .finally(() => {
        if (vigente) setCargandoVisitas(false)
      })
    return () => {
      vigente = false
    }
  }, [mostrarListado, esTecnico, idEmpresaSel])

  function actualizarCampo(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setErrorForm('')
    setExito('')
    if (!idEmpresaSel) {
      setErrorForm('Elige una empresa para la visita.')
      return
    }
    setEnviando(true)
    try {
      await createVisita({
        id_empresa: idEmpresaSel,
        id_comercial: user.id_usuario,
        ...form,
      })
      setExito('Visita programada.')
      setForm(formInicial())
      await cargarVisitas()
    } catch (err) {
      const status = err.response?.status
      if (status === 400) {
        setErrorForm(err.response?.data?.detail ?? 'Datos inválidos.')
      } else if (status === 403) {
        setErrorForm('No tienes permiso para programar visitas.')
      } else {
        setErrorForm('No se pudo programar la visita. Inténtalo de nuevo.')
      }
    } finally {
      setEnviando(false)
    }
  }

  // Cambia el estado de una visita (PUT /visitas/{id}). Actualiza la fila en
  // sitio para no recargar todo el listado.
  async function handleCambiarEstado(idVisita, estado) {
    setErrorAccion('')
    setAccionEnCurso(idVisita)
    try {
      const actualizada = await updateVisita(idVisita, { estado })
      setVisitas((prev) =>
        prev.map((v) => (v.id_visita === idVisita ? { ...v, ...actualizada } : v)),
      )
    } catch (err) {
      const status = err.response?.status
      if (status === 403) {
        setErrorAccion('No tienes permiso para modificar visitas.')
      } else if (status === 404) {
        setErrorAccion('La visita ya no existe; recarga el listado.')
      } else {
        setErrorAccion('No se pudo actualizar la visita. Inténtalo de nuevo.')
      }
    } finally {
      setAccionEnCurso(null)
    }
  }

  // Elimina una visita (DELETE /visitas/{id}). El backend responde 409 si la
  // visita tiene sillas registradas; se avisa sin borrarla.
  async function handleEliminar(idVisita) {
    setErrorAccion('')
    if (!window.confirm(`¿Eliminar la visita #${idVisita}? Esta acción no se puede deshacer.`)) {
      return
    }
    setAccionEnCurso(idVisita)
    try {
      await deleteVisita(idVisita)
      setVisitas((prev) => prev.filter((v) => v.id_visita !== idVisita))
    } catch (err) {
      const status = err.response?.status
      if (status === 409) {
        setErrorAccion('No se puede eliminar: la visita tiene sillas registradas.')
      } else if (status === 403) {
        setErrorAccion('No tienes permiso para eliminar visitas.')
      } else if (status === 404) {
        setErrorAccion('La visita ya no existe; recarga el listado.')
      } else {
        setErrorAccion('No se pudo eliminar la visita. Inténtalo de nuevo.')
      }
    } finally {
      setAccionEnCurso(null)
    }
  }

  const tecnicosPorId = useMemo(() => {
    const mapa = new Map()
    tecnicos.forEach((t) => mapa.set(t.id_usuario, t.nombre))
    return mapa
  }, [tecnicos])

  return (
    <div className="page-stack">
      <section className="card">
        <h1>{esTecnico ? 'Mis visitas' : 'Visitas'}</h1>
        {esTecnico ? (
          <p className="state-text">Estas son las visitas que tienes asignadas.</p>
        ) : (
          <p className="state-text">
            Elige una empresa para ver sus visitas
            {puedeCrear ? ' o programar una nueva.' : '.'}
          </p>
        )}

        {!esTecnico && cargandoEmpresas && (
          <p className="state-text">Cargando empresas…</p>
        )}

        {!esTecnico && !cargandoEmpresas && errorEmpresas && (
          <p className="form-error" role="alert">
            {errorEmpresas}
          </p>
        )}

        {!esTecnico && !cargandoEmpresas && !errorEmpresas && (
          <label className="form-field" style={{ maxWidth: '22rem', marginTop: '0.75rem' }}>
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
      </section>

      {puedeCrear && idEmpresaSel && (
        <section className="card">
          <h2>Programar visita</h2>
          <form className="form-grid" onSubmit={handleSubmit}>
            <label className="form-field">
              <span className="form-field__label">Sede</span>
              {cargandoSedes ? (
                <span className="state-text">Cargando sedes…</span>
              ) : sedesDisponibles ? (
                <select
                  className="form-field__input"
                  value={form.id_sede}
                  onChange={(e) => actualizarCampo('id_sede', e.target.value)}
                  required
                  disabled={enviando || sedes.length === 0}
                >
                  <option value="">
                    {sedes.length === 0 ? '— Sin sedes —' : '— Seleccionar —'}
                  </option>
                  {sedes.map((s) => (
                    <option key={s.id_sede} value={s.id_sede}>
                      {s.nombre}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="form-field__input"
                  type="number"
                  min={1}
                  value={form.id_sede}
                  onChange={(e) => actualizarCampo('id_sede', e.target.value)}
                  required
                  disabled={enviando}
                  placeholder="ID de sede"
                />
              )}
            </label>

            <label className="form-field">
              <span className="form-field__label">Técnico</span>
              {tecnicosDisponibles ? (
                <select
                  className="form-field__input"
                  value={form.id_tecnico}
                  onChange={(e) => actualizarCampo('id_tecnico', e.target.value)}
                  required
                  disabled={enviando || tecnicos.length === 0}
                >
                  <option value="">— Seleccionar —</option>
                  {tecnicos.map((t) => (
                    <option key={t.id_usuario} value={t.id_usuario}>
                      {t.nombre}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="form-field__input"
                  type="number"
                  min={1}
                  value={form.id_tecnico}
                  onChange={(e) => actualizarCampo('id_tecnico', e.target.value)}
                  required
                  disabled={enviando}
                  placeholder="ID del técnico"
                />
              )}
            </label>

            <label className="form-field">
              <span className="form-field__label">Fecha programada (opcional)</span>
              <input
                className="form-field__input"
                type="datetime-local"
                value={form.fecha_programada}
                onChange={(e) => actualizarCampo('fecha_programada', e.target.value)}
                disabled={enviando}
              />
            </label>

            <label className="form-field">
              <span className="form-field__label">Cantidad estimada de sillas</span>
              <input
                className="form-field__input"
                type="number"
                min={0}
                value={form.cantidad_estimada}
                onChange={(e) => actualizarCampo('cantidad_estimada', e.target.value)}
                required
                disabled={enviando}
              />
            </label>

            <label className="form-field" style={{ gridColumn: '1 / -1' }}>
              <span className="form-field__label">Observaciones (opcional)</span>
              <textarea
                className="form-field__input"
                rows={3}
                value={form.observaciones}
                onChange={(e) => actualizarCampo('observaciones', e.target.value)}
                disabled={enviando}
              />
            </label>

            {!sedesDisponibles && (
              <p className="form-notice" role="status">
                No se pudo cargar la lista de sedes; ingresa el ID de la sede.
              </p>
            )}

            {!tecnicosDisponibles && (
              <p className="form-notice" role="status">
                No se pudo cargar la lista de técnicos; ingresa el ID del técnico.
              </p>
            )}

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
                {enviando ? 'Programando…' : 'Programar visita'}
              </button>
            </div>
          </form>
        </section>
      )}

      {mostrarListado && (
        <section className="card">
          <h2>{esTecnico ? 'Mis visitas asignadas' : 'Visitas de la empresa'}</h2>

          {cargandoVisitas && <p className="state-text">Cargando visitas…</p>}

          {!cargandoVisitas && errorVisitas && (
            <div className="state-error" role="alert">
              <p>{errorVisitas}</p>
              <button className="btn btn--ghost" type="button" onClick={cargarVisitas}>
                Reintentar
              </button>
            </div>
          )}

          {!cargandoVisitas && !errorVisitas && visitas.length === 0 && (
            <p className="state-text">
              {esTecnico
                ? 'No tienes visitas asignadas.'
                : 'Esta empresa aún no tiene visitas.'}
            </p>
          )}

          {!cargandoVisitas && !errorVisitas && visitas.length > 0 && (
            <>
              {errorAccion && (
                <p className="form-error" role="alert">
                  {errorAccion}
                </p>
              )}
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Sede</th>
                      <th>Técnico</th>
                      <th>Fecha programada</th>
                      <th>Cant. estimada</th>
                      <th>Estado</th>
                      <th>Observaciones</th>
                      {puedeCrear && <th>Acciones</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {visitas.map((v) => {
                      const ocupada = accionEnCurso === v.id_visita
                      return (
                        <tr key={v.id_visita}>
                          <td>{v.id_sede}</td>
                          <td>{tecnicosPorId.get(v.id_tecnico) ?? v.id_tecnico}</td>
                          <td>
                            {v.fecha_programada
                              ? new Date(v.fecha_programada).toLocaleString()
                              : '—'}
                          </td>
                          <td>{v.cantidad_estimada}</td>
                          <td>
                            {puedeCrear ? (
                              <select
                                className="form-field__input"
                                aria-label={`Estado de la visita ${v.id_visita}`}
                                value={v.estado}
                                onChange={(e) =>
                                  handleCambiarEstado(v.id_visita, e.target.value)
                                }
                                disabled={ocupada}
                              >
                                {ESTADOS_VISITA.map((estado) => (
                                  <option key={estado} value={estado}>
                                    {ESTADO_LABEL[estado]}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              (ESTADO_LABEL[v.estado] ?? v.estado)
                            )}
                          </td>
                          <td>{v.observaciones ?? '—'}</td>
                          {puedeCrear && (
                            <td>
                              <button
                                className="btn btn--ghost"
                                type="button"
                                onClick={() => handleEliminar(v.id_visita)}
                                disabled={ocupada}
                              >
                                {ocupada ? '…' : 'Eliminar'}
                              </button>
                            </td>
                          )}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  )
}
