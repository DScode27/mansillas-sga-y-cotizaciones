/* Gestión de usuarios (HU-20, R5).
 *
 * Solo la ve COMERCIAL_MANSILLAS (la ruta está tras RequireRole y el backend
 * impone el 403). Lista los usuarios y permite crear uno nuevo con su rol. El
 * campo "empresa" solo aparece y se exige para roles de cliente (ADMIN_CLIENTE
 * /EMPLEADO_CLIENTE); para roles internos el backend quiere id_empresa nulo.
 * Maneja estados de carga, error y vacío, y refleja los errores del backend
 * (correo duplicado 409, regla de empresa 400).
 */
import { Fragment, useEffect, useState } from 'react'
import { asignarRol, createUsuario, listUsuarios } from '../api/usuarios'
import { listEmpresas } from '../api/empresas'
import PasswordField from '../components/PasswordField'
import { ROLES } from '../auth/roles'
import { construirCambioRol, rolEsDeCliente } from './usuariosRol'

// Roles que se pueden asignar desde esta pantalla, con etiqueta legible.
const ROLES_ASIGNABLES = [
  { value: ROLES.COMERCIAL_MANSILLAS, label: 'Comercial Mansillas' },
  { value: ROLES.TECNICO, label: 'Técnico' },
  { value: ROLES.ADMIN_CLIENTE, label: 'Administrador cliente' },
  { value: ROLES.EMPLEADO_CLIENTE, label: 'Empleado cliente' },
]

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

  // Empresas para elegir por nombre al asignar un rol de cliente (P1). Si el
  // listado falla, `empresasDisponibles` cae a false y el campo degrada al
  // input de ID actual para no bloquear la gestión.
  const [empresas, setEmpresas] = useState([])
  const [empresasDisponibles, setEmpresasDisponibles] = useState(true)

  const [form, setForm] = useState(FORM_INICIAL)
  const [enviando, setEnviando] = useState(false)
  const [errorForm, setErrorForm] = useState('')
  const [exito, setExito] = useState('')

  // Edición de rol inline (RF-20): id del usuario con el control abierto, borrador
  // del nuevo rol/empresa, y estados de envío/error por fila.
  const [rolEditandoId, setRolEditandoId] = useState(null)
  const [rolDraft, setRolDraft] = useState({ rol: ROLES.TECNICO, id_empresa: '' })
  const [guardandoRol, setGuardandoRol] = useState(false)
  const [errorRol, setErrorRol] = useState('')

  const rolEsCliente = rolEsDeCliente(form.rol)
  const rolDraftEsCliente = rolEsDeCliente(rolDraft.rol)

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

  // Carga el catálogo de empresas para el desplegable (P1). Un fallo degrada a
  // input de ID (no bloquea el alta ni el cambio de rol).
  useEffect(() => {
    let vigente = true
    listEmpresas()
      .then((data) => {
        if (vigente) setEmpresas(data)
      })
      .catch(() => {
        if (vigente) setEmpresasDisponibles(false)
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

  // Abre/cierra el control de cambio de rol de una fila. Al abrir, siembra el
  // borrador con el rol y empresa actuales del usuario.
  function toggleEdicionRol(usuario) {
    setErrorRol('')
    if (rolEditandoId === usuario.id_usuario) {
      setRolEditandoId(null)
      return
    }
    setRolEditandoId(usuario.id_usuario)
    setRolDraft({
      rol: usuario.rol,
      id_empresa: usuario.id_empresa != null ? String(usuario.id_empresa) : '',
    })
  }

  function actualizarRolDraft(campo, valor) {
    setRolDraft((prev) => ({ ...prev, [campo]: valor }))
  }

  async function handleGuardarRol(event, idUsuario) {
    event.preventDefault()
    setErrorRol('')

    // Misma regla condicional que el alta: cliente exige empresa, interno la omite.
    const { error, payload } = construirCambioRol({
      rol: rolDraft.rol,
      idEmpresa: rolDraft.id_empresa,
    })
    if (error) {
      setErrorRol(error)
      return
    }

    setGuardandoRol(true)
    try {
      await asignarRol(idUsuario, payload)
      setRolEditandoId(null)
      await cargarUsuarios()
    } catch (err) {
      const status = err.response?.status
      if (status === 400) {
        setErrorRol(err.response?.data?.detail ?? 'Regla de rol/empresa inválida.')
      } else if (status === 404) {
        setErrorRol('El usuario ya no existe.')
      } else {
        setErrorRol('No se pudo cambiar el rol. Inténtalo de nuevo.')
      }
    } finally {
      setGuardandoRol(false)
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
            <PasswordField
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
              <span className="form-field__label">Empresa</span>
              {empresasDisponibles ? (
                <select
                  className="form-field__input"
                  value={form.id_empresa}
                  onChange={(e) => actualizarCampo('id_empresa', e.target.value)}
                  required
                  disabled={enviando || empresas.length === 0}
                >
                  <option value="">
                    {empresas.length === 0 ? '— Sin empresas —' : '— Seleccionar —'}
                  </option>
                  {empresas.map((emp) => (
                    <option key={emp.id_empresa} value={emp.id_empresa}>
                      {emp.nombre}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="form-field__input"
                  type="number"
                  min={1}
                  value={form.id_empresa}
                  onChange={(e) => actualizarCampo('id_empresa', e.target.value)}
                  required
                  disabled={enviando}
                  placeholder="ID de empresa"
                />
              )}
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
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {usuarios.map((u) => {
                  const editando = rolEditandoId === u.id_usuario
                  return (
                    <Fragment key={u.id_usuario}>
                      <tr>
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
                        <td>
                          <button
                            className="btn btn--ghost"
                            type="button"
                            onClick={() => toggleEdicionRol(u)}
                            aria-expanded={editando}
                            disabled={guardandoRol}
                          >
                            {editando ? 'Cancelar' : 'Cambiar rol'}
                          </button>
                        </td>
                      </tr>
                      {editando && (
                        <tr className="data-table__detalle">
                          <td colSpan={6}>
                            <form
                              className="form-grid"
                              onSubmit={(e) => handleGuardarRol(e, u.id_usuario)}
                            >
                              <label className="form-field">
                                <span className="form-field__label">Nuevo rol</span>
                                <select
                                  className="form-field__input"
                                  value={rolDraft.rol}
                                  onChange={(e) =>
                                    actualizarRolDraft('rol', e.target.value)
                                  }
                                  disabled={guardandoRol}
                                >
                                  {ROLES_ASIGNABLES.map((r) => (
                                    <option key={r.value} value={r.value}>
                                      {r.label}
                                    </option>
                                  ))}
                                </select>
                              </label>

                              {rolDraftEsCliente && (
                                <label className="form-field">
                                  <span className="form-field__label">
                                    Empresa
                                  </span>
                                  {empresasDisponibles ? (
                                    <select
                                      className="form-field__input"
                                      value={rolDraft.id_empresa}
                                      onChange={(e) =>
                                        actualizarRolDraft('id_empresa', e.target.value)
                                      }
                                      required
                                      disabled={guardandoRol || empresas.length === 0}
                                    >
                                      <option value="">
                                        {empresas.length === 0
                                          ? '— Sin empresas —'
                                          : '— Seleccionar —'}
                                      </option>
                                      {empresas.map((emp) => (
                                        <option
                                          key={emp.id_empresa}
                                          value={emp.id_empresa}
                                        >
                                          {emp.nombre}
                                        </option>
                                      ))}
                                    </select>
                                  ) : (
                                    <input
                                      className="form-field__input"
                                      type="number"
                                      min={1}
                                      value={rolDraft.id_empresa}
                                      onChange={(e) =>
                                        actualizarRolDraft('id_empresa', e.target.value)
                                      }
                                      required
                                      disabled={guardandoRol}
                                      placeholder="ID de empresa"
                                    />
                                  )}
                                </label>
                              )}

                              {errorRol && (
                                <p className="form-error" role="alert">
                                  {errorRol}
                                </p>
                              )}

                              <div className="form-actions">
                                <button
                                  className="btn"
                                  type="submit"
                                  disabled={guardandoRol}
                                >
                                  {guardandoRol ? 'Guardando…' : 'Guardar rol'}
                                </button>
                              </div>
                            </form>
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
    </div>
  )
}
