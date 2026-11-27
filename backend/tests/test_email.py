"""Unit tests for the SMTP email helper (HU-13), fully isolated.

These tests use a fake SMTP client (monkeypatched) and never open a real
connection or send real mail. They do not need PostgreSQL. Note: pytest still
auto-loads `tests/conftest.py`, whose autouse fixtures require an isolated
`TEST_DATABASE_URL`; to run only these in true isolation use a mechanism that
does not load that conftest. They are written here so they run together with the
suite once the isolated database is available.
"""

import pytest

from app.config import settings
from app.services import email as email_service


@pytest.fixture
def smtp_configurado(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "user")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    monkeypatch.setattr(settings, "smtp_from", "no-reply@test")
    monkeypatch.setattr(settings, "smtp_tls", True)
    monkeypatch.setattr(settings, "smtp_timeout", 5.0)


class _FakeSMTP:
    instancias = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls = False
        self.login_args = None
        self.sent = None
        _FakeSMTP.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.tls = True
        self.tls_context = context

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, mensaje):
        self.sent = mensaje


@pytest.fixture
def fake_smtp(monkeypatch):
    _FakeSMTP.instancias.clear()
    monkeypatch.setattr(email_service.smtplib, "SMTP", _FakeSMTP)
    return _FakeSMTP


def test_envio_construye_mensaje(smtp_configurado, fake_smtp):
    email_service.enviar_correo("cliente@example.com", "Asunto", "Cuerpo")

    smtp = fake_smtp.instancias[-1]
    assert smtp.host == "smtp.test"
    assert smtp.port == 587
    assert smtp.timeout == 5.0            # finite timeout
    assert smtp.tls is True               # TLS used
    assert smtp.login_args == ("user", "secret")
    assert smtp.sent["To"] == "cliente@example.com"
    assert smtp.sent["Subject"] == "Asunto"
    assert smtp.sent["From"] == "no-reply@test"
    assert "Cuerpo" in smtp.sent.get_content()


def test_sin_configuracion_error_controlado(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "smtp_from", "")

    with pytest.raises(email_service.EmailNoConfigurado):
        email_service.enviar_correo("a@b.com", "s", "c")


def test_fallo_smtp_se_traduce(smtp_configurado, monkeypatch):
    import smtplib

    class _Falla:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            pass

        def login(self, *a):
            pass

        def send_message(self, m):
            raise smtplib.SMTPException("boom")

    monkeypatch.setattr(email_service.smtplib, "SMTP", _Falla)
    with pytest.raises(email_service.EmailEnvioError):
        email_service.enviar_correo("a@b.com", "s", "c")


@pytest.mark.parametrize(
    "direccion",
    [
        "a@b.com\r\nBcc: otro@x.com",  # header injection via CRLF
        "a@b.com\nSubject: hack",
        "a@b.com, c@d.com",            # multiple recipients
        "a@b.com otro@d.com",          # whitespace
        "sin-arroba",
        "",
        "   ",
        "a@b",                          # no TLD
    ],
)
def test_direcciones_invalidas_rechazadas(direccion):
    with pytest.raises(email_service.EmailInvalido):
        email_service.validar_destinatario(direccion)


def test_direccion_valida_se_limpia():
    assert email_service.validar_destinatario("  cliente@example.com  ") == "cliente@example.com"


def test_direccion_demasiado_larga_rechazada():
    larga = ("x" * 150) + "@e.com"  # > 150 chars
    with pytest.raises(email_service.EmailInvalido):
        email_service.validar_destinatario(larga)


def test_tls_usa_contexto_ssl(smtp_configurado, fake_smtp, monkeypatch):
    """STARTTLS is called with an ssl context (create_default_context)."""
    import ssl

    recibido = {}

    def _starttls(self, context=None):
        recibido["context"] = context
        self.tls = True

    monkeypatch.setattr(_FakeSMTP, "starttls", _starttls, raising=False)
    # Record what create_default_context returns to compare identity.
    contexto_real = ssl.create_default_context()
    monkeypatch.setattr(email_service.ssl, "create_default_context", lambda: contexto_real)

    email_service.enviar_correo("cliente@example.com", "s", "c")

    assert isinstance(recibido.get("context"), ssl.SSLContext)
    assert recibido["context"] is contexto_real


def test_fallo_starttls_no_degrada(smtp_configurado, monkeypatch):
    """If STARTTLS fails, the send fails (no clear-text fallback)."""
    import smtplib

    class _NoTLS:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            raise smtplib.SMTPException("starttls not supported")

        def login(self, *a):
            raise AssertionError("login must not be reached without TLS")

        def send_message(self, m):
            raise AssertionError("send must not be reached without TLS")

    monkeypatch.setattr(email_service.smtplib, "SMTP", _NoTLS)
    with pytest.raises(email_service.EmailEnvioError):
        email_service.enviar_correo("cliente@example.com", "s", "c")


