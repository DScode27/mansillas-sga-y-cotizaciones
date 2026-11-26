/* API de precotizaciones (recurso de otro dev, mockeable).
 *
 * Mismo patrón que `visitas.js`/`sillas.js`: con `USE_MOCK.precotizaciones` en
 * `true` trabaja sobre un store en memoria; en `false` pega al backend real sin
 * tocar las pantallas. Cubre el portal comercial (R9, M5): el comercial ve las
 * sillas levantadas de una visita y crea precotizaciones en estado `BORRADOR`.
 *
 * Reglas del SQL que respetamos aquí:
 *   - El estado arranca en `BORRADOR` (DEFAULT de `precotizacion`). La
 *     aceptación (`ENVIADA`/`ACEPTADA`) queda fuera de mi alcance.
 *   - `creada_por` es el usuario comercial autenticado; `token` lo genera la BD.
 *
 * El listado acepta `id_visita` para pedir solo las precotizaciones de esa
 * visita; el aislamiento real por empresa lo impone el backend según el usuario
 * autenticado (R4), esto solo es el filtro de la pantalla.
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

// Store en memoria para el mock. Se reinicia al recargar.
const precotizacionesMock = []
let proximoIdMock = 1

export async function listPrecotizaciones(idVisita) {
  if (USE_MOCK.precotizaciones) {
    if (idVisita == null || idVisita === '') {
      return [...precotizacionesMock]
    }
    return precotizacionesMock.filter((p) => p.id_visita === Number(idVisita))
  }
  const { data } = await apiClient.get('/precotizaciones', {
    params: idVisita ? { id_visita: idVisita } : undefined,
  })
  return data
}

export async function createPrecotizacion({
  id_visita,
  observaciones,
}) {
  // Contrato real (POST /precotizaciones, `PrecotizacionCreate`): solo acepta
  // `id_visita`, `confirmar_validacion` y `observaciones`. `id_empresa` y
  // `creada_por` los deriva el backend del usuario comercial autenticado, así
  // que no se envían. `confirmar_validacion` DEBE ser `true` (StrictBool): el
  // comercial confirma que revisó el levantamiento (HU-12); sin ella el backend
  // responde 422.
  const payload = {
    id_visita: Number(id_visita),
    confirmar_validacion: true,
    observaciones: observaciones?.trim() || null,
  }

  if (USE_MOCK.precotizaciones) {
    const precotizacion = {
      id_precotizacion: proximoIdMock++,
      // El estado arranca en BORRADOR (DEFAULT del SQL); el token lo da la BD.
      estado: 'BORRADOR',
      token: `mock-token-${proximoIdMock}`,
      correo_cliente: null,
      fecha_envio: null,
      fecha_aceptacion: null,
      fecha_creacion: new Date().toISOString(),
      ...payload,
    }
    precotizacionesMock.push(precotizacion)
    return precotizacion
  }

  const { data } = await apiClient.post('/precotizaciones', payload)
  return data
}

/* Envía al cliente el enlace único de una precotización (RF-13, HU-13).
 *
 * Contrato real (POST /precotizaciones/{id}/enviar, `EnvioRequest`): acepta
 * `correo_cliente` y `confirmar_validacion`. El backend envía el correo y, solo
 * tras un envío exitoso, pasa la precotización a `ENVIADA`, fija `correo_cliente`
 * y `fecha_envio` (devueltos en la respuesta). Reglas que la pantalla respeta:
 *   - Primer envío desde `BORRADOR`: `confirmar_validacion` DEBE ser `true`
 *     (StrictBool); sin ella el backend responde 422.
 *   - Reenvío desde `ENVIADA`: reusa el `correo_cliente` guardado y NO exige
 *     confirmación; cambiar el destinatario da 409.
 *
 * Los errores HTTP se propagan tal cual (no se envuelven) para que la pantalla
 * los mapee: 422, 409, 503, 502, 404.
 */
export async function enviarPrecotizacion({
  id,
  correo_cliente,
  confirmar_validacion,
}) {
  const payload = {
    correo_cliente: correo_cliente?.trim() ?? '',
    confirmar_validacion: confirmar_validacion === true,
  }

  if (USE_MOCK.precotizaciones) {
    const precotizacion = precotizacionesMock.find(
      (p) => p.id_precotizacion === Number(id),
    )
    if (precotizacion == null) {
      const error = new Error('No encontrado')
      error.response = { status: 404, data: { detail: 'No encontrado' } }
      throw error
    }
    // Un correo vacío es inválido (el backend valida el destinatario → 422).
    if (!payload.correo_cliente) {
      const error = new Error('Correo inválido')
      error.response = { status: 422, data: { detail: 'Correo inválido' } }
      throw error
    }
    const primerEnvio = precotizacion.estado === 'BORRADOR'
    if (primerEnvio) {
      // Primer envío: exige la confirmación de validación del levantamiento.
      if (payload.confirmar_validacion !== true) {
        const error = new Error('Falta confirmación')
        error.response = {
          status: 422,
          data: {
            detail: 'Se requiere confirmar_validacion=true para el primer envío',
          },
        }
        throw error
      }
    } else if (precotizacion.estado === 'ENVIADA') {
      // Reenvío: no se puede cambiar el destinatario ya guardado.
      if (
        precotizacion.correo_cliente &&
        payload.correo_cliente !== precotizacion.correo_cliente
      ) {
        const error = new Error('Destinatario distinto')
        error.response = {
          status: 409,
          data: {
            detail:
              'No se puede cambiar el destinatario de una propuesta ya enviada',
          },
        }
        throw error
      }
    } else {
      // ACEPTADA / ANULADA no son enviables.
      const error = new Error('Estado no enviable')
      error.response = {
        status: 409,
        data: {
          detail: 'La precotización no puede enviarse en su estado actual',
        },
      }
      throw error
    }
    precotizacion.estado = 'ENVIADA'
    precotizacion.correo_cliente = payload.correo_cliente
    precotizacion.fecha_envio = new Date().toISOString()
    return { ...precotizacion }
  }

  const { data } = await apiClient.post(
    `/precotizaciones/${id}/enviar`,
    payload,
  )
  return data
}

/* Lista los accesos registrados al enlace público de una precotización
 * (GET /precotizaciones/{id_precotizacion}/accesos).
 *
 * El backend devuelve la lista de accesos (fecha, navegador, sistema operativo)
 * o, cuando no hay ninguno, un objeto `{ mensaje: 'Sin accesos registrados' }`.
 * Aquí se normaliza siempre a un arreglo para que la pantalla no distinga los
 * dos formatos: lista vacía == sin accesos. Solo el comercial lo consulta, así
 * que va autenticado por `apiClient`. */
export async function listAccesos(idPrecotizacion) {
  if (USE_MOCK.precotizaciones) {
    return []
  }
  const { data } = await apiClient.get(
    `/precotizaciones/${idPrecotizacion}/accesos`,
  )
  return Array.isArray(data) ? data : []
}
