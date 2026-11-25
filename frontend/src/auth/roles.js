/* Roles del sistema (los 4 del SQL).
 *
 * Fuente única de los nombres de rol para evitar strings sueltos en guards y
 * navegación. Inician sesión por usuario/contraseña COMERCIAL_MANSILLAS,
 * TECNICO y ADMIN_CLIENTE; EMPLEADO_CLIENTE solo entra por el flujo QR+OTP
 * (fuera de mi alcance).
 */
export const ROLES = {
  COMERCIAL_MANSILLAS: 'COMERCIAL_MANSILLAS',
  TECNICO: 'TECNICO',
  ADMIN_CLIENTE: 'ADMIN_CLIENTE',
  EMPLEADO_CLIENTE: 'EMPLEADO_CLIENTE',
}
