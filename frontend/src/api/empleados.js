/* API de empleados del cliente (recurso de otro dev, mockeable).
 *
 * Mismo patrón que `empresas.js`: con `USE_MOCK.empleados` en `true` trabaja
 * sobre un store en memoria; en `false` pega al backend real sin tocar las
 * pantallas. Cubre el alta manual y la importación por Excel (R6): la
 * importación manda las filas ya parseadas por el frontend y el backend las
 * inserta y registra la carga en `carga_excel`.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

// Store en memoria para el mock, por empresa. Se reinicia al recargar.
const empleadosMock = []
let proximoIdMock = 1

function filtrarPorEmpresa(idEmpresa) {
  return empleadosMock.filter((e) => e.id_empresa === Number(idEmpresa))
}

export async function listEmpleados(idEmpresa) {
  if (USE_MOCK.empleados) {
    return filtrarPorEmpresa(idEmpresa)
  }
  const { data } = await apiClient.get('/empleados', {
    params: { id_empresa: idEmpresa },
  })
  return data
}

export async function createEmpleado({
  id_empresa,
  id_sede,
  id_departamento,
  nombre,
  documento,
  correo,
  cargo,
}) {
  const payload = {
    id_empresa: Number(id_empresa),
    id_sede: Number(id_sede),
    id_departamento: Number(id_departamento),
    nombre: nombre.trim(),
    documento: documento?.trim() || null,
    correo: correo?.trim() || null,
    cargo: cargo.trim(),
  }

  if (USE_MOCK.empleados) {
    if (
      payload.documento &&
      empleadosMock.some(
        (e) =>
          e.id_empresa === payload.id_empresa && e.documento === payload.documento,
      )
    ) {
      // UNIQUE (id_empresa, documento) del SQL → 409 en el backend real.
      throw { response: { status: 409 } }
    }
    const empleado = { id_empleado: proximoIdMock++, activo: true, ...payload }
    empleadosMock.push(empleado)
    return empleado
  }

  const { data } = await apiClient.post('/empleados', payload)
  return data
}

/* Importación masiva por Excel (R6).
 *
 * `filas` son los empleados ya validados en la previsualización. El backend
 * inserta lo válido, registra la carga en `carga_excel` (archivo, procesados,
 * con error) y devuelve el resumen. En mock simulamos ese resumen e insertamos
 * en el store para que el listado los refleje.
 */
export async function importarEmpleadosExcel({ id_empresa, nombre_archivo, filas }) {
  if (USE_MOCK.empleados) {
    let procesados = 0
    const errores = []
    filas.forEach((fila, indice) => {
      const duplicado =
        fila.documento &&
        empleadosMock.some(
          (e) =>
            e.id_empresa === Number(id_empresa) && e.documento === fila.documento,
        )
      if (duplicado) {
        errores.push({ fila: indice + 1, motivo: 'Documento duplicado' })
        return
      }
      empleadosMock.push({
        id_empleado: proximoIdMock++,
        id_empresa: Number(id_empresa),
        activo: true,
        ...fila,
      })
      procesados++
    })
    return {
      id_carga: Date.now(),
      nombre_archivo,
      registros_procesados: procesados,
      registros_con_error: errores.length,
      errores,
    }
  }

  const { data } = await apiClient.post('/empleados/importar', {
    id_empresa: Number(id_empresa),
    nombre_archivo,
    filas,
  })
  return data
}
