/* API del catálogo de empresas cliente.
 *
 * Consume el backend real: `GET /empresas` (listado dentro del alcance del rol:
 * los internos ven todas, el ADMIN_CLIENTE solo la suya) y `POST /empresas`
 * (alta, solo COMERCIAL_MANSILLAS). El interceptor de `apiClient` adjunta el
 * JWT; los errores HTTP se propagan tal cual para que las pantallas mapeen
 * 409 (NIT duplicado), 400/422 (datos inválidos) y 403 (sin permiso).
 */
import { apiClient } from './client'

/* Lista las empresas visibles para el usuario autenticado.
 *
 * Devuelve [{ id_empresa, nombre, nit, correo, telefono, permiso_qr, activa }]
 * (EmpresaOut). El backend aplica el alcance por rol. */
export async function listEmpresas() {
  const { data } = await apiClient.get('/empresas')
  return data
}

/* Crea una empresa (solo COMERCIAL_MANSILLAS en el backend).
 *
 * `nombre` y `nit` son obligatorios; `correo` y `telefono` opcionales (se
 * mandan como null si vienen vacíos). Un NIT ya usado responde 409. */
export async function createEmpresa({ nombre, nit, correo, telefono }) {
  const { data } = await apiClient.post('/empresas', {
    nombre: nombre.trim(),
    nit: nit.trim(),
    correo: correo?.trim() || null,
    telefono: telefono?.trim() || null,
  })
  return data
}
