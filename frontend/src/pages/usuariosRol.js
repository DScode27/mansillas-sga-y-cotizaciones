/* Regla condicional de empresa para el cambio de rol (RF-20, R7).
 *
 * Misma regla que el alta de usuario: los roles de cliente
 * (ADMIN_CLIENTE/EMPLEADO_CLIENTE) exigen `id_empresa`; los roles internos
 * (COMERCIAL_MANSILLAS/TECNICO) lo quieren nulo. Se extrae aquí para que el
 * handler de cambio de rol sea pequeño y verificable sin montar la pantalla.
 */
import { ROLES } from '../auth/roles'

export const ROLES_CLIENTE = [ROLES.ADMIN_CLIENTE, ROLES.EMPLEADO_CLIENTE]

export function rolEsDeCliente(rol) {
  return ROLES_CLIENTE.includes(rol)
}

/* Construye el cuerpo para `asignarRol`. Devuelve `{ error }` cuando un rol de
 * cliente llega sin empresa, o `{ payload }` listo para enviar (con
 * `id_empresa` numérico para cliente y `null` para rol interno). */
export function construirCambioRol({ rol, idEmpresa }) {
  if (rolEsDeCliente(rol)) {
    const valor = String(idEmpresa ?? '').trim()
    if (!valor) {
      return { error: 'Los roles de cliente requieren el ID de empresa.' }
    }
    return { payload: { rol, id_empresa: Number(valor) } }
  }
  return { payload: { rol, id_empresa: null } }
}
