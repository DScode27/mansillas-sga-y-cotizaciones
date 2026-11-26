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

  // `SillaOut` no incluye `sugerir_cambio` ni el estado de los componentes (eso
  // lo expone el checklist, vía `vista_estado_mantenimiento`). Las pantallas
  // pintan la insignia `sugerir_cambio` y, en el portal comercial, los
  // componentes a cambiar (DANADO). Por eso enriquecemos cada silla con su
  // checklist. Es N+1 acotado al número de sillas de la visita (pocas por
  // levantamiento); si crece, el backend debería devolver ambos en el listado.
  // Una silla sin checklist aún guardado degrada a `sugerir_cambio=false` y
  // `componentes=[]` sin romper la lista.
  const enriquecidas = await Promise.all(
    data.map(async (silla) => {
      // Componentes y fotos se piden en paralelo; cualquiera que falle degrada a
      // su valor vacío sin romper la fila (la silla sin checklist/fotos aún se
      // lista). Las fotos aquí son solo la lista de ids; las imágenes se bajan
      // bajo demanda al expandir el detalle (`getFotoSillaUrl`).
      const [resComp, resFotos] = await Promise.allSettled([
        getComponentes(silla.id_silla),
        listFotosSilla(silla.id_silla),
      ])
      const componentes =
        resComp.status === 'fulfilled' ? (resComp.value.items ?? []) : []
      const sugerir_cambio =
        resComp.status === 'fulfilled' ? resComp.value.sugerir_cambio : false
      const fotos = resFotos.status === 'fulfilled' ? resFotos.value : []
      return { ...silla, componentes, sugerir_cambio, fotos }
    }),
  )
  return enriquecidas
}

/* Lista las fotos de una silla (GET /sillas/{id}/fotos, autenticado).
 *
 * Devuelve [{ id_fotografia, id_silla, ruta_archivo, nombre_archivo,
 * fecha_subida }] (FotografiaOut). Solo se usa el `id_fotografia` para luego
 * bajar la imagen con `getFotoSillaUrl`. En mock devuelve las fotos del store. */
export async function listFotosSilla(idSilla) {
  if (USE_MOCK.sillas) {
    const silla = sillasMock.find((s) => s.id_silla === Number(idSilla))
    return silla?.fotos ?? []
  }
  const { data } = await apiClient.get(FOTOS_ENDPOINT(idSilla))
  return data
}

/* Baja una foto de una silla y devuelve un object URL para mostrarla
 * (GET /sillas/{id}/fotos/{id_fotografia}, autenticado, `responseType: blob`).
 *
 * Quien la use debe revocar el object URL al desmontar/colapsar para no filtrar
 * memoria. En mock, la foto del store ya guarda una URL local (createObjectURL
 * en `uploadFotoSilla`), que se devuelve tal cual. */
export async function getFotoSillaUrl(idSilla, idFotografia) {
  if (USE_MOCK.sillas) {
    const silla = sillasMock.find((s) => s.id_silla === Number(idSilla))
    const foto = silla?.fotos?.find((f) => f.id_fotografia === idFotografia)
    return foto?.ruta_archivo ?? ''
  }
  const { data } = await apiClient.get(
    `${FOTOS_ENDPOINT(idSilla)}/${idFotografia}`,
    { responseType: 'blob' },
  )
  return URL.createObjectURL(data)
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
  // Contrato del backend real (POST /visitas/{id_visita}/sillas): solo acepta
  // estos cuatro campos. La empresa, sede y departamento los deduce el servidor
  // del empleado; el codigo_qr/token_publico los genera la BD. El estado de los
  // componentes se persiste aparte con PUT /sillas/{id}/componentes (ver abajo),
  // y las fotos con POST /sillas/{id}/fotos; todo tras crear la silla.
  const payload = {
    id_empleado: Number(id_empleado),
    cargo: cargo.trim(),
    serial_antiguo: serial_antiguo?.trim() || null,
    observaciones: observaciones?.trim() || null,
  }

  if (USE_MOCK.sillas) {
    const numero = proximoQrMock++
    const silla = {
      id_silla: proximoIdMock++,
      id_empresa: Number(id_empresa),
      id_visita: Number(id_visita),
      id_sede: Number(id_sede),
      id_departamento: Number(id_departamento),
      numero_qr: numero,
      codigo_qr: `SIC-${String(numero).padStart(8, '0')}`,
      token_publico: `mock-token-${numero}`,
      estado: 'REGISTRADA',
      fecha_registro: new Date().toISOString(),
      fotos: [],
      componentes: componentes.map((c) => ({
        id_componente: c.id_componente,
        estado: c.estado,
        observacion: c.observacion?.trim() || null,
      })),
      ...payload,
    }
    sillasMock.push(silla)
    return conDerivados(silla)
  }

  // 1) Crea la silla (SillaCreadaOut: id_silla, codigo_qr, token_publico…).
  const { data: silla } = await apiClient.post(
    `/visitas/${Number(id_visita)}/sillas`,
    payload,
  )

  // 2) Persiste el checklist de componentes. El backend exige el checklist
  //    COMPLETO (los 5 componentes) con estados válidos y devuelve la
  //    `sugerir_cambio` ya calculada en la BD, que combinamos en la respuesta
  //    para que la pantalla muestre la insignia sin recalcular.
  const checklist = await guardarComponentes(silla.id_silla, componentes)

  return { ...silla, sugerir_cambio: checklist.sugerir_cambio }
}

