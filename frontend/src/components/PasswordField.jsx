/* Campo de contraseña con botón para mostrar/ocultar el texto.
 *
 * Reutilizable en login y en el alta de usuarios. Alterna el `type` entre
 * `password` y `text` con un botón "ojo" accesible (`aria-pressed` refleja si la
 * contraseña está visible). Reenvía el resto de props al `<input>` (value,
 * onChange, required, minLength, autoComplete, disabled, name…).
 */
import { useState } from 'react'

export default function PasswordField({ className = 'form-field__input', ...props }) {
  const [visible, setVisible] = useState(false)

  return (
    <span className="password-field">
      <input
        {...props}
        type={visible ? 'text' : 'password'}
        className={className}
      />
      <button
        type="button"
        className="password-field__toggle"
        onClick={() => setVisible((v) => !v)}
        aria-pressed={visible}
        aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
        disabled={props.disabled}
      >
        {visible ? 'Ocultar' : 'Mostrar'}
      </button>
    </span>
  )
}
