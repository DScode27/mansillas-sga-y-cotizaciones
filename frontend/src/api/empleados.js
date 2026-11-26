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

/* Listado de empleados para los selectores por nombre (Fase 4, R9/RF-06).
 *
 * Consumo directo del endpoint real `GET /empresas/{id_empresa}/empleados`
 * (existe tras la tarea 9), sin mock: es solo lectura y alimenta el `<select>`
 * de empleado del levantamiento. Difiere de `listEmpleados` (que mantiene su
 * contrato mockeable para el CRUD de `EmpleadosSection`): este usa la ruta
 * anidada del catálogo. El interceptor de `apiClient` adjunta el JWT y el
 * backend impone RBAC/aislamiento; los errores HTTP se propagan tal cual para
 * que la pantalla los mapee y, si falla, degrade a input de ID.
 *
 * Devuelve [{ id_empleado, id_empresa, id_sede, id_departamento, nombre,
 * documento, correo, cargo, activo }] (EmpleadoOut). */
export async function listEmpleadosEmpresa(idEmpresa) {
  const { data } = await apiClient.get(`/empresas/${idEmpresa}/empleados`)
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

/* Importación masiva por Excel (R6 / HU-19).
 *
 * Dos contratos según el modo:
 *   - Mock: el frontend ya parseó el `.xlsx` en el navegador y pasa `filas`
 *     (las válidas de la previsualización). Simulamos el resumen e insertamos
 *     en el store para que el listado los refleje.
 *   - Real (`POST /carga-masiva/empleados`): el backend parsea el archivo él
 *     mismo, así que hay que enviarle el `.xlsx` crudo por `multipart/form-data`
 *     (campo `archivo`). El `id_empresa` NO se envía: el backend lo deriva del
 *     `ADMIN_CLIENTE` autenticado (aislamiento estructural). La previsualización
 *     local sigue siendo solo UX; el conteo autoritativo es el del backend.
 *
 * El resumen del backend (`ReporteCargaOut`) trae `total_procesadas`,
 * `total_aplicadas` y `errores: [{ fila, motivo }]`. Lo normalizamos a la forma
 * que consume la pantalla (`registros_procesados`, `registros_con_error`).
 */
export async function importarEmpleadosExcel({
  id_empresa,
  nombre_archivo,
  filas,
  archivo,
}) {
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

  // Endpoint real: manda el archivo crudo; el backend parsea y valida.
  // `Content-Type: undefined` hace que el navegador fije el multipart con su
  // boundary (el `apiClient` trae un default `application/json` que, de dejarse,
  // rompería el parseo del archivo en el backend).
  const formData = new FormData()
  formData.append('archivo', archivo, archivo?.name ?? nombre_archivo)
  const { data } = await apiClient.post('/carga-masiva/empleados', formData, {
    headers: { 'Content-Type': undefined },
  })

  // Normaliza el `ReporteCargaOut` a la forma que usa la pantalla.
  return {
    nombre_archivo: data.nombre_archivo ?? nombre_archivo,
    registros_procesados: data.total_aplicadas ?? 0,
    registros_con_error: data.errores?.length ?? 0,
    errores: data.errores ?? [],
  }
}
