/* Empleados de una empresa: alta manual + importación por Excel (R6).
 *
 * Se monta con una empresa ya elegida (la clave `key` por empresa la remonta al
 * cambiar, así el estado arranca limpio). Dos vías de alta:
 *   - Manual: formulario con empresa/sede/depto y datos del empleado.
 *   - Excel: se parsea el archivo en el navegador, se muestra la
 *     previsualización (filas válidas y errores) y solo al confirmar se envía;
 *     el backend inserta y registra la carga en `carga_excel`.
 *
 * Empleados es recurso de otro dev (mock conmutable). Sede/depto se piden como
 * id porque su CRUD llega en una tarea posterior; las FK compuestas del SQL
 * validan la coherencia en el backend.
 */
import { useEffect, useRef, useState } from 'react'
import {
  createEmpleado,
  importarEmpleadosExcel,
  listEmpleados,
} from '../api/empleados'
import { listSedes } from '../api/sedes'
import { listDepartamentos } from '../api/departamentos'
import { parseEmpleadosExcel } from '../utils/parseEmpleadosExcel'

function formInicial() {
  return {
    id_sede: '',
    id_departamento: '',
    nombre: '',
    documento: '',
    correo: '',
    cargo: '',
  }
}

export default function EmpleadosSection({ empresa }) {
  const idEmpresa = empresa.id_empresa

  const [empleados, setEmpleados] = useState([])
  const [cargando, setCargando] = useState(true)
  const [errorLista, setErrorLista] = useState('')

  // Alta manual
  const [form, setForm] = useState(formInicial)
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')
  const [exitoForm, setExitoForm] = useState('')

  // Desplegables encadenados: sede (por empresa) → departamento (por sede).
  const [sedes, setSedes] = useState([])
  const [cargandoSedes, setCargandoSedes] = useState(false)
  const [errorSedes, setErrorSedes] = useState('')
  const [departamentos, setDepartamentos] = useState([])
  const [cargandoDeptos, setCargandoDeptos] = useState(false)
  const [errorDeptos, setErrorDeptos] = useState('')

  // Importación Excel
  const inputArchivo = useRef(null)
  const [nombreArchivo, setNombreArchivo] = useState('')
  const [archivo, setArchivo] = useState(null) // File original, para el envío real
  const [preview, setPreview] = useState(null) // { columnasFaltantes, validas, errores }
  const [errorArchivo, setErrorArchivo] = useState('')
  const [importando, setImportando] = useState(false)
  const [resumen, setResumen] = useState(null)

  async function cargarEmpleados() {
    setCargando(true)
    setErrorLista('')
    try {
      const data = await listEmpleados(idEmpresa)
      setEmpleados(data)
    } catch {
      setErrorLista('No se pudieron cargar los empleados.')
    } finally {
      setCargando(false)
    }
  }

  useEffect(() => {
    let vigente = true
    listEmpleados(idEmpresa)
      .then((data) => {
        if (vigente) setEmpleados(data)
      })
      .catch(() => {
        if (vigente) setErrorLista('No se pudieron cargar los empleados.')
      })
      .finally(() => {
        if (vigente) setCargando(false)
      })
    return () => {
      vigente = false
    }
  }, [idEmpresa])

  // Carga las sedes de la empresa para el primer desplegable. Los setState van
  // dentro del flujo asíncrono (patrón de `SedesSection`) para no encadenar
  // renders disparando estado síncrono dentro del efecto.
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setSedes([])
        setErrorSedes('')
        setCargandoSedes(true)
        return listSedes(idEmpresa)
      })
      .then((data) => {
        if (vigente && data) setSedes(data)
      })
      .catch(() => {
        if (vigente) setErrorSedes('No se pudieron cargar las sedes.')
      })
      .finally(() => {
        if (vigente) setCargandoSedes(false)
      })
    return () => {
      vigente = false
    }
  }, [idEmpresa])

  // Al elegir sede, carga sus departamentos (FK compuesta por sede). Sin sede
  // elegida, limpia la lista sin pegarle al backend.
  useEffect(() => {
    let vigente = true
    Promise.resolve()
      .then(() => {
        if (!vigente) return null
        setDepartamentos([])
        setErrorDeptos('')
        if (!form.id_sede) {
          setCargandoDeptos(false)
          return null
        }
        setCargandoDeptos(true)
        return listDepartamentos(form.id_sede)
      })
      .then((data) => {
        if (vigente && data) setDepartamentos(data)
      })
      .catch(() => {
        if (vigente) setErrorDeptos('No se pudieron cargar los departamentos.')
      })
      .finally(() => {
        if (vigente && form.id_sede) setCargandoDeptos(false)
      })
    return () => {
      vigente = false
    }
  }, [form.id_sede])

  function actualizarCampo(campo, valor) {
    setForm((prev) => ({ ...prev, [campo]: valor }))
  }

  // Cambiar de sede invalida el departamento elegido (pertenece a la anterior).
  function actualizarSede(valor) {
    setForm((prev) => ({ ...prev, id_sede: valor, id_departamento: '' }))
  }

  async function handleSubmitManual(event) {
    event.preventDefault()
    setErrorForm('')
    setExitoForm('')
    setEnviando(true)
    try {
      await createEmpleado({ id_empresa: idEmpresa, ...form })
      setExitoForm('Empleado agregado.')
      setForm(formInicial())
      await cargarEmpleados()
    } catch (err) {
      const status = err.response?.status
      if (status === 409) {
        setErrorForm('Ya existe un empleado con ese documento en la empresa.')
      } else if (status === 400) {
        setErrorForm(err.response?.data?.detail ?? 'Datos inválidos.')
      } else {
        setErrorForm('No se pudo agregar el empleado. Inténtalo de nuevo.')
      }
    } finally {
      setEnviando(false)
    }
  }

  async function handleArchivo(event) {
    const file = event.target.files?.[0]
    setErrorArchivo('')
    setResumen(null)
    setPreview(null)
    if (!file) {
      setNombreArchivo('')
      setArchivo(null)
      return
    }
    setNombreArchivo(file.name)
    setArchivo(file)
    try {
      const resultado = await parseEmpleadosExcel(file)
      setPreview(resultado)
    } catch (err) {
      setErrorArchivo(err.message ?? 'No se pudo leer el archivo.')
    }
  }

  function limpiarImportacion() {
    setPreview(null)
    setNombreArchivo('')
    setArchivo(null)
    setErrorArchivo('')
    setResumen(null)
    if (inputArchivo.current) inputArchivo.current.value = ''
  }

  async function confirmarImportacion() {
    if (!preview || preview.validas.length === 0) return
    setImportando(true)
    setErrorArchivo('')
    try {
      const res = await importarEmpleadosExcel({
        id_empresa: idEmpresa,
        nombre_archivo: nombreArchivo,
        filas: preview.validas,
        archivo,
      })
      setResumen(res)
      setPreview(null)
      setArchivo(null)
      if (inputArchivo.current) inputArchivo.current.value = ''
      await cargarEmpleados()
    } catch (err) {
      // El endpoint real valida la extensión y el formato (400 con `detail`).
      const detalle = err.response?.data?.detail
      setErrorArchivo(
        detalle ?? 'No se pudo registrar la carga. Inténtalo de nuevo.',
      )
    } finally {
      setImportando(false)
    }
  }

  return (
    <div className="empleados">
      <h3 className="empleados__titulo">{empresa.nombre}</h3>

      {/* --- Alta manual --- */}
      <form className="form-grid" onSubmit={handleSubmitManual}>
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
          <span className="form-field__label">Cargo</span>
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
          <span className="form-field__label">Documento (opcional)</span>
          <input
            className="form-field__input"
            type="text"
            value={form.documento}
            onChange={(e) => actualizarCampo('documento', e.target.value)}
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
          <span className="form-field__label">Sede</span>
          <select
            className="form-field__input"
            value={form.id_sede}
            onChange={(e) => actualizarSede(e.target.value)}
            required
            disabled={enviando || cargandoSedes || sedes.length === 0}
          >
            <option value="">
              {cargandoSedes
                ? 'Cargando sedes…'
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
          {errorSedes && (
            <span className="form-error" role="alert">
              {errorSedes}
            </span>
          )}
        </label>

        <label className="form-field">
          <span className="form-field__label">Departamento</span>
          <select
            className="form-field__input"
            value={form.id_departamento}
            onChange={(e) => actualizarCampo('id_departamento', e.target.value)}
            required
            disabled={
              enviando ||
              !form.id_sede ||
              cargandoDeptos ||
              departamentos.length === 0
            }
          >
            <option value="">
              {!form.id_sede
                ? '— Elige una sede primero —'
                : cargandoDeptos
                  ? 'Cargando departamentos…'
                  : departamentos.length === 0
                    ? '— Sin departamentos —'
                    : '— Seleccionar —'}
            </option>
            {departamentos.map((d) => (
              <option key={d.id_departamento} value={d.id_departamento}>
                {d.nombre}
              </option>
            ))}
          </select>
          {errorDeptos && (
            <span className="form-error" role="alert">
              {errorDeptos}
            </span>
          )}
        </label>

        {errorForm && (
          <p className="form-error" role="alert">
            {errorForm}
          </p>
        )}
        {exitoForm && (
          <p className="form-success" role="status">
            {exitoForm}
          </p>
        )}

        <div className="form-actions">
          <button className="btn" type="submit" disabled={enviando}>
            {enviando ? 'Agregando…' : 'Agregar empleado'}
          </button>
        </div>
      </form>

      {/* --- Importación por Excel --- */}
      <div className="empleados__import">
        <h4 className="empleados__subtitulo">Importar por Excel</h4>
        <p className="state-text">
          Columnas: nombre, cargo, sede, departamento (requeridas); documento y
          correo (opcionales). Solo <code>.xlsx</code>.
        </p>

        <label className="form-field" style={{ maxWidth: '26rem', marginTop: '0.5rem' }}>
          <span className="form-field__label">Archivo</span>
          <input
            ref={inputArchivo}
            className="form-field__input"
            type="file"
            accept=".xlsx"
            onChange={handleArchivo}
            disabled={importando}
          />
        </label>

        {errorArchivo && (
          <p className="form-error" role="alert">
            {errorArchivo}
          </p>
        )}

        {preview && preview.columnasFaltantes.length > 0 && (
          <p className="form-notice" role="alert">
            Faltan columnas requeridas: {preview.columnasFaltantes.join(', ')}.
          </p>
        )}

        {preview && preview.columnasFaltantes.length === 0 && (
          <div className="empleados__preview">
            <p className="form-notice">
              Previsualización de <strong>{nombreArchivo}</strong>:{' '}
              {preview.validas.length} fila(s) válida(s),{' '}
              {preview.errores.length} con error.
            </p>

            {preview.validas.length > 0 && (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Cargo</th>
                      <th>Documento</th>
                      <th>Correo</th>
                      <th>Sede</th>
                      <th>Depto.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.validas.map((fila, i) => (
                      <tr key={i}>
                        <td>{fila.nombre}</td>
                        <td>{fila.cargo}</td>
                        <td>{fila.documento ?? '—'}</td>
                        <td>{fila.correo ?? '—'}</td>
                        <td>{fila.id_sede}</td>
                        <td>{fila.id_departamento}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {preview.errores.length > 0 && (
              <ul className="empleados__errores">
                {preview.errores.map((e) => (
                  <li key={e.fila}>
                    Fila {e.fila}: {e.motivos.join(', ')}.
                  </li>
                ))}
              </ul>
            )}

            <div className="form-actions" style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                className="btn"
                type="button"
                onClick={confirmarImportacion}
                disabled={importando || preview.validas.length === 0}
              >
                {importando
                  ? 'Registrando…'
                  : `Registrar ${preview.validas.length} empleado(s)`}
              </button>
              <button
                className="btn btn--ghost"
                type="button"
                onClick={limpiarImportacion}
                disabled={importando}
              >
                Cancelar
              </button>
            </div>
          </div>
        )}

        {resumen && (
          <p className="form-success" role="status">
            Carga registrada: {resumen.registros_procesados} procesado(s),{' '}
            {resumen.registros_con_error} con error.
          </p>
        )}
      </div>

      {/* --- Listado de empleados --- */}
      <h4 className="empleados__subtitulo">Empleados registrados</h4>

      {cargando && <p className="state-text">Cargando empleados…</p>}

      {!cargando && errorLista && (
        <div className="state-error" role="alert">
          <p>{errorLista}</p>
          <button className="btn btn--ghost" type="button" onClick={cargarEmpleados}>
            Reintentar
          </button>
        </div>
      )}

      {!cargando && !errorLista && empleados.length === 0 && (
        <p className="state-text">Esta empresa aún no tiene empleados.</p>
      )}

      {!cargando && !errorLista && empleados.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Cargo</th>
                <th>Documento</th>
                <th>Correo</th>
                <th>Sede</th>
                <th>Depto.</th>
              </tr>
            </thead>
            <tbody>
              {empleados.map((e) => (
                <tr key={e.id_empleado}>
                  <td>{e.nombre}</td>
                  <td>{e.cargo}</td>
                  <td>{e.documento ?? '—'}</td>
                  <td>{e.correo ?? '—'}</td>
                  <td>{e.id_sede}</td>
                  <td>{e.id_departamento}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
