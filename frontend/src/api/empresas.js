/* API de empresas (recurso de otro dev, mockeable).
 *
 * Patrón de mock conmutable: mientras `USE_MOCK.empresas` sea `true`, devuelve
 * datos simulados; al poner la bandera en `false` pega al endpoint real sin
 * cambiar las pantallas que lo consumen. El alta de empresa es la pantalla
 * mínima del MVP (nombre + NIT únicos, R6); sedes/departamentos vienen después.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

// Store en memoria para el mock: permite ver reflejadas las altas durante la
// sesión mientras el endpoint real no existe. Se reinicia al recargar.
const empresasMock = [
  { id_empresa: 1, nombre: 'Empresa Demo S.A.', nit: '900123456-7', activa: true },
]
let proximoIdMock = 2

export async function listEmpresas() {
  if (USE_MOCK.empresas) {
    return [...empresasMock]
  }
  const { data } = await apiClient.get('/empresas')
  return data
}

export async function createEmpresa({ nombre, nit, correo, telefono }) {
  if (USE_MOCK.empresas) {
    const nitNormalizado = nit.trim()
    if (empresasMock.some((e) => e.nit === nitNormalizado)) {
      // Imita el 409 por NIT duplicado del backend real para que la pantalla
      // ejercite esa rama de error también en modo mock.
      throw { response: { status: 409 } }
    }
    const empresa = {
      id_empresa: proximoIdMock++,
      nombre: nombre.trim(),
      nit: nitNormalizado,
      correo: correo?.trim() || null,
      telefono: telefono?.trim() || null,
      activa: true,
    }
    empresasMock.push(empresa)
    return empresa
  }

  const { data } = await apiClient.post('/empresas', {
    nombre: nombre.trim(),
    nit: nit.trim(),
    correo: correo?.trim() || null,
    telefono: telefono?.trim() || null,
  })
  return data
}
