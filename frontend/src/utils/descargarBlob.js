/* Descarga de un `Blob` como archivo en el navegador.
 *
 * Patrón compartido por las pantallas que bajan archivos generados por el
 * backend (PDF de QR en RF-05, exportación de inventario en RF-11). Centraliza
 * el truco del objeto URL + `<a download>` sintético para no repetirlo en cada
 * vista y asegurar que la URL temporal siempre se revoca.
 *
 * No toca la red: recibe un `Blob` ya resuelto y solo dispara la descarga.
 */

/* Dispara la descarga de `blob` con el nombre de archivo indicado.
 *
 * Crea un objeto URL a partir del blob, simula un clic sobre un enlace
 * `<a download>` para que el navegador guarde el archivo y revoca la URL en un
 * `finally` para no dejar recursos colgando aunque algo falle. */
export function descargarBlob(blob, nombreArchivo) {
  const url = URL.createObjectURL(blob)
  try {
    const enlace = document.createElement('a')
    enlace.href = url
    enlace.download = nombreArchivo
    document.body.appendChild(enlace)
    enlace.click()
    enlace.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}
