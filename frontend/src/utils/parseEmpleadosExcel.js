/* Parseo de la plantilla de empleados (Excel/CSV) en el navegador, con SheetJS.
 *
 * Lee la primera hoja, toma la fila de encabezados y mapea cada columna a los
 * campos de `empleado` del SQL. Devuelve filas válidas (listas para enviar) y
 * errores por fila para la previsualización (R6: mostrar antes de registrar).
 * No toca la red: solo transforma el archivo a datos revisables.
 *
 * SheetJS (`xlsx`) es pesado, así que se carga de forma diferida (import
 * dinámico): solo entra al bundle cuando el usuario importa un archivo, no en
 * la carga inicial de la app.
 *
 * Encabezados aceptados (sin distinguir mayúsculas/acentos):
 *   nombre, documento, correo, cargo, sede (id), departamento (id)
 */

// Sinónimos de encabezado → campo interno. Se normaliza el encabezado antes de
// buscar aquí, así que basta con cubrir las variantes razonables.
const ALIAS_COLUMNA = {
  nombre: 'nombre',
  nombres: 'nombre',
  documento: 'documento',
  cedula: 'documento',
  identificacion: 'documento',
  correo: 'correo',
  email: 'correo',
  'correo electronico': 'correo',
  cargo: 'cargo',
  rol: 'cargo',
  sede: 'id_sede',
  'id sede': 'id_sede',
  id_sede: 'id_sede',
  departamento: 'id_departamento',
  area: 'id_departamento',
  'id departamento': 'id_departamento',
  id_departamento: 'id_departamento',
}

function normalizar(texto) {
  return String(texto ?? '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // quita acentos
    .replace(/\s+/g, ' ')
}

function mapearEncabezados(encabezados) {
  const mapa = {}
  encabezados.forEach((bruto, indice) => {
    const campo = ALIAS_COLUMNA[normalizar(bruto)]
    if (campo && !(campo in mapa)) {
      mapa[campo] = indice
    }
  })
  return mapa
}

function validarFila(fila, numeroFila) {
  const errores = []
  if (!fila.nombre) errores.push('falta nombre')
  if (!fila.cargo) errores.push('falta cargo')
  if (!fila.id_sede) errores.push('falta sede')
  if (!fila.id_departamento) errores.push('falta departamento')
  return errores.length ? { fila: numeroFila, motivos: errores } : null
}

/* Lee un File y devuelve { columnasFaltantes, validas, errores }.
 * Lanza Error con mensaje legible si el archivo no se puede interpretar. */
export async function parseEmpleadosExcel(file) {
  const XLSX = await import('xlsx')
  const buffer = await file.arrayBuffer()

  let libro
  try {
    libro = XLSX.read(buffer, { type: 'array' })
  } catch {
    throw new Error('No se pudo leer el archivo. ¿Es un Excel o CSV válido?')
  }

  const hoja = libro.Sheets[libro.SheetNames[0]]
  if (!hoja) {
    throw new Error('El archivo no tiene ninguna hoja con datos.')
  }

  // `header: 1` → matriz de filas; la primera es el encabezado.
  const matriz = XLSX.utils.sheet_to_json(hoja, { header: 1, blankrows: false })
  if (matriz.length < 2) {
    throw new Error('El archivo no tiene filas de empleados bajo el encabezado.')
  }

  const mapa = mapearEncabezados(matriz[0])
  const REQUERIDAS = { nombre: 'nombre', cargo: 'cargo', id_sede: 'sede', id_departamento: 'departamento' }
  const columnasFaltantes = Object.entries(REQUERIDAS)
    .filter(([campo]) => !(campo in mapa))
    .map(([, etiqueta]) => etiqueta)

  if (columnasFaltantes.length) {
    return { columnasFaltantes, validas: [], errores: [] }
  }

  const valor = (celda, indice) =>
    indice == null ? '' : String(celda[indice] ?? '').trim()

  const validas = []
  const errores = []

  matriz.slice(1).forEach((celda, i) => {
    const numeroFila = i + 2 // +1 por el encabezado, +1 para base 1 (fila de Excel)
    const fila = {
      nombre: valor(celda, mapa.nombre),
      documento: valor(celda, mapa.documento) || null,
      correo: valor(celda, mapa.correo) || null,
      cargo: valor(celda, mapa.cargo),
      id_sede: Number(valor(celda, mapa.id_sede)) || null,
      id_departamento: Number(valor(celda, mapa.id_departamento)) || null,
    }

    const error = validarFila(fila, numeroFila)
    if (error) {
      errores.push(error)
    } else {
      validas.push(fila)
    }
  })

  return { columnasFaltantes: [], validas, errores }
}
