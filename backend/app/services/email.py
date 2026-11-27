"""Minimal synchronous SMTP sender (HU-13).

Standard library only (`smtplib` + `email.message`). No external dependency, no
queue/worker, no multi-provider abstraction. The helper is generic
(`enviar_correo(destinatario, asunto, cuerpo)`) so it can be reused later for
HU-15 OTP emails without implementing OTP here.

Safety:
- Missing SMTP config does not break app startup; a send attempt without enough
  config raises `EmailNoConfigurado` (a controlled error), handled by the caller.
- TLS (STARTTLS) is used when configured and is never silently downgraded: if
  STARTTLS fails, the send fails instead of continuing in clear text.
- A finite timeout is always set.
- Recipient is validated (single address, no control characters / header
  injection) before contacting the server.
- Passwords, tokens and message bodies are never logged.
"""

from __future__ import annotations

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.config import settings

# Max length of a client email, matching the DB column `precotizacion.correo_cliente`.
MAX_CORREO = 150

logger = logging.getLogger(__name__)

# Simple, dependency-free address check. Rejects control chars and whitespace
# (which also blocks header injection via CR/LF and multiple recipients).
_PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailError(Exception):
    """Base class for email helper errors."""


class EmailNoConfigurado(EmailError):
    """SMTP configuration is insufficient to send (controlled error)."""


class EmailInvalido(EmailError):
    """The recipient address is invalid or unsafe."""


class EmailEnvioError(EmailError):
    """The SMTP send failed (connection, auth, TLS, timeout, ...)."""


def validar_destinatario(correo: str) -> str:
    """Return the cleaned recipient or raise `EmailInvalido`.

    Conservative, dependency-free check. Rejects control characters BEFORE
    normalizing (so a trailing CRLF cannot be stripped away and hidden),
    multiple addresses, whitespace, over-length values, and anything not
    matching a simple address shape.
    """
    if not isinstance(correo, str):
        raise EmailInvalido("Correo inválido")
    # Reject control chars (incl. CR/LF/tab) on the RAW value, before stripping.
    if any(ord(c) < 32 or ord(c) == 127 for c in correo):
        raise EmailInvalido("Correo con caracteres de control no permitidos")
    valor = correo.strip()
    if not valor:
        raise EmailInvalido("Correo requerido")
    if len(valor) > MAX_CORREO:
        raise EmailInvalido("Correo demasiado largo")
    # A comma or any inner whitespace means multiple recipients / injection.
    if "," in valor or any(c.isspace() for c in valor):
        raise EmailInvalido("Correo con caracteres no permitidos")
    if not _PATRON_CORREO.match(valor):
        raise EmailInvalido("Formato de correo inválido")
    return valor


def _enviar_por_resend(destinatario: str, asunto: str, cuerpo: str) -> None:
    """Send a plain-text email via Resend's HTTP API.

    Used when `RESEND_API_KEY` is configured (preferred on hosts that block
    outbound SMTP ports). Raises `EmailEnvioError` on any transport or API
    error. The API key and message body are never logged.
    """
    try:
        respuesta = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.smtp_from,
                "to": [destinatario],
                "subject": asunto,
                "text": cuerpo,
            },
            timeout=settings.smtp_timeout,
        )
        respuesta.raise_for_status()
    except httpx.HTTPStatusError as error:
        # Resend returns a short, non-sensitive reason in the body (e.g. a
        # restricted sender/recipient in test mode). Log it to aid diagnosis;
        # it contains no API key or message body.
        detalle = error.response.text[:300]
        logger.error(
            "Fallo al enviar correo (Resend) a %s: HTTP %s %s",
            destinatario,
            error.response.status_code,
            detalle,
        )
        raise EmailEnvioError("No fue posible enviar el correo") from error
    except httpx.HTTPError as error:
        logger.error(
            "Fallo al enviar correo (Resend) a %s: %s",
            destinatario,
            type(error).__name__,
        )
        raise EmailEnvioError("No fue posible enviar el correo") from error


def _construir_mensaje(destinatario: str, asunto: str, cuerpo: str) -> EmailMessage:
    mensaje = EmailMessage()
    mensaje["From"] = settings.smtp_from
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)
    return mensaje


def enviar_correo(
    destinatario: str, asunto: str, cuerpo: str, *, exigir_tls: bool = False
) -> None:
    """Send a plain-text email synchronously.

    Raises `EmailNoConfigurado` if SMTP is not configured (or, when
    `exigir_tls=True`, if TLS is disabled), `EmailInvalido` for a bad recipient,
    and `EmailEnvioError` on any SMTP failure. `exigir_tls=True` (used for OTP)
    requires a TLS-protected transport regardless of whether SMTP authenticates,
    and is checked before opening any connection. Existing callers that omit the
    keyword keep their previous behaviour.
    """
    if not settings.smtp_configurado:
        raise EmailNoConfigurado("SMTP no está configurado")

    # Prefer Resend's HTTP API when configured (works where SMTP is blocked).
    # Transport is always TLS (HTTPS), so `exigir_tls` is satisfied.
    if settings.resend_configurado:
        destino = validar_destinatario(destinatario)
        _enviar_por_resend(destino, asunto, cuerpo)
        return

    if exigir_tls and not settings.smtp_tls:
        raise EmailNoConfigurado("Este envío requiere una conexión SMTP con TLS")

    # Timeout must be positive and finite.
    timeout = settings.smtp_timeout
    if not (isinstance(timeout, (int, float)) and timeout > 0 and timeout != float("inf")):
        raise EmailNoConfigurado("SMTP_TIMEOUT debe ser positivo y finito")

    # Inconsistent credentials: one of user/password set without the other.
    if bool(settings.smtp_user) != bool(settings.smtp_password):
        raise EmailNoConfigurado(
            "Configuración SMTP inconsistente: usuario y contraseña deben definirse juntos"
        )

    # Never authenticate over an unprotected connection.
    if settings.smtp_user and not settings.smtp_tls:
        raise EmailNoConfigurado(
            "No se permite autenticación SMTP sin TLS"
        )

    destino = validar_destinatario(destinatario)
    mensaje = _construir_mensaje(destino, asunto, cuerpo)

    try:
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=timeout
        ) as servidor:
            if settings.smtp_tls:
                # Upgrade to TLS with a validated default context; if STARTTLS
                # fails, the exception propagates and we do NOT fall back to
                # clear text.
                contexto = ssl.create_default_context()
                servidor.starttls(context=contexto)
            if settings.smtp_user:
                servidor.login(settings.smtp_user, settings.smtp_password)
            servidor.send_message(mensaje)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as error:
        # Log the error type only; never the password, token, or body.
        logger.error("Fallo al enviar correo a %s: %s", destino, type(error).__name__)
        raise EmailEnvioError("No fue posible enviar el correo") from error
