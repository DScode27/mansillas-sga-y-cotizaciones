/* Gestión de usuarios (HU-20, R5).
 *
 * Solo la ve COMERCIAL_MANSILLAS (la ruta está tras RequireRole y el backend
 * impone el 403). Lista los usuarios y permite crear uno nuevo con su rol. El
 * campo "empresa" solo aparece y se exige para roles de cliente (ADMIN_CLIENTE
 * /EMPLEADO_CLIENTE); para roles internos el backend quiere id_empresa nulo.
 * Maneja estados de carga, error y vacío, y refleja los errores del backend
 * (correo duplicado 409, regla de empresa 400).
 */
import { useEffect, useState } from 'react'
import { createUsuario, listUsuarios } from '../api/usuarios'
import { ROLES } from '../auth/roles'

// Roles que se pueden asignar desde esta pantalla, con etiqueta legible.
const ROLES_ASIGNABLES = [
  { value: ROLES.COMERCIAL_MANSILLAS, label: 'Comercial Mansillas' },
  { value: ROLES.TECNICO, label: 'Técnico' },
  { value: ROLES.ADMIN_CLIENTE, label: 'Administrador cliente' },
  { value: ROLES.EMPLEADO_CLIENTE, label: 'Empleado cliente' },
]

const ROLES_CLIENTE = [ROLES.ADMIN_CLIENTE, ROLES.EMPLEADO_CLIENTE]

const FORM_INICIAL = {
  nombre: '',
  correo: '',
  password: '',
  rol: ROLES.TECNICO,
  id_empresa: '',
}

export default function UsuariosPage() {
  const [usuarios, setUsuarios] = useState([])
  const [cargando, setCargando] = useState(true)
  const [errorLista, setErrorLista] = useState('')

  const [form, setForm] = useState(FORM_INICIAL)
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')
  const [exito, setExito] = useState('')

  const rolEsCliente = ROLES_CLIENTE.includes(form.rol)

  async function cargarUsuarios() {
    setCargando(true)
    setErrorLista('')
    try {
      const data = await listUsuarios()
      setUsuarios(data)
    } catch {
      setErrorLista('No se pudieron cargar los usuarios.')
    } finally {
      setCargando(false)
    }
  }

  // Carga inicial. El estado ya arranca en `cargando=true` / `errorLista=''`,
  // así que el efecto no hace ningún setState síncrono: solo refleja el
  // resultado del fetch cuando llega.
  useEffect(() => {
    let vigente = true
    listUsuarios()
      .then((data) => {
        if (vigente) setUsuarios(data)
      })
      .catch(() => {
        if (vigente) setErrorLista('No se pudieron cargar los usuarios.')
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

    if (rolEsCliente && !form.id_empresa.trim()) {
      setErrorForm('Los roles de cliente requieren el ID de empresa.')
      return
    }

    setEnviando(true)
    try {
      await createUsuario({
        nombre: form.nombre.trim(),
        correo: form.correo.trim(),
        password: form.password,
        rol: form.rol,
        id_empresa: rolEsCliente ? Number(form.id_empresa) : null,
      })
      setExito('Usuario creado. Ya puede iniciar sesión.')
      setForm(FORM_INICIAL)
      await cargarUsuarios()
    } catch (err) {
      const status = err.response?.status
      if (status === 409) {
        setErrorForm('Ya existe un usuario con ese correo.')
      } else if (status === 400) {
        setErrorForm(err.response?.data?.detail ?? 'Datos inválidos.')
      } else {
        setErrorForm('No se pudo crear el usuario. Inténtalo de nuevo.')
      }
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="page-stack">
      <section className="card">
        <h1>Crear usuario</h1>
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
            <span className="form-field__label">Correo</span>
            <input
              className="form-field__input"
              type="email"
              autoComplete="off"
              value={form.correo}
              onChange={(e) => actualizarCampo('correo', e.target.value)}
              required
              disabled={enviando}
            />
          </label>

          <label className="form-field">
            <span className="form-field__label">Contraseña</span>
            <input
              className="form-field__input"
              type="password"
              autoComplete="new-password"
              minLength={6}
              value={form.password}
              onChange={(e) => actualizarCampo('password', e.target.value)}
              required
              disabled={enviando}
            />
          </label>

          <label className="form-field">
            <span className="form-field__label">Rol</span>
            <select
              className="form-field__input"
              value={form.rol}
              onChange={(e) => actualizarCampo('rol', e.target.value)}
              disabled={enviando}
            >
              {ROLES_ASIGNABLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>

          {rolEsCliente && (
            <label className="form-field">
              <span className="form-field__label">ID de empresa</span>
              <input
                className="form-field__input"
                type="number"
                min={1}
                value={form.id_empresa}
                onChange={(e) => actualizarCampo('id_empresa', e.target.value)}
                required
                disabled={enviando}
              />
            </label>
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
              {enviando ? 'Creando…' : 'Crear usuario'}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h2>Usuarios</h2>

        {cargando && <p className="state-text">Cargando usuarios…</p>}

        {!cargando && errorLista && (
          <div className="state-error" role="alert">
            <p>{errorLista}</p>
            <button className="btn btn--ghost" type="button" onClick={cargarUsuarios}>
              Reintentar
            </button>
          </div>
        )}

        {!cargando && !errorLista && usuarios.length === 0 && (
          <p className="state-text">Aún no hay usuarios registrados.</p>
        )}

        {!cargando && !errorLista && usuarios.length > 0 && (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Correo</th>
                  <th>Rol</th>
                  <th>Empresa</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {usuarios.map((u) => (
                  <tr key={u.id_usuario}>
                    <td>{u.nombre}</td>
                    <td>{u.correo}</td>
                    <td>{u.rol}</td>
                    <td>{u.id_empresa ?? '—'}</td>
                    <td>
                      <span
                        className={
                          u.activo ? 'badge badge--ok' : 'badge badge--off'
                        }
                      >
                        {u.activo ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
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
