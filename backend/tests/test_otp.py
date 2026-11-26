"""Isolated unit tests for the OTP service (HU-15). No DB, no SMTP, no sleeps.

Note: pytest auto-loads `tests/conftest.py`, whose autouse fixtures require an
isolated `TEST_DATABASE_URL`. These tests touch no database; to run them in true
isolation, execute them with a mechanism that does not load that conftest.
"""

import pytest

from app.config import settings
from app.services import otp


@pytest.fixture(autouse=True)
def _secreto_otp(monkeypatch):
    # Only the secret is configurable from the environment; the numeric OTP
    # parameters are fixed module constants in app.services.otp.
    monkeypatch.setattr(settings, "otp_secret", "s" * 48)
    monkeypatch.setattr(settings, "jwt_secret", "jwt-distinto-suficientemente-largo-xxxxx")


# --- Cryptography -----------------------------------------------------------

def test_genera_seis_digitos():
    for _ in range(50):
        c = otp.generar_otp()
        assert len(c) == 6 and c.isascii() and c.isdigit()


def test_conserva_ceros_iniciales(monkeypatch):
    monkeypatch.setattr(otp.secrets, "randbelow", lambda n: 7)
    assert otp.generar_otp() == "000007"


def test_formato_codigo():
    assert otp.es_otp_valido("000123")
    assert not otp.es_otp_valido("12345")      # too short
    assert not otp.es_otp_valido("1234567")    # too long
    assert not otp.es_otp_valido("12a456")     # non-digit
    assert not otp.es_otp_valido("١٢٣٤٥٦")      # unicode digits, not ASCII


def test_verificacion_correcta():
    c = otp.generar_otp()
    h = otp.hash_otp(10, c)
    assert otp.verificar_otp(h, 10, c) is True


def test_codigo_incorrecto():
    h = otp.hash_otp(10, "123456")
    assert otp.verificar_otp(h, 10, "654321") is False


def test_precotizacion_diferente():
    c = otp.generar_otp()
    h = otp.hash_otp(10, c)
    assert otp.verificar_otp(h, 11, c) is False


def test_emision_diferente_nonce_distinto():
    c = "123456"
    h1 = otp.hash_otp(10, c)
    h2 = otp.hash_otp(10, c)
    assert h1.split("$")[1] != h2.split("$")[1]   # different nonce
    assert h1 != h2
    assert otp.verificar_otp(h1, 10, c) and otp.verificar_otp(h2, 10, c)


def test_representacion_invalida():
    for malo in ("", "bad", "v1$only", "v2$nonce$hmac", "v1$$hmac", "v1$nonce$"):
        with pytest.raises(otp.OtpFormatoError):
            otp.verificar_otp(malo, 10, "123456")


def test_secreto_ausente(monkeypatch):
    monkeypatch.setattr(settings, "otp_secret", "")
    with pytest.raises(otp.OtpConfigError):
        otp.hash_otp(1, "123456")


def test_secreto_insuficiente(monkeypatch):
    monkeypatch.setattr(settings, "otp_secret", "corto")
    with pytest.raises(otp.OtpConfigError):
        otp.hash_otp(1, "123456")


def test_secreto_igual_jwt(monkeypatch):
    monkeypatch.setattr(settings, "otp_secret", "m" * 48)
    monkeypatch.setattr(settings, "jwt_secret", "m" * 48)
    with pytest.raises(otp.OtpConfigError):
        otp.hash_otp(1, "123456")


def test_representacion_estructural():
    """Deterministic structural check of the stored representation (not probabilistic)."""
    h = otp.hash_otp(10, "135791")
    version, nonce, mac = h.split("$")
    assert version == "v1"
    assert len(nonce) == 32 and all(c in "0123456789abcdef" for c in nonce)
    assert len(mac) == 64 and all(c in "0123456789abcdef" for c in mac)


def test_extraer_nonce():
    h = otp.hash_otp(10, "135791")
    assert otp.extraer_nonce(h) == h.split("$")[1]
    with pytest.raises(otp.OtpFormatoError):
        otp.extraer_nonce("v1$bad$short")


