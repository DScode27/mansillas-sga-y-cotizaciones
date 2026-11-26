/* API de empleados del cliente (backend real, Fase 4 R9).
 *
 * Alta manual y listado consumen la ruta anidada del catálogo
 * (`/empresas/{id_empresa}/empleados`), coherente con sedes y departamentos: la
 * empresa va en la ruta, no en el cuerpo. La importación por Excel (R6) manda
 * el `.xlsx` crudo a `POST /carga-masiva/empleados`, que parsea, inserta y
 * registra la carga en `carga_excel`. El interceptor de `apiClient` adjunta el
 * JWT y el backend impone el RBAC y el aislamiento por empresa; los errores HTTP
 * se propagan tal cual para que la pantalla los mapee.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

export async function listEmpleados(idEmpresa) {
  const { data } = await apiClient.get(`/empresas/${idEmpresa}/empleados`)
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

/* Alta manual de un empleado (`POST /empresas/{id_empresa}/empleados`).
 *
 * La empresa va en la ruta, no en el cuerpo. `id_sede` e `id_departamento` son
 * los desplegables encadenados de la pantalla; el backend valida que existan en
 * la empresa y sean coherentes (400 si no). `nombre` y `cargo` son obligatorios;
 * `documento` (único por empresa → 409) y `correo` son opcionales y se mandan
 * como null si vienen vacíos. Devuelve el empleado creado (`EmpleadoOut`). */
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
    id_sede: Number(id_sede),
    id_departamento: Number(id_departamento),
    nombre: nombre.trim(),
    documento: documento?.trim() || null,
    correo: correo?.trim() || null,
    cargo: cargo.trim(),
  }

  const { data } = await apiClient.post(
    `/empresas/${id_empresa}/empleados`,
    payload,
  )
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
