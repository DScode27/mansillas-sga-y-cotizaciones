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
const fichasMock = {
  'mock-token-1': {
    codigo_qr: 'SIC-00000001',
    estado: 'REGISTRADA',
    empresa: 'Industrias del Valle S.A.S.',
    sede: 'Sede Principal',
    serial_antiguo: 'OLD-3391',
    cargo: 'Analista de compras',
    componentes: [
      { nombre: 'Cilindros', estado: 'BUENO' },
      { nombre: 'Ruedas', estado: 'MANTENIMIENTO' },
      { nombre: 'Bases', estado: 'BUENO' },
      { nombre: 'Asiento / Espaldar', estado: 'DANADO' },
      { nombre: 'Malla', estado: 'BUENO' },
    ],
  },
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
    return ficha
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