def test_nonce_hmac_formatos_invalidos():
    bad_nonce = "v1$" + ("z" * 32) + "$" + ("a" * 64)      # non-hex nonce
    short_nonce = "v1$" + ("a" * 10) + "$" + ("a" * 64)    # wrong nonce length
    bad_mac = "v1$" + ("a" * 32) + "$" + ("a" * 10)        # wrong hmac length
    for malo in (bad_nonce, short_nonce, bad_mac):
        with pytest.raises(otp.OtpFormatoError):
            otp.verificar_otp(malo, 10, "135791")


def test_hmac_unicode_rechazado():
    unicode_rep = "v1$" + ("a" * 32) + "$" + ("á" * 64)
    with pytest.raises(otp.OtpFormatoError):
        otp.verificar_otp(unicode_rep, 10, "135791")


def test_hash_otp_rechaza_codigo_invalido():
    for malo in ("12345", "1234567", "12a456", "١٢٣٤٥٦", 123456):
        with pytest.raises(otp.OtpFormatoError):
            otp.hash_otp(10, malo)


def test_verificar_otp_rechaza_codigo_invalido():
    h = otp.hash_otp(10, "123456")
    for malo in ("12345", "12a456", "١٢٣٤٥٦"):
        with pytest.raises(otp.OtpFormatoError):
            otp.verificar_otp(h, 10, malo)


def test_otp_configurado(monkeypatch):
    assert otp.otp_configurado() is True
    monkeypatch.setattr(settings, "otp_secret", "")
    assert otp.otp_configurado() is False


# --- Abuse control (in-memory, injected monotonic clock) --------------------

class _Reloj:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avanzar(self, s):
        self.t += s


def _control():
    return otp.ControlAbuso(reloj=_Reloj())


def test_intervalo_60s():
    reloj = _Reloj()
    c = otp.ControlAbuso(reloj=reloj)
    c.registrar_solicitud(1)
    with pytest.raises(otp.OtpLimiteError):
        c.registrar_solicitud(1)           # too soon
    reloj.avanzar(60)
    c.registrar_solicitud(1)               # allowed after the interval


def test_limite_acumulado_solicitudes():
    reloj = _Reloj()
    c = otp.ControlAbuso(reloj=reloj)
    for _ in range(otp.OTP_MAX_REQUESTS_WINDOW):
        c.registrar_solicitud(1)
        reloj.avanzar(60)
    with pytest.raises(otp.OtpLimiteError):
        c.registrar_solicitud(1)           # cumulative request cap


def test_intentos_por_emision():
    c = _control()
    for _ in range(otp.OTP_MAX_ATTEMPTS):
        c.registrar_fallo(1, "nonceA")
    with pytest.raises(otp.OtpLimiteError):
        c.verificar_intentos(1, "nonceA")


def test_limite_acumulado_intentos():
    c = _control()
    # spread across several issuances so per-issuance cap is not the trigger
    for i in range(otp.OTP_MAX_ATTEMPTS_WINDOW):
        c.registrar_fallo(1, f"nonce{i}")
    with pytest.raises(otp.OtpLimiteError):
        c.verificar_intentos(1, "nonceZ")


def test_nueva_emision_no_reinicia_acumulado():
    c = _control()
    for i in range(otp.OTP_MAX_ATTEMPTS_WINDOW):
        c.registrar_fallo(1, f"nonce{i}")
    # A brand-new issuance must still be blocked by the cumulative limit.
    with pytest.raises(otp.OtpLimiteError):
        c.verificar_intentos(1, "nonce-nuevo")


def test_recuperacion_tras_ventana():
    reloj = _Reloj()
    c = otp.ControlAbuso(reloj=reloj)
    for i in range(otp.OTP_MAX_ATTEMPTS_WINDOW):
        c.registrar_fallo(1, f"nonce{i}")
    reloj.avanzar(otp.OTP_WINDOW_SECONDS + 1)
    c.verificar_intentos(1, "nonce-post")   # window elapsed → allowed


