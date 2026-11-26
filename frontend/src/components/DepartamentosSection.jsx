/* Registrar departamento dentro de una sede (catálogo organizacional).
 *
 * Desplegables encadenados empresa → sede: el comercial elige empresa (de las
 * props) y, según esa empresa, elige una de sus sedes; no digita ningún ID. El
 * formulario de departamento solo se habilita cuando hay empresa Y sede
 * elegidas. El backend (`POST /sedes/{id_sede}/departamentos`) deriva la empresa
 * de la sede, impone el RBAC y la unicidad del nombre por sede.
 *
 * La prop `refrescoSedes` (un contador que cambia el padre al crear una sede)
 * fuerza a recargar las sedes de la empresa elegida, para que una sede recién
 * creada aparezca aquí sin recargar la página. Estados de carga/error/éxito
 * coherentes con el resto de la página.
 */
import { useEffect, useState } from 'react'
import { createDepartamento, listDepartamentos } from '../api/departamentos'
import { listSedes } from '../api/sedes'

export default function DepartamentosSection({ empresas, refrescoSedes }) {
  const [empresaSel, setEmpresaSel] = useState('')
  const [sedeSel, setSedeSel] = useState('')
  const [nombre, setNombre] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')
  const [exito, setExito] = useState('')

  const [sedes, setSedes] = useState([])
  const [cargandoSedes, setCargandoSedes] = useState(false)
  const [errorSedes, setErrorSedes] = useState('')

  const [departamentos, setDepartamentos] = useState([])
  const [cargandoDeptos, setCargandoDeptos] = useState(false)
  const [errorDeptos, setErrorDeptos] = useState('')

  const idEmpresaSel = empresaSel ? Number(empresaSel) : null
  const idSedeSel = sedeSel ? Number(sedeSel) : null

  // Encadenado empresa → sedes. Al cambiar de empresa (o cuando el padre señala
  // que se creó una sede, vía `refrescoSedes`) se recargan las sedes y se limpia
  // la sede elegida para no arrastrar una de otra empresa.
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setSedes([])
        setSedeSel('')
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
  }, [idEmpresaSel, refrescoSedes])

  // Encadenado sede → departamentos (listado bajo el formulario).
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setDepartamentos([])
        setErrorDeptos('')
        if (!idSedeSel) {
          setCargandoDeptos(false)
          return null
        }
        setCargandoDeptos(true)
        return listDepartamentos(idSedeSel)
      })
      .then((data) => {
        if (vigente && data) setDepartamentos(data)
      })
      .catch(() => {
        if (vigente) setErrorDeptos('No se pudieron cargar los departamentos.')
      })
      .finally(() => {
        if (vigente && idSedeSel) setCargandoDeptos(false)
      })
    return () => {
      vigente = false
    }
  }, [idSedeSel])

  async function recargarDepartamentos() {
    if (!idSedeSel) return
    setCargandoDeptos(true)
    setErrorDeptos('')
    try {
      setDepartamentos(await listDepartamentos(idSedeSel))
    } catch {
      setErrorDeptos('No se pudieron cargar los departamentos.')
    } finally {
      setCargandoDeptos(false)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setErrorForm('')
    setExito('')
    if (!idSedeSel) {
      setErrorForm('Elige una empresa y una sede para el departamento.')
      return
    }
    setEnviando(true)
    try {
      const depto = await createDepartamento(idSedeSel, { nombre })
      setExito(`Departamento "${depto.nombre}" creado.`)
      setNombre('')
      await recargarDepartamentos()
    } catch (err) {
      const status = err.response?.status
      if (status === 409) {
        setErrorForm('Ya existe un departamento con ese nombre en la sede.')
      } else if (status === 404) {
        setErrorForm('La sede ya no existe; recarga el listado.')
      } else if (status === 403) {
        setErrorForm('No tienes permiso para registrar departamentos.')
      } else if (status === 400 || status === 422) {
        setErrorForm('Datos inválidos.')
      } else {
        setErrorForm('No se pudo crear el departamento. Inténtalo de nuevo.')
      }
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section className="card">
      <h2>Registrar departamento</h2>
      <p className="state-text">
        Elige la empresa y luego la sede a la que pertenece el departamento.
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
          <span className="form-field__label">Sede</span>
          {cargandoSedes ? (
            <span className="state-text">Cargando sedes…</span>
          ) : errorSedes ? (
            <span className="form-error" role="alert">
              {errorSedes}
            </span>
          ) : (
            <select
              className="form-field__input"
              value={sedeSel}
              onChange={(e) => setSedeSel(e.target.value)}
              required
              disabled={enviando || !idEmpresaSel || sedes.length === 0}
            >
              <option value="">
                {!idEmpresaSel
                  ? '— Elige una empresa primero —'
                  : sedes.length === 0
                    ? '— Sin sedes —'
                    : '— Seleccionar —'}
              </option>
              {sedes.map((s) => (
                <option key={s.id_sede} value={s.id_sede}>
                  {s.nombre}
                </option>
              ))}
            </select>
          )}
        </label>

        <label className="form-field">
          <span className="form-field__label">Nombre</span>
          <input
            className="form-field__input"
            type="text"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            required
            disabled={enviando || !idSedeSel}
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
          <button className="btn" type="submit" disabled={enviando || !idSedeSel}>
            {enviando ? 'Guardando…' : 'Registrar departamento'}
          </button>
        </div>
      </form>

      {idSedeSel && (
        <div style={{ marginTop: '1rem' }}>
          <h3>Departamentos de la sede</h3>

          {cargandoDeptos && (
            <p className="state-text">Cargando departamentos…</p>
          )}

          {!cargandoDeptos && errorDeptos && (
            <div className="state-error" role="alert">
              <p>{errorDeptos}</p>
              <button
                className="btn btn--ghost"
                type="button"
                onClick={recargarDepartamentos}
              >
                Reintentar
              </button>
            </div>
          )}

          {!cargandoDeptos && !errorDeptos && departamentos.length === 0 && (
            <p className="state-text">Esta sede aún no tiene departamentos.</p>
          )}

          {!cargandoDeptos && !errorDeptos && departamentos.length > 0 && (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Nombre</th>
                  </tr>
                </thead>
                <tbody>
                  {departamentos.map((d) => (
                    <tr key={d.id_departamento}>
                      <td>{d.nombre}</td>
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
