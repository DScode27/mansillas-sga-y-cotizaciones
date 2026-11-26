/* Lightbox: modal accesible para ver una foto a tamaño grande.
 *
 * Se abre al hacer clic en una miniatura (en las tarjetas de silla y en la vista
 * pública por QR). Cierra con Esc, clic en el overlay o el botón de cerrar, y
 * atrapa el foco mientras está abierto para no perderlo tras el modal. No crea
 * ni revoca object URLs: solo muestra la `url` que recibe; la gestión de la
 * memoria sigue a cargo de quien creó la URL.
 */
import { useEffect, useRef } from 'react'

export default function Lightbox({ url, alt = '', onClose }) {
  const cerrarRef = useRef(null)

  // Cierre con Escape y foco inicial en el botón de cerrar. El listener se
  // limpia al desmontar o al cambiar el handler.
  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    cerrarRef.current?.focus()
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  if (!url) return null

  return (
    <div
      className="lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={alt || 'Vista ampliada de la foto'}
      onClick={onClose}
    >
      <div className="lightbox__contenido" onClick={(e) => e.stopPropagation()}>
        <button
          ref={cerrarRef}
          type="button"
          className="lightbox__cerrar"
          onClick={onClose}
          aria-label="Cerrar"
        >
          ×
        </button>
        <img className="lightbox__img" src={url} alt={alt} />
      </div>
    </div>
  )
}