def test_limpieza_entradas_expiradas():
    reloj = _Reloj()
    c = otp.ControlAbuso(reloj=reloj)
    c.registrar_solicitud(1)
    reloj.avanzar(otp.OTP_WINDOW_SECONDS + otp.OTP_REQUEST_INTERVAL_SECONDS + 1)
    # purge happens on the next operation for another pre-quotation
    c.registrar_solicitud(2)
    assert 1 not in c._pre


def test_capacidad_no_elimina_vigentes(monkeypatch):
    monkeypatch.setattr(otp, "_MAX_ENTRADAS", 2)
    reloj = _Reloj()
    c = otp.ControlAbuso(reloj=reloj)
    c.registrar_solicitud(1)
    c.registrar_solicitud(2)
    with pytest.raises(otp.OtpLimiteError):
        c.registrar_solicitud(3)           # full, nothing expired to free


def test_limpieza_emision():
    """Issuance counters are purged once their retention elapses."""
    reloj = _Reloj()
    c = otp.ControlAbuso(reloj=reloj)
    c.registrar_fallo(1, "nonceA")
    assert (1, "nonceA") in c._emision
    reloj.avanzar(otp.OTP_WINDOW_SECONDS + 1)
    c.registrar_fallo(2, "nonceB")   # triggers purge
    assert (1, "nonceA") not in c._emision


def test_conserva_emision_vigente():
    reloj = _Reloj()
    c = otp.ControlAbuso(reloj=reloj)
    c.registrar_fallo(1, "nonceA")
    reloj.avanzar(10)
    c.registrar_fallo(2, "nonceB")
    assert (1, "nonceA") in c._emision   # still within retention


def test_capacidad_emision(monkeypatch):
    monkeypatch.setattr(otp, "_MAX_ENTRADAS", 2)
    c = _control()
    c.registrar_fallo(1, "n1")
    c.registrar_fallo(2, "n2")
    with pytest.raises(otp.OtpLimiteError):
        c.registrar_fallo(3, "n3")   # emision dict full, nothing to free


def test_registrar_fallo_no_crece_ilimitado():
    """Once the per-issuance cap is reached, the counter does not grow further."""
    c = _control()
    for _ in range(OTP_MAX := otp.OTP_MAX_ATTEMPTS):
        c.registrar_fallo(1, "nonceA")
    for _ in range(100):
        c.registrar_fallo(1, "nonceA")
    assert c._emision[(1, "nonceA")]["count"] == otp.OTP_MAX_ATTEMPTS


def test_fallos_acumulados_acotados():
    """The cumulative failure list does not grow beyond the window cap."""
    c = _control()
    for i in range(otp.OTP_MAX_ATTEMPTS_WINDOW + 50):
        c.registrar_fallo(1, f"n{i}")
    assert len(c._pre[1]["fallos"]) <= otp.OTP_MAX_ATTEMPTS_WINDOW


def test_reloj_inicia_en_cero():
    """A monotonic clock starting at 0 must not be treated as 'no previous request'."""
    class _Cero:
        def __init__(self): self.t = 0.0
        def __call__(self): return self.t
        def avanzar(self, s): self.t += s

    reloj = _Cero()
    c = otp.ControlAbuso(reloj=reloj)
    c.registrar_solicitud(1)          # records at t=0
    with pytest.raises(otp.OtpLimiteError):
        c.registrar_solicitud(1)      # still within 60 s, must be rejected


def test_concurrencia_misma_emision():
    import threading

    c = _control()
    errores = []

    def worker():
        try:
            for _ in range(100):
                c.registrar_fallo(7, "nonce-comun")
        except Exception as e:  # noqa: BLE001
            errores.append(e)

    hilos = [threading.Thread(target=worker) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []
    # Capped regardless of the concurrent increments.
    assert c._emision[(7, "nonce-comun")]["count"] == otp.OTP_MAX_ATTEMPTS


def test_seguridad_hilos():
    import threading

    c = _control()
    errores = []

    def worker(pre):
        try:
            for i in range(50):
                c.registrar_fallo(pre, f"n{i}")
        except Exception as e:  # noqa: BLE001
            errores.append(e)

    hilos = [threading.Thread(target=worker, args=(h,)) for h in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert errores == []   # no crash / race under concurrent access
