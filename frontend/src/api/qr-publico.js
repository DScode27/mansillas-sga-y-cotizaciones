/* API de la vista pública por QR (recurso de otro dev, mockeable).
 *
 * Cualquier persona que escanea el QR abre la ficha básica de la silla por su
 * `token_publico`, sin login ni OTP (R10, M6). Por eso NO usamos `apiClient`:
 * ese cliente adjunta el JWT y, ante un 401, redirige a /login. Aquí la vista
 * es pública y anónima, así que usamos una instancia axios propia sin esos
 * interceptores; un token inválido responde 404 y la pantalla lo muestra.
 *
 * Con `USE_MOCK.qrPublico` en `true` trabaja sobre datos simulados; en `false`
 * pega al endpoint público real sin tocar la pantalla. El backend expone solo
 * datos básicos (empresa/sede, identificación de la silla y estado de sus
 * componentes), nunca precotizaciones ni datos sensibles.
 */
import axios from 'axios'
import { USE_MOCK } from './mocks'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

// Cliente anónimo: sin Authorization ni redirección a /login (ver cabecera).
const publicClient = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
})

// Cliente anónimo para bajar imágenes: mismo `baseURL`, sin JWT, y con
// `responseType: 'blob'` para recibir los bytes de la foto tal cual.
const publicBlobClient = axios.create({
  baseURL,
  responseType: 'blob',
})

// Error que la pantalla reconoce como "token inválido" (404), para distinguirlo
// de un fallo de red/servidor y mostrar el mensaje correcto.
export class TokenNoEncontrado extends Error {
  constructor() {
    super('Token público no encontrado')
    this.name = 'TokenNoEncontrado'
  }
}

// Fichas simuladas, indexadas por token. Reflejan lo que expone el backend:
// identificación de la silla, dueño (empresa/sede) y estado de los componentes.
// Coincide con `token_publico` que genera el mock de sillas (`mock-token-1`…).
// `permiso_qr` decide el bloque de tickets de la pantalla (1=solo consulta,
// 2=consulta+tickets, 3=tickets solo admin); se añaden fichas con nivel 1 y 3
// para poder demostrar los avisos sin formulario.
const fichasMock = {
  'mock-token-1': {
    codigo_qr: 'SIC-00000001',
    estado: 'REGISTRADA',
    empresa: 'Industrias del Valle S.A.S.',
    sede: 'Sede Principal',
    serial_antiguo: 'OLD-3391',
    cargo: 'Analista de compras',
    permiso_qr: 2,
    componentes: [
      { nombre: 'Cilindros', estado: 'BUENO' },
      { nombre: 'Ruedas', estado: 'MANTENIMIENTO' },
      { nombre: 'Bases', estado: 'BUENO' },
      { nombre: 'Asiento / Espaldar', estado: 'DANADO' },
      { nombre: 'Malla', estado: 'BUENO' },
    ],
    // Fotos simuladas: ids + una imagen placeholder por cada una (ver
    // `listFotosPublicas`/`getFotoPublicaUrl`).
    fotos: [{ id_fotografia: 101 }, { id_fotografia: 102 }],
  },
  'mock-token-2': {
    codigo_qr: 'SIC-00000002',
    estado: 'REGISTRADA',
    empresa: 'Industrias del Valle S.A.S.',
    sede: 'Sede Principal',
    cargo: 'Auxiliar contable',
    permiso_qr: 1,
    componentes: [{ nombre: 'Ruedas', estado: 'BUENO' }],
  },
  'mock-token-3': {
    codigo_qr: 'SIC-00000003',
    estado: 'REGISTRADA',
    empresa: 'Industrias del Valle S.A.S.',
    sede: 'Sede Secundaria',
    cargo: 'Jefe de planta',
    permiso_qr: 3,
    componentes: [{ nombre: 'Bases', estado: 'MANTENIMIENTO' }],
  },
}

// Empleados simulados por token, coherentes con cada ficha. Identifican al
// empleado por correo o documento dentro de la empresa dueña, igual que el
// backend (RN-6). Un correo/documento que no coincida produce el 404
// "Empleado no encontrado".
const empleadosMock = {
  'mock-token-1': { correo: 'empleado@valle.com', documento: '1001001001' },
  'mock-token-2': { correo: 'auxiliar@valle.com', documento: '1002002002' },
  'mock-token-3': { correo: 'jefe@valle.com', documento: '1003003003' },
}

// OTP fijo que el mock acepta como válido. El mock NUNCA lo envía al navegador
// ni lo muestra; solo lo compara en memoria, igual que el backend compara el
// hash sin exponer el código. En modo real el empleado lo recibe por correo.
const OTP_MOCK_VALIDO = '000000'