/* Guarda el estado de los componentes de una silla (PUT /sillas/{id}/componentes).
 *
 * El backend valida que el checklist esté completo (los 5 componentes) y que
 * cada estado sea uno de ESTADOS_COMPONENTE; responde con los items guardados y
 * `sugerir_cambio` (según `vista_estado_mantenimiento`). En mock actualiza el
 * store y recalcula la sugerencia localmente. */
export async function guardarComponentes(idSilla, componentes) {
  const items = componentes.map((c) => ({
    id_componente: c.id_componente,
    estado: c.estado,
    observacion: c.observacion?.trim() || null,
  }))

  if (USE_MOCK.sillas) {
    const silla = sillasMock.find((s) => s.id_silla === Number(idSilla))
    if (silla) silla.componentes = items
    return {
      id_silla: Number(idSilla),
      items,
      sugerir_cambio: calcularSugerirCambio(items),
    }
  }

  const { data } = await apiClient.put(`/sillas/${idSilla}/componentes`, { items })
  return data
}

/* Lee el checklist de componentes de una silla (GET /sillas/{id}/componentes). */
export async function getComponentes(idSilla) {
  if (USE_MOCK.sillas) {
    const silla = sillasMock.find((s) => s.id_silla === Number(idSilla))
    const items = silla?.componentes ?? []
    return {
      id_silla: Number(idSilla),
      items,
      sugerir_cambio: calcularSugerirCambio(items),
    }
  }
  const { data } = await apiClient.get(`/sillas/${idSilla}/componentes`)
  return data
}

/* Trae una silla por su id (GET /sillas/{id_silla}). */
export async function getSilla(idSilla) {
  if (USE_MOCK.sillas) {
    const silla = sillasMock.find((s) => s.id_silla === Number(idSilla))
    if (!silla) {
      throw { response: { status: 404 } }
    }
    return conDerivados(silla)
  }
  const { data } = await apiClient.get(`/sillas/${idSilla}`)
  return data
}

/* Actualiza los datos editables de una silla (PUT /sillas/{id_silla}).
 *
 * El backend solo deja cambiar `serial_antiguo` y `observaciones`; responde 409
 * si el serial queda duplicado en la empresa, conflicto que el mock imita. */
export async function updateSilla(idSilla, cambios) {
  const payload = {}
  if ('serial_antiguo' in cambios) {
    payload.serial_antiguo = cambios.serial_antiguo?.trim() || null
  }
  if ('observaciones' in cambios) {
    payload.observaciones = cambios.observaciones?.trim() || null
  }

  if (USE_MOCK.sillas) {
    const silla = sillasMock.find((s) => s.id_silla === Number(idSilla))
    if (!silla) {
      throw { response: { status: 404 } }
    }
    if (
      payload.serial_antiguo &&
      sillasMock.some(
        (s) =>
          s.id_silla !== silla.id_silla &&
          s.id_empresa === silla.id_empresa &&
          s.serial_antiguo === payload.serial_antiguo,
      )
    ) {
      throw { response: { status: 409 } }
    }
    Object.assign(silla, payload)
    return conDerivados(silla)
  }
  const { data } = await apiClient.put(`/sillas/${idSilla}`, payload)
  return data
}

/* Subida de fotos de una silla (R8).
 *
 * Endpoint real: POST /sillas/{id_silla}/fotos (multipart, campo `archivo`),
 * una foto por llamada; devuelve `FotografiaOut`. En mock genera una URL local
 * temporal (`URL.createObjectURL`) para previsualizar; quien la use debe
 * revocarla al desmontar. */
const FOTOS_ENDPOINT = (idSilla) => `/sillas/${idSilla}/fotos`

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

  // `Content-Type: undefined` deja que el navegador fije el multipart con su
  // boundary; el default `application/json` del `apiClient` rompería la subida.
  const formData = new FormData()
  formData.append('archivo', archivo)
  const { data } = await apiClient.post(FOTOS_ENDPOINT(id_silla), formData, {
    headers: { 'Content-Type': undefined },
  })
  return data
}