def test_auth_sin_tls_rechazada(smtp_configurado, monkeypatch):
    """Authentication is refused over a non-TLS connection."""
    monkeypatch.setattr(settings, "smtp_tls", False)
    # user/password are set (from smtp_configurado) → auth would be attempted.
    with pytest.raises(email_service.EmailNoConfigurado):
        email_service.enviar_correo("cliente@example.com", "s", "c")


def test_config_credenciales_inconsistente(smtp_configurado, monkeypatch):
    """User set without password (or vice versa) → controlled error."""
    monkeypatch.setattr(settings, "smtp_password", "")
    with pytest.raises(email_service.EmailNoConfigurado):
        email_service.enviar_correo("cliente@example.com", "s", "c")


def test_timeout_invalido_rechazado(smtp_configurado, monkeypatch):
    for malo in (0, -1, float("inf")):
        monkeypatch.setattr(settings, "smtp_timeout", malo)
        with pytest.raises(email_service.EmailNoConfigurado):
            email_service.enviar_correo("cliente@example.com", "s", "c")


def test_exigir_tls_con_tls_habilitado(smtp_configurado, fake_smtp):
    """exigir_tls=True with TLS enabled sends normally."""
    email_service.enviar_correo("cliente@example.com", "s", "c", exigir_tls=True)
    assert fake_smtp.instancias[-1].tls is True


def test_exigir_tls_sin_tls_sin_credenciales(monkeypatch, fake_smtp):
    """exigir_tls=True with TLS disabled and NO credentials is rejected before
    opening a connection."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "no-reply@test")
    monkeypatch.setattr(settings, "smtp_user", "")      # no credentials
    monkeypatch.setattr(settings, "smtp_password", "")
    monkeypatch.setattr(settings, "smtp_tls", False)    # TLS disabled

    with pytest.raises(email_service.EmailNoConfigurado):
        email_service.enviar_correo("cliente@example.com", "s", "c", exigir_tls=True)
    # No SMTP instance was created (rejected before connecting).
    assert fake_smtp.instancias == []


@pytest.fixture
def resend_configurado(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(settings, "smtp_from", "no-reply@test")
    monkeypatch.setattr(settings, "smtp_timeout", 5.0)


def test_resend_envia_por_http_sin_smtp(resend_configurado, fake_smtp, monkeypatch):
    """With Resend configured, send goes over HTTP and never opens SMTP."""
    llamadas = {}

    class _Resp:
        def raise_for_status(self):
            llamadas["raised"] = True

    def _post(url, headers=None, json=None, timeout=None):
        llamadas["url"] = url
        llamadas["headers"] = headers
        llamadas["json"] = json
        llamadas["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(email_service.httpx, "post", _post)

    email_service.enviar_correo("cliente@example.com", "Asunto", "Cuerpo")

    assert llamadas["url"] == "https://api.resend.com/emails"
    assert llamadas["headers"]["Authorization"] == "Bearer re_test_key"
    assert llamadas["json"]["from"] == "no-reply@test"
    assert llamadas["json"]["to"] == ["cliente@example.com"]
    assert llamadas["json"]["subject"] == "Asunto"
    assert llamadas["json"]["text"] == "Cuerpo"
    assert llamadas["timeout"] == 5.0
    assert fake_smtp.instancias == []  # SMTP never opened


def test_resend_error_http_se_traduce(resend_configurado, monkeypatch):
    """A Resend HTTP error maps to EmailEnvioError (controlled)."""
    import httpx

    def _post(*a, **k):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(email_service.httpx, "post", _post)
    with pytest.raises(email_service.EmailEnvioError):
        email_service.enviar_correo("cliente@example.com", "s", "c")


def test_resend_destinatario_invalido_rechazado(resend_configurado):
    """Recipient validation still applies on the Resend path."""
    with pytest.raises(email_service.EmailInvalido):
        email_service.enviar_correo("a@b.com\r\nBcc: x@y.com", "s", "c")


def test_exigir_tls_default_retrocompatible(monkeypatch, fake_smtp):
    """Without exigir_tls (HU-13 callers), a no-credentials non-TLS send still works."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "no-reply@test")
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")
    monkeypatch.setattr(settings, "smtp_tls", False)
    monkeypatch.setattr(settings, "smtp_timeout", 5.0)

    email_service.enviar_correo("cliente@example.com", "s", "c")   # no exception
    assert len(fake_smtp.instancias) == 1
