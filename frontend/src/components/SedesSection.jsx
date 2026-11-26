/* Registrar sede dentro de una empresa (catálogo organizacional).
 *
 * El comercial elige una empresa de un desplegable (no digita su ID) y registra
 * la sede con nombre/dirección/ciudad. El backend (`POST /empresas/{id}/sedes`)
 * impone el RBAC y la unicidad del nombre por empresa. Tras crear, se refresca
 * el listado de sedes de la empresa elegida y se avisa al padre (`onSedeCreada`)
 * para que otras secciones dependientes (p. ej. departamentos) se enteren.
 *
 * Patrón de estados (carga/error/éxito) y degradación coherentes con
 * `EmpresasPage`/`EmpleadosSection`. Las empresas llegan por props desde la
 * página, que es la dueña de ese listado.
 */
import { useEffect, useState } from 'react'
import { createSede, listSedes } from '../api/sedes'

const SEDE_INICIAL = { nombre: '', direccion: '', ciudad: '' }

export default function SedesSection({ empresas, onSedeCreada }) {
  const [empresaSel, setEmpresaSel] = useState('')
  const [form, setForm] = useState(SEDE_INICIAL)
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')
  const [exito, setExito] = useState('')

  const [sedes, setSedes] = useState([])
  const [cargandoSedes, setCargandoSedes] = useState(false)
  const [errorSedes, setErrorSedes] = useState('')

  const idEmpresaSel = empresaSel ? Number(empresaSel) : null

  // Carga las sedes de la empresa elegida para mostrarlas bajo el formulario.
  // Los setState van dentro del flujo asíncrono para no encadenar renders.
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setSedes([])
        setErrorSedes('')
        setExito('')
        if (!idEmpresaSel) {
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
        if (vigente) setErrorSedes('No se pudieron cargar las sedes.')
      })
      .finally(() => {
        if (vigente && idEmpresaSel) setCargandoSedes(false)
      })
    return () => {
      vigente = false
    }
  }, [idEmpresaSel])

  function actualizarCampo(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }))
  }

  async function recargarSedes() {
    if (!idEmpresaSel) return
    setCargandoSedes(true)
    setErrorSedes('')
    try {
      setSedes(await listSedes(idEmpresaSel))
    } catch {
      setErrorSedes('No se pudieron cargar las sedes.')
    } finally {
      setCargandoSedes(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setErrorForm('')
    setExito('')
    if (!idEmpresaSel) {
      setErrorForm('Elige una empresa para la sede.')
      return
    }
    setEnviando(true)
    try {
      const sede = await createSede(idEmpresaSel, form)
      setExito(`Sede "${sede.nombre}" creada.`)
      setForm(SEDE_INICIAL)
      await recargarSedes()
      onSedeCreada?.(sede)
    } catch (err) {
      const status = err.response?.status
      if (status === 409) {
        setErrorForm('Ya existe una sede con ese nombre en la empresa.')
      } else if (status === 404) {
        setErrorForm('La empresa ya no existe; recarga el listado.')
      } else if (status === 403) {
        setErrorForm('No tienes permiso para registrar sedes.')
      } else if (status === 400 || status === 422) {
        setErrorForm('Datos inválidos.')
      } else {
        setErrorForm('No se pudo crear la sede. Inténtalo de nuevo.')
      }
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section className="card">
      <h2>Registrar sede</h2>
      <p className="state-text">
        Elige la empresa a la que pertenece la sede.
      </p>

      <form className="form-grid" onSubmit={handleSubmit}>
        <label className="form-field">
          <span className="form-field__label">Empresa</span>
          <select
            className="form-field__input"
            value={empresaSel}
            onChange={(e) => setEmpresaSel(e.target.value)}
            required
            disabled={enviando || empresas.length === 0}
          >
            <option value="">
              {empresas.length === 0 ? '— Sin empresas —' : '— Seleccionar —'}
            </option>
            {empresas.map((e) => (
              <option key={e.id_empresa} value={e.id_empresa}>
                {e.nombre}
              </option>
            ))}
          </select>
        </label>

        <label className="form-field">
          <span className="form-field__label">Nombre</span>
          <input
            className="form-field__input"
            type="text"
            value={form.nombre}
            onChange={(e) => actualizarCampo('nombre', e.target.value)}
            required
            disabled={enviando}
          />
        </label>

        <label className="form-field">
          <span className="form-field__label">Dirección (opcional)</span>
          <input
            className="form-field__input"
            type="text"
            value={form.direccion}
            onChange={(e) => actualizarCampo('direccion', e.target.value)}
            disabled={enviando}
          />
        </label>

        <label className="form-field">
          <span className="form-field__label">Ciudad (opcional)</span>
          <input
            className="form-field__input"
            type="text"
            value={form.ciudad}
            onChange={(e) => actualizarCampo('ciudad', e.target.value)}
            disabled={enviando}
          />
        </label>

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
            {enviando ? 'Guardando…' : 'Registrar sede'}
          </button>
        </div>
      </form>

      {idEmpresaSel && (
        <div style={{ marginTop: '1rem' }}>
          <h3>Sedes de la empresa</h3>

          {cargandoSedes && <p className="state-text">Cargando sedes…</p>}

          {!cargandoSedes && errorSedes && (
            <div className="state-error" role="alert">
              <p>{errorSedes}</p>
              <button
                className="btn btn--ghost"
                type="button"
                onClick={recargarSedes}
              >
                Reintentar
              </button>
            </div>
          )}

          {!cargandoSedes && !errorSedes && sedes.length === 0 && (
            <p className="state-text">Esta empresa aún no tiene sedes.</p>
          )}

          {!cargandoSedes && !errorSedes && sedes.length > 0 && (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>Dirección</th>
                    <th>Ciudad</th>
                  </tr>
                </thead>
                <tbody>
                  {sedes.map((s) => (
                    <tr key={s.id_sede}>
                      <td>{s.nombre}</td>
                      <td>{s.direccion ?? '—'}</td>
                      <td>{s.ciudad ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
