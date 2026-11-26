/* API de la página pública de aceptación de precotización (RF-15, HU-15).
 *
 * El cliente abre el enlace de su propuesta (`/propuesta/{token}`) sin login:
 * consulta la propuesta, solicita un código por correo (OTP) y la acepta con
 * su nombre/cargo + código. Como la vista es anónima NO usamos `apiClient` (ese
 * adjunta el JWT y, ante un 401, redirige a /login). Usamos una instancia axios
 * propia sin esos interceptores, igual que `qr-publico.js`: un token inválido o
 * una propuesta no disponible (BORRADOR/ANULADA) responden 404 y la pantalla lo
 * muestra como "propuesta no disponible".
 *
 * Con `USE_MOCK.propuesta` en `true` trabaja sobre datos simulados; en `false`
 * pega al endpoint público real sin tocar la pantalla. El backend solo expone
 * datos básicos de la propuesta (empresa, fecha de envío y lista de sillas con
 * código QR, cargo y estado); nunca datos sensibles. El código (OTP) NUNCA
 * viaja a esta vista: lo recibe el cliente por correo; aquí solo se envía al
 * backend para aceptar, jamás se muestra ni se registra en claro.
 */
import axios from 'axios'
import { USE_MOCK } from './mocks'

const baseURL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

// Cliente anónimo: sin Authorization ni redirección a /login (ver cabecera).
const publicClient = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
})

// Error que la pantalla reconoce como "propuesta no disponible" (404), para
// distinguirlo de un fallo de red/servidor y mostrar el mensaje correcto.
// Análogo a `TokenNoEncontrado` de `qr-publico.js`.
export class PropuestaNoEncontrada extends Error {
  constructor() {
    super('Propuesta no disponible')
    this.name = 'PropuestaNoEncontrada'
  }
}

// --- Datos simulados ---------------------------------------------------------
// Propuestas simuladas indexadas por token. Reflejan el contrato público
// (`PropuestaPublicaOut`): empresa, fecha de envío, estado y lista de sillas.
// `mock-propuesta-enviada` arranca en ENVIADA (flujo completo) y
// `mock-propuesta-aceptada` ya está ACEPTADA (estado final, sin formulario).
const propuestasMock = {
  'mock-propuesta-enviada': {
    token: 'mock-propuesta-enviada',
    estado: 'ENVIADA',
    fecha_envio: '2024-05-02T14:30:00',
    fecha_aceptacion: null,
    empresa_nombre: 'Industrias del Valle S.A.S.',
    sillas: [
      { codigo_qr: 'SIC-00000001', cargo: 'Analista de compras', estado: 'REGISTRADA' },
      { codigo_qr: 'SIC-00000002', cargo: 'Auxiliar contable', estado: 'REGISTRADA' },
    ],
  },
  'mock-propuesta-aceptada': {
    token: 'mock-propuesta-aceptada',
    estado: 'ACEPTADA',
    fecha_envio: '2024-04-20T09:00:00',
    fecha_aceptacion: '2024-04-21T11:15:00',
    empresa_nombre: 'Comercial Andina Ltda.',
    sillas: [
      { codigo_qr: 'SIC-00000010', cargo: 'Gerente', estado: 'REGISTRADA' },
    ],
  },
}

// OTP fijo que el mock acepta como válido. El mock NUNCA lo envía al navegador
// ni lo muestra; solo lo compara en memoria, igual que el backend compara el
// hash sin exponer el código. En modo real el cliente lo recibe por correo.
const OTP_MOCK_VALIDO = '000000'

// OTPs emitidos en el mock, por token: una entrada presente equivale a "hay un
// OTP vigente para esta propuesta" (el cliente ya lo solicitó).
const otpEmitidosMock = new Set()

// Construye un error con forma de respuesta axios (`err.response.status`) para
// que la pantalla mapee el código HTTP igual que con el backend real.
function errorHttpMock(status, detail) {
  const error = new Error(detail)
  error.response = { status, data: { detail } }
  return error
}

/* Trae la propuesta pública por su `token` (GET /propuesta/{token}).
 *
 * Solo las propuestas ENVIADA/ACEPTADA son consultables; un token inválido o
 * una propuesta en BORRADOR/ANULADA dan un 404 indistinguible que esta función
 * convierte en `PropuestaNoEncontrada`. Cualquier otro fallo se propaga tal
 * cual para que la pantalla muestre un error genérico. */