// OTPs emitidos en el mock, por token: simula que el empleado ya solicitó su
// código. Una entrada presente equivale a "hay un OTP vigente para este token".
const otpEmitidosMock = new Set()

// Contador de tickets del mock para devolver un número incremental coherente.
let siguienteIdTicketMock = 9001

// Construye un error con forma de respuesta axios (`err.response.status`) para
// que la pantalla mapee el código HTTP igual que con el backend real.
function errorHttpMock(status, detail) {
  const error = new Error(detail)
  error.response = { status, data: { detail } }
  return error
}

// Localiza al empleado simulado de un token comparando correo o documento, con
// el mismo criterio que el backend (acotado a la empresa dueña de la silla).
function coincideEmpleadoMock(token, { correo, documento }) {
  const empleado = empleadosMock[token]
  if (!empleado) return false
  if (correo && empleado.correo === correo) return true
  if (documento && empleado.documento === documento) return true
  return false
}

/* Trae la ficha pública de una silla por su `token_publico`.
 * Lanza `TokenNoEncontrado` cuando el token no existe (404); cualquier otro
 * fallo se propaga tal cual para que la pantalla muestre un error genérico. */
export async function getSillaPublica(token) {
  if (USE_MOCK.qrPublico) {
    const ficha = fichasMock[token]
    if (!ficha) {
      throw new TokenNoEncontrado()
    }
    // Normaliza la ficha mock al mismo contrato que la rama real (incluye
    // `permiso_qr`), para que la pantalla no dependa de qué rama la sirvió.
    return {
      id_silla: ficha.id_silla ?? null,
      codigo_qr: ficha.codigo_qr,
      estado: ficha.estado ?? null,
      cargo: ficha.cargo ?? null,
      permiso_qr: ficha.permiso_qr ?? null,
      empresa: ficha.empresa ?? null,
      sede: ficha.sede ?? null,
      serial_antiguo: ficha.serial_antiguo ?? null,
      componentes: ficha.componentes ?? [],
    }
  }

  try {
    // Ruta pública real (HU-17): GET /qr/silla/{token}. Es el único endpoint
    // anónimo de consulta por QR; `GET /sillas/token/{token}` es interno
    // (contrato `SillaCreadaOut`) y no debe usarse aquí. El contrato público
    // `ConsultaPublicaOut` expone solo datos básicos: `id_silla`, `codigo_qr`,
    // `estado`, `cargo` y `permiso_qr` de la empresa dueña; nunca datos
    // personales del empleado. Empresa/sede, serial y componentes aún NO los
    // devuelve el backend, así que la pantalla los resuelve con `?? '—'` o no
    // los renderiza (la ficha es defensiva ante campos ausentes).
    const { data } = await publicClient.get(`/qr/silla/${token}`)
    return {
      id_silla: data.id_silla ?? null,
      codigo_qr: data.codigo_qr,
      estado: data.estado ?? null,
      cargo: data.cargo ?? null,
      permiso_qr: data.permiso_qr ?? null,
      empresa: data.empresa ?? null,
      sede: data.sede ?? null,
      serial_antiguo: data.serial_antiguo ?? null,
      componentes: data.componentes ?? [],
    }
  } catch (err) {
    if (err.response?.status === 404) {
      throw new TokenNoEncontrado()
    }
    throw err
  }
}

/* Solicita el envío de un OTP al empleado de la silla (POST /qr/silla/{token}/otp).
 *
 * Paso 1 del flujo público de ticket (HU-24, RF-24). El empleado se identifica
 * con su `correo` o su `documento`; el backend lo resuelve dentro de la empresa
 * dueña de la silla y le envía el código por correo. Responde 204 sin cuerpo:
 * esta función no devuelve nada en caso de éxito.
 *
 * El código NUNCA viaja a esta vista anónima: lo recibe el empleado por correo.
 * En modo mock se registra que hay un OTP vigente para el token (sin exponer el
 * valor) cuando la identificación coincide; si no, se reproduce el 404
 * "Empleado no encontrado" del backend. Los errores HTTP se propagan tal cual
 * (o con forma `err.response.status` en mock) para que la pantalla los mapee. */
export async function solicitarOtpTicket(token, { correo, documento }) {
  if (USE_MOCK.qrPublico) {
    if (!fichasMock[token]) {
      throw errorHttpMock(404, 'QR no válido')
    }
    if (!coincideEmpleadoMock(token, { correo, documento })) {
      throw errorHttpMock(404, 'Empleado no encontrado')
    }
    otpEmitidosMock.add(token)
    return
  }

  // 204 No Content: sin cuerpo que leer. Los errores (404 QR/empleado) se
  // propagan para que la pantalla los mapee por `err.response.status`.
  await publicClient.post(`/qr/silla/${token}/otp`, { correo, documento })
}

