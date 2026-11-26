/* Tarjeta de una silla levantada, compartida por Levantamiento y Portal
 * comercial (P2).
 *
 * Muestra el código QR, la insignia de estado (`sugerir_cambio`), el cargo, el
 * estado de los componentes y, de forma expandible, las fotos de la silla. Las
 * imágenes se bajan bajo demanda al expandir (patrón "contador + cargar al
 * expandir"): `getFotoSillaUrl` devuelve object URLs que se revocan al colapsar
 * o al desmontar, para no filtrar memoria.
 *
 * El `extra` opcional se renderiza bajo el cargo (p. ej. "Componentes a cambiar"
 * del portal comercial), para no duplicar el manejo de fotos entre pantallas.
 */
import { useEffect, useRef, useState } from 'react'
import { getFotoSillaUrl } from '../api/sillas'
import Lightbox from './Lightbox'

const ESTADO_COMPONENTE_LABEL = {
  BUENO: 'Bueno',
  MANTENIMIENTO: 'Mantenimiento',
  DANADO: 'Dañado',
  NO_APLICA: 'No aplica',
}

const ESTADO_COMPONENTE_BADGE = {
  BUENO: 'badge--ok',
  MANTENIMIENTO: 'badge--alerta',
  DANADO: 'badge--alerta',
  NO_APLICA: 'badge--off',
}

export default function SillaCard({ silla, extra = null }) {
  const [expandida, setExpandida] = useState(false)
  const [fotos, setFotos] = useState([])
  const [cargandoFotos, setCargandoFotos] = useState(false)
  const [errorFotos, setErrorFotos] = useState('')
  // Foto abierta en el lightbox (su url) o null.
  const [fotoAmpliada, setFotoAmpliada] = useState(null)
  // Object URLs vivos, para revocarlos al colapsar o desmontar.
  const urlsRef = useRef([])

  const componentes = silla.componentes ?? []
  const numFotos = silla.fotos?.length ?? 0

  function revocarUrls() {
    urlsRef.current.forEach((u) => {
      if (u.startsWith('blob:')) URL.revokeObjectURL(u)
    })
    urlsRef.current = []
  }

  // Revoca los object URLs al desmontar la tarjeta.
  useEffect(() => revocarUrls, [])

  async function toggleFotos() {
    if (expandida) {
      setExpandida(false)
      setFotos([])
      setFotoAmpliada(null)
      revocarUrls()
      return
    }
    setExpandida(true)
    if (numFotos === 0) return
    setCargandoFotos(true)
    setErrorFotos('')
    try {
      const cargadas = []
      for (const foto of silla.fotos) {
        const url = await getFotoSillaUrl(silla.id_silla, foto.id_fotografia)
        urlsRef.current.push(url)
        cargadas.push({ id: foto.id_fotografia, url })
      }
      setFotos(cargadas)
    } catch {
      setErrorFotos('No se pudieron cargar las fotos.')
    } finally {
      setCargandoFotos(false)
    }
  }

  return (
    <li className="sillas-lista__item">
      <div className="sillas-lista__cabecera">
        <span className="sillas-lista__qr">{silla.codigo_qr}</span>
        {silla.sugerir_cambio ? (
          <span className="badge badge--alerta">Sugerir cambio</span>
        ) : (
          <span className="badge badge--ok">En buen estado</span>
        )}
      </div>

      <p className="sillas-lista__cargo">{silla.cargo}</p>

      {extra}

      {componentes.length > 0 && (
        <ul className="sillas-lista__componentes-estado">
          {componentes.map((c) => (
            <li
              key={c.id_componente ?? c.nombre}
              className="sillas-lista__componente"
            >
              <span>{c.nombre}</span>
              <span
                className={`badge ${ESTADO_COMPONENTE_BADGE[c.estado] ?? 'badge--off'}`}
              >
                {ESTADO_COMPONENTE_LABEL[c.estado] ?? c.estado}
              </span>
            </li>
          ))}
        </ul>
      )}

      {numFotos > 0 && (
        <div className="sillas-lista__fotos-bloque">
          <button
            className="btn btn--ghost"
            type="button"
            onClick={toggleFotos}
            aria-expanded={expandida}
          >
            {expandida
              ? 'Ocultar fotos'
              : `Ver ${numFotos} foto${numFotos === 1 ? '' : 's'}`}
          </button>

          {expandida && cargandoFotos && (
            <p className="state-text">Cargando fotos…</p>
          )}
          {expandida && errorFotos && (
            <p className="form-error" role="alert">
              {errorFotos}
            </p>
          )}
          {expandida && !cargandoFotos && !errorFotos && fotos.length > 0 && (
            <ul className="sillas-lista__fotos-grid">
              {fotos.map((f) => (
                <li key={f.id}>
                  <button
                    type="button"
                    className="foto-thumb-btn"
                    onClick={() => setFotoAmpliada(f.url)}
                    aria-label={`Ampliar foto ${f.id} de ${silla.codigo_qr}`}
                  >
                    <img
                      src={f.url}
                      alt={`Foto ${f.id} de ${silla.codigo_qr}`}
                      className="sillas-lista__foto-thumb"
                    />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {fotoAmpliada && (
        <Lightbox
          url={fotoAmpliada}
          alt={`Foto de ${silla.codigo_qr}`}
          onClose={() => setFotoAmpliada(null)}
        />
      )}
    </li>
  )
}
