/* API de sillas y su levantamiento (recurso de otro dev, mockeable).
 *
 * Mismo patrón que `visitas.js`/`empleados.js`: con `USE_MOCK.sillas` en `true`
 * trabaja sobre un store en memoria; en `false` pega al backend real sin tocar
 * las pantallas. Cubre el levantamiento móvil (R8, HU-28): registrar una silla
 * dentro de una visita con el estado de sus 5 componentes y subir fotos.
 *
 * Reglas del SQL que respetamos aquí:
 *   - `codigo_qr` lo genera la BD (SIC-00000001…); al crear se envía '' y el
 *     mock simula el consecutivo.
 *   - El estado de cada componente es uno de BUENO/MANTENIMIENTO/DANADO/NO_APLICA.
 *   - `sugerir_cambio` replica `vista_estado_mantenimiento`: TRUE cuando más del
 *     70% de los componentes que aplican están DANADO.
 *
 * El listado acepta `id_visita` para pedir solo las sillas de esa visita; el
 * aislamiento real por empresa lo impone el backend según el usuario (R4).
 */
import { apiClient } from './client'
import { USE_MOCK } from './mocks'

// Catálogo de componentes del SQL (tabla `componente`, insert inicial).
export const COMPONENTES = [
  { id_componente: 1, nombre: 'Cilindros' },
  { id_componente: 2, nombre: 'Ruedas' },
  { id_componente: 3, nombre: 'Bases' },
  { id_componente: 4, nombre: 'Asiento / Espaldar' },
  { id_componente: 5, nombre: 'Malla' },
]

// Estados posibles de un componente (CHECK de `silla_componente`).
export const ESTADOS_COMPONENTE = ['BUENO', 'MANTENIMIENTO', 'DANADO', 'NO_APLICA']

/* Calcula `sugerir_cambio` igual que `vista_estado_mantenimiento`:
 * ignora los NO_APLICA y sugiere cambio si los DANADO superan el 70% de los
 * componentes que sí aplican. Sin componentes que apliquen → FALSE. */
export function calcularSugerirCambio(componentes) {
  const aplican = componentes.filter((c) => c.estado !== 'NO_APLICA')
  if (aplican.length === 0) return false
  const danados = aplican.filter((c) => c.estado === 'DANADO').length
  return danados / aplican.length > 0.7
}

// Store en memoria para el mock. Se reinicia al recargar.
const sillasMock = []
let proximoIdMock = 1
let proximoQrMock = 1

function conDerivados(silla) {
  // El backend real expone `sugerir_cambio` desde la vista; en mock lo
  // calculamos a partir de los componentes para que la UI lo muestre igual.
  return { ...silla, sugerir_cambio: calcularSugerirCambio(silla.componentes) }
}

export async function listSillas(idVisita) {
  if (USE_MOCK.sillas) {
    const filtradas =
      idVisita == null || idVisita === ''
        ? sillasMock
        : sillasMock.filter((s) => s.id_visita === Number(idVisita))
    return filtradas.map(conDerivados)
  }
  const { data } = await apiClient.get('/sillas', {
    params: idVisita ? { id_visita: idVisita } : undefined,
  })
  return data
}

export async function createSilla({
  id_empresa,
  id_visita,
  id_sede,
  id_departamento,
  id_empleado,
  cargo,
  serial_antiguo,
  observaciones,
  componentes,
}) {
  const payload = {
    id_empresa: Number(id_empresa),
    id_visita: Number(id_visita),
    id_sede: Number(id_sede),
    id_departamento: Number(id_departamento),
    id_empleado: Number(id_empleado),
    cargo: cargo.trim(),
    serial_antiguo: serial_antiguo?.trim() || null,
    observaciones: observaciones?.trim() || null,
    // El código QR lo genera la BD: se envía '' para que el trigger lo asigne.
    codigo_qr: '',
    componentes: componentes.map((c) => ({
      id_componente: c.id_componente,
      estado: c.estado,
      observacion: c.observacion?.trim() || null,
    })),
  }

  if (USE_MOCK.sillas) {
    const numero = proximoQrMock++
    const silla = {
      id_silla: proximoIdMock++,
      numero_qr: numero,
      codigo_qr: `SIC-${String(numero).padStart(8, '0')}`,
      token_publico: `mock-token-${numero}`,
      estado: 'REGISTRADA',
      fecha_registro: new Date().toISOString(),
      fotos: [],
      ...payload,
    }
    sillasMock.push(silla)
    return conDerivados(silla)
  }

  const { data } = await apiClient.post('/sillas', payload)
  return data
}

/* Subida de fotos de una silla (R8).
 *
 * El backend real guarda el archivo en almacenamiento y registra la ruta en
 * `fotografia`. En mock generamos una URL local temporal (`URL.createObjectURL`)
 * para previsualizar sin backend; quien la use debe revocarla al desmontar.
 */
export async function uploadFotoSilla({ id_silla, archivo }) {
  if (USE_MOCK.sillas) {
    const silla = sillasMock.find((s) => s.id_silla === Number(id_silla))
    const foto = {
      id_fotografia: Date.now(),
      ruta_archivo: URL.createObjectURL(archivo),
      nombre_archivo: archivo.name,
      fecha_subida: new Date().toISOString(),
    }
    if (silla) silla.fotos.push(foto)
    return foto
  }

  const formData = new FormData()
  formData.append('archivo', archivo)
  const { data } = await apiClient.post(`/sillas/${id_silla}/fotos`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}