export async function getPropuesta(token) {
  if (USE_MOCK.propuesta) {
    const propuesta = propuestasMock[token]
    if (!propuesta) {
      throw new PropuestaNoEncontrada()
    }
    return {
      token: propuesta.token,
      estado: propuesta.estado,
      fecha_envio: propuesta.fecha_envio ?? null,
      fecha_aceptacion: propuesta.fecha_aceptacion ?? null,
      empresa_nombre: propuesta.empresa_nombre ?? '',
      sillas: propuesta.sillas ?? [],
    }
  }

  try {
    const { data } = await publicClient.get(`/propuesta/${token}`)
    // El contrato real (`PropuestaPublicaOut`) no incluye `fecha_aceptacion`;
    // la pantalla la obtiene de la respuesta de aceptación. Se normaliza a null
    // para que no dependa de qué rama la sirvió.
    return {
      token: data.token,
      estado: data.estado,
      fecha_envio: data.fecha_envio ?? null,
      fecha_aceptacion: data.fecha_aceptacion ?? null,
      empresa_nombre: data.empresa_nombre ?? '',
      sillas: data.sillas ?? [],
    }
  } catch (err) {
    if (err.response?.status === 404) {
      throw new PropuestaNoEncontrada()
    }
    throw err
  }
}

/* Solicita el envío de un OTP al cliente de la propuesta
 * (POST /propuesta/{token}/otp).
 *
 * Paso 1 del flujo de aceptación (HU-15). El destinatario es SIEMPRE el
 * `correo_cliente` almacenado de la precotización (nunca viene del cliente).
 * Responde 202 sin datos útiles: esta función no devuelve nada en caso de
 * éxito. El código NUNCA viaja a esta vista: lo recibe el cliente por correo.
 *
 * En modo mock se registra que hay un OTP vigente para el token (sin exponer el
 * valor) cuando la propuesta está ENVIADA; si no, se reproduce el 404 del
 * backend. Los errores HTTP se propagan tal cual (o con forma
 * `err.response.status` en mock) para que la pantalla los mapee (404/429/503/502). */
export async function solicitarOtpPropuesta(token) {
  if (USE_MOCK.propuesta) {
    const propuesta = propuestasMock[token]
    if (!propuesta || propuesta.estado !== 'ENVIADA') {
      throw errorHttpMock(404, 'No encontrado')
    }
    otpEmitidosMock.add(token)
    return
  }

  // 202 Accepted: el cuerpo solo trae un mensaje genérico, sin el código. Los
  // errores (404/429/503/502) se propagan para que la pantalla los mapee.
  await publicClient.post(`/propuesta/${token}/otp`)
}

/* Acepta la propuesta con el OTP (POST /propuesta/{token}/aceptar).
 *
 * Paso 2 del flujo de aceptación (HU-15). Envía `nombre_aceptante`,
 * `cargo_aceptante` y el `codigo` recibido por correo. El backend valida el OTP
 * (400 si es inválido/expirado), rechaza una propuesta ya aceptada o no
 * disponible (409) y datos inválidos (422), y registra la aceptación. Responde
 * 200 con `{ estado, fecha_aceptacion }`; esta función devuelve esos datos para
 * que la pantalla muestre la confirmación y bloquee la UI.
 *
 * El `codigo` solo se envía al backend: nunca se muestra ni se registra en
 * claro. En modo mock se validan estado, código y repetición de forma coherente
 * con el backend (correcto → ACEPTADA; incorrecto → 400; repetido → 409). */
export async function aceptarPropuesta(
  token,
  { nombre_aceptante, cargo_aceptante, codigo },
) {
  if (USE_MOCK.propuesta) {
    const propuesta = propuestasMock[token]
    if (!propuesta) {
      throw errorHttpMock(404, 'No encontrado')
    }
    if (propuesta.estado === 'ACEPTADA') {
      throw errorHttpMock(409, 'La propuesta ya fue aceptada')
    }
    if (propuesta.estado !== 'ENVIADA') {
      throw errorHttpMock(
        409,
        'La propuesta no está disponible para aceptación',
      )
    }
    if (!nombre_aceptante?.trim() || !cargo_aceptante?.trim()) {
      throw errorHttpMock(422, 'Datos de aceptación inválidos')
    }
    if (!otpEmitidosMock.has(token) || codigo !== OTP_MOCK_VALIDO) {
      throw errorHttpMock(400, 'Código inválido o expirado')
    }
    // OTP válido: se consume (un solo uso) y la propuesta pasa a ACEPTADA.
    otpEmitidosMock.delete(token)
    const fechaAceptacion = new Date().toISOString()
    propuesta.estado = 'ACEPTADA'
    propuesta.fecha_aceptacion = fechaAceptacion
    return { estado: 'ACEPTADA', fecha_aceptacion: fechaAceptacion }
  }

  const { data } = await publicClient.post(`/propuesta/${token}/aceptar`, {
    nombre_aceptante: nombre_aceptante?.trim() ?? '',
    cargo_aceptante: cargo_aceptante?.trim() ?? '',
    codigo,
  })
  return data
}
