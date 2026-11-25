/* Alta de empresa y empleados (M2, R6).
 *
 * Pensada para COMERCIAL_MANSILLAS (la ruta la acota RequireRole; el backend
 * impone el RBAC). Tres bloques:
 *   1. Alta de empresa: pantalla mínima del MVP (nombre + NIT únicos).
 *   2. Selección de empresa para trabajar sus empleados.
 *   3. Empleados de esa empresa: alta manual + importación por Excel con
 *      previsualización antes de registrar la carga (`carga_excel`).
 *
 * Empresas y empleados son recursos de otros devs: se consumen con mocks
 * conmutables (src/api). Estados de carga, error y vacío en cada listado.
 */
import { useEffect, useState } from 'react'
import { createEmpresa, listEmpresas } from '../api/empresas'
import EmpleadosSection from '../components/EmpleadosSection'

const EMPRESA_INICIAL = { nombre: '', nit: '', correo: '', telefono: '' }

export default function EmpresasPage() {
  const [empresas, setEmpresas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [errorLista, setErrorLista] = useState('')

  const [form, setForm] = useState(EMPRESA_INICIAL)
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')
  const [exito, setExito] = useState('')

  const [empresaSel, setEmpresaSel] = useState('')

  async function cargarEmpresas() {
    setCargando(true)
    setErrorLista('')
    try {
      const data = await listEmpresas()
      setEmpresas(data)
    } catch {
      setErrorLista('No se pudieron cargar las empresas.')
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => {
    let vigente = true
    listEmpresas()
      .then((data) => {
        if (vigente) setEmpresas(data)
      })
      .catch(() => {
        if (vigente) setErrorLista('No se pudieron cargar las empresas.')
      })
      .finally(() => {
        if (vigente) setCargando(false)
      })
    return () => {
      vigente = false
    }
  }, [])

  function actualizarCampo(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setErrorForm('')
    setExito('')
    setEnviando(true)
    try {
      const empresa = await createEmpresa(form)
      setExito(`Empresa "${empresa.nombre}" creada.`)
      setForm(EMPRESA_INICIAL)
      await cargarEmpresas()
      setEmpresaSel(String(empresa.id_empresa))
    } catch (err) {
      const status = err.response?.status
      if (status === 409) {
        setErrorForm('Ya existe una empresa con ese NIT.')
      } else if (status === 400) {
        setErrorForm(err.response?.data?.detail ?? 'Datos inválidos.')
      } else {
        setErrorForm('No se pudo crear la empresa. Inténtalo de nuevo.')
      }
    } finally {
      setEnviando(false)
    }
  }

  const empresaActiva = empresas.find(
    (e) => String(e.id_empresa) === empresaSel,
  )

  return (
    <div className="page-stack">
      <section className="card">
        <h1>Registrar empresa</h1>
        <form className="form-grid" onSubmit={handleSubmit}>
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
            <span className="form-field__label">NIT</span>
            <input
              className="form-field__input"
              type="text"
              value={form.nit}
              onChange={(e) => actualizarCampo('nit', e.target.value)}
              required
              disabled={enviando}
            />
          </label>

          <label className="form-field">
            <span className="form-field__label">Correo (opcional)</span>
            <input
              className="form-field__input"
              type="email"
              value={form.correo}
              onChange={(e) => actualizarCampo('correo', e.target.value)}
              disabled={enviando}
            />
          </label>

          <label className="form-field">
            <span className="form-field__label">Teléfono (opcional)</span>
            <input
              className="form-field__input"
              type="tel"
              value={form.telefono}
              onChange={(e) => actualizarCampo('telefono', e.target.value)}
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
              {enviando ? 'Guardando…' : 'Registrar empresa'}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h2>Empresas</h2>

        {cargando && <p className="state-text">Cargando empresas…</p>}

        {!cargando && errorLista && (
          <div className="state-error" role="alert">
            <p>{errorLista}</p>
            <button className="btn btn--ghost" type="button" onClick={cargarEmpresas}>
              Reintentar
            </button>
          </div>
        )}

        {!cargando && !errorLista && empresas.length === 0 && (
          <p className="state-text">Aún no hay empresas registradas.</p>
        )}

        {!cargando && !errorLista && empresas.length > 0 && (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>NIT</th>
                  <th>Correo</th>
                  <th>Teléfono</th>
                </tr>
              </thead>
              <tbody>
                {empresas.map((e) => (
                  <tr key={e.id_empresa}>
                    <td>{e.nombre}</td>
                    <td>{e.nit}</td>
                    <td>{e.correo ?? '—'}</td>
                    <td>{e.telefono ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Empleados</h2>
        <p className="state-text">
          Elige una empresa para gestionar sus empleados.
        </p>

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

        {empresaActiva && (
          <EmpleadosSection
            key={empresaActiva.id_empresa}
            empresa={empresaActiva}
          />
        )}
      </section>
    </div>
  )
}