/* Crea un ticket validado por OTP para la silla (POST /qr/silla/{token}/ticket).
 *
 * Paso 2 del flujo público de ticket (HU-24, RF-24). Envía asunto, descripción,
 * la identificación del empleado (`correo` o `documento`) y el `codigo` recibido
 * por correo. El backend aplica el `permiso_qr` de la empresa (403 si el nivel
 * no habilita al empleado), valida el OTP (400 si es inválido/expirado) y crea
 * el ticket. Responde 201 con el `TicketOut`; esta función devuelve esos datos
 * (incluye `id_ticket`, que la pantalla muestra como confirmación).
 *
 * El `codigo` solo se envía al backend: nunca se muestra ni registra en claro.
 * En modo mock se validan permiso, identificación y OTP de forma coherente con
 * el backend, devolviendo un ticket simulado con número incremental. */
export async function crearTicket(
  token,
  { asunto, descripcion, correo, documento, codigo },
) {
  if (USE_MOCK.qrPublico) {
    const ficha = fichasMock[token]
    if (!ficha) {
      throw errorHttpMock(404, 'QR no válido')
    }
    if (ficha.permiso_qr === 1) {
      throw errorHttpMock(403, 'Permiso insuficiente')
    }
    if (ficha.permiso_qr === 3) {
      throw errorHttpMock(
        403,
        'Solo el administrador del cliente puede crear tickets',
      )
    }
    if (!coincideEmpleadoMock(token, { correo, documento })) {
      throw errorHttpMock(404, 'Empleado no encontrado')
    }
    if (!otpEmitidosMock.has(token) || codigo !== OTP_MOCK_VALIDO) {
      throw errorHttpMock(400, 'OTP inválido')
    }
    // OTP válido: se consume (un solo uso, como en el backend) y se devuelve un
    // ticket simulado con el contrato de `TicketOut`.
    otpEmitidosMock.delete(token)
    const idTicket = siguienteIdTicketMock++
    return {
      id_ticket: idTicket,
      id_silla: ficha.id_silla ?? null,
      asunto,
      descripcion,
      estado: 'ABIERTO',
      fecha_creacion: new Date().toISOString(),
    }
  }

  const { data } = await publicClient.post(`/qr/silla/${token}/ticket`, {
    asunto,
    descripcion,
    correo,
    documento,
    codigo,
  })
  return data
}

/* Lista las fotos públicas de una silla por su `token_publico`
 * (GET /qr/silla/{token}/fotos).
 *
 * El backend expone solo los `id_fotografia`; los bytes se bajan aparte con
 * `getFotoPublicaUrl`. Una silla sin fotos devuelve []. Un token inválido
 * propaga `TokenNoEncontrado` (404), igual que la ficha. En modo mock devuelve
 * la lista `fotos` de la ficha simulada. */
export async function listFotosPublicas(token) {
  if (USE_MOCK.qrPublico) {
    const ficha = fichasMock[token]
    if (!ficha) throw new TokenNoEncontrado()
    return ficha.fotos ?? []
  }

  try {
    const { data } = await publicClient.get(`/qr/silla/${token}/fotos`)
    return data
  } catch (err) {
    if (err.response?.status === 404) throw new TokenNoEncontrado()
    throw err
  }
}

/* Baja una foto pública y devuelve un object URL para mostrarla
 * (GET /qr/silla/{token}/fotos/{id_fotografia}).
 *
 * Usa el cliente anónimo con `responseType: 'blob'` (sin JWT). Quien la use debe
 * revocar el object URL (`URL.revokeObjectURL`) al desmontar para no filtrar
 * memoria. En modo mock genera un SVG placeholder como data URL (no hay bytes
 * reales que servir), coherente con el resto de mocks de previsualización. */
export async function getFotoPublicaUrl(token, idFotografia) {
  if (USE_MOCK.qrPublico) {
    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120">` +
      `<rect width="100%" height="100%" fill="#e2e8f0"/>` +
      `<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" ` +
      `font-family="sans-serif" font-size="14" fill="#475569">Foto ${idFotografia}</text>` +
      `</svg>`
    return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
  }

  const { data } = await publicBlobClient.get(
    `/qr/silla/${token}/fotos/${idFotografia}`,
  )
  return URL.createObjectURL(data)
}
