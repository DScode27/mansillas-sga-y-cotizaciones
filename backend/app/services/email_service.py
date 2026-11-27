"""Envío del OTP por correo (HU-24).

El `.env` actual no define SMTP, así que el envío se abstrae tras el `Protocol`
`EmailSender`. En desarrollo (`settings.smtp_host` vacío) se usa `LogEmailSender`,
que escribe el código al logger en lugar de enviar un correo real; cuando hay
`smtp_host` configurado, `get_email_sender()` devuelve `SmtpEmailSender`, que
envía por SMTP usando los settings de `app/config.py`.

El router inyecta el sender vía `Depends(get_email_sender)`, lo que permite
sustituirlo por un *fake* en pruebas (`app.dependency_overrides`).
"""

from __future__ import annotations

import logging
from typing import Protocol

from ..config import settings
from .email import enviar_correo

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    """Interfaz de envío del OTP; cualquier implementación la satisface."""

    def enviar_codigo(self, correo: str, codigo: str) -> None:
        """Envía (o registra) el código de verificación al destinatario."""
        ...


class LogEmailSender:
    """Modo desarrollo: escribe el código al logger, sin tocar SMTP.

    Pensado para entornos sin SMTP configurado: el código queda en los logs
    (nivel INFO) para poder completar el flujo de OTP durante el desarrollo.
    """

    def enviar_codigo(self, correo: str, codigo: str) -> None:
        logger.info("OTP para %s: %s (modo desarrollo, no se envió correo)", correo, codigo)


class SmtpEmailSender:
    """Envío real por SMTP usando los settings de `app/config.py`.

    Se instancia solo cuando `settings.smtp_host` está configurado. Usa STARTTLS
    y autentica con `smtp_user`/`smtp_password` únicamente si hay usuario.
    """

    def enviar_codigo(self, correo: str, codigo: str) -> None:
        cuerpo = (
            "Mansillas SIC\n\n"
            "Para enviar tu ticket de soporte, usa este código de "
            "verificación:\n\n"
            f"    {codigo}\n\n"
            f"El código caduca en {settings.otp_ttl_minutes} minutos. No lo "
            "compartas con nadie.\n"
            "Si tú no solicitaste este código, ignora este mensaje."
        )
        # Reuse the shared sender (`email.py`), which prefers Resend's HTTP API
        # when configured and falls back to SMTP otherwise.
        enviar_correo(correo, "Tu código de verificación - Mansillas SIC", cuerpo)


def get_email_sender() -> EmailSender:
    """Dependencia FastAPI: envío real si hay SMTP o Resend; si no, log."""
    if settings.smtp_configurado:
        return SmtpEmailSender()
    return LogEmailSender()
