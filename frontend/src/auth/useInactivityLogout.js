/* Temporizador de inactividad de la sesión (HU-25, R2).
 *
 * Mientras hay sesión, reinicia un contador cada vez que el usuario interactúa
 * (ratón, teclado, scroll, toque). Si pasan los minutos configurados sin
 * actividad, cierra la sesión y redirige a /login con un aviso.
 *
 * Es solo la capa de UX: el backend ya expira la sesión por inactividad y
 * responde 401 en la siguiente petición. Este temporizador evita que una
 * pestaña abierta y ociosa quede con sesión visible.
 *
 * El límite sale de `VITE_INACTIVITY_MINUTES` (default 30), consistente con
 * `SESSION_INACTIVITY_MINUTES` del backend.
 */
import { useEffect, useRef } from 'react'

const DEFAULT_MINUTES = 30

const minutes = Number(import.meta.env.VITE_INACTIVITY_MINUTES) || DEFAULT_MINUTES
const TIMEOUT_MS = minutes * 60 * 1000

// Eventos que cuentan como "actividad" del usuario.
const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart']

export function useInactivityLogout(isAuthenticated, onTimeout) {
  // Guardamos el callback en una ref para no reinstalar los listeners cada
  // render cuando cambia la identidad de la función. La ref se actualiza en un
  // efecto (no durante el render) para seguir las reglas de hooks.
  const onTimeoutRef = useRef(onTimeout)

  useEffect(() => {
    onTimeoutRef.current = onTimeout
  }, [onTimeout])

  useEffect(() => {
    if (!isAuthenticated) {
      return undefined
    }

    let timerId

    function reset() {
      clearTimeout(timerId)
      timerId = setTimeout(() => onTimeoutRef.current(), TIMEOUT_MS)
    }

    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, reset, { passive: true })
    }
    reset() // arranca el contador al montar con sesión

    return () => {
      clearTimeout(timerId)
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, reset)
      }
    }
  }, [isAuthenticated])
}
