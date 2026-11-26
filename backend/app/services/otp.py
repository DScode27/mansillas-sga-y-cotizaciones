"""OTP generation, hashing/verification and in-memory abuse control (HU-15).

Standard library only (`secrets`, `hmac`, `hashlib`). The plain OTP is returned
to the caller only so it can be emailed; it is never stored or logged. Only a
versioned HMAC representation `v1$nonce$hmac` is persisted in
`codigo_verificacion.codigo_hash`.

Cryptography:
- Code: `secrets`, exactly `OTP_LENGTH` ASCII digits (leading zeros preserved).
- Hash: HMAC-SHA256 keyed by an independent `OTP_SECRET`, binding the
  pre-quotation id, a per-issuance random nonce, and the code.
- Stored representation: `v1$<32-hex-nonce>$<64-hex-hmac>`, strictly validated.
- Verify: parse + recompute + `hmac.compare_digest`. Malformed → `OtpFormatoError`.
- `OTP_SECRET` is read from the environment; it must not equal `JWT_SECRET` and
  must be long enough. Missing/insecure → `OtpConfigError` (controlled), never a
  default. The secret is never logged or placed in exception messages.

The OTP numeric parameters below are fixed, documented MVP constants (not
env-overridable); only the secret comes from configuration.

Abuse control is in memory (thread-safe, bounded, self-purging, monotonic
clock). Documented limitations: non-persistent, lost on restart, not shared
across processes/instances; NOT sufficient protection for public production.
`threading.Lock` makes single operations atomic; it does NOT provide
transactional concurrency — the acceptance flow must additionally hold the
Visit-row lock across check+verify+record.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections.abc import Callable

from app.config import settings

# --- Fixed MVP constants (not env-overridable) ------------------------------
OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
OTP_REQUEST_INTERVAL_SECONDS = 60
OTP_MAX_ATTEMPTS = 5            # failed attempts per issuance
OTP_MAX_REQUESTS_WINDOW = 5     # requests per pre-quotation within the window
OTP_MAX_ATTEMPTS_WINDOW = 15    # cumulative failed attempts within the window
OTP_WINDOW_SECONDS = 3600       # window for the cumulative limits

_VERSION = "v1"
_MIN_SECRET_LEN = 32
_MAX_ENTRADAS = 10_000          # documented capacity per in-memory dict
_NONCE_BYTES = 16               # → 32 hex chars
_RE_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_RE_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class OtpConfigError(Exception):
    """OTP_SECRET is missing, too short, or equal to JWT_SECRET (controlled)."""


class OtpFormatoError(Exception):
    """A stored `codigo_hash` representation, or an input value, is malformed."""


class OtpLimiteError(Exception):
    """An abuse limit or capacity was reached (interval / attempts / window)."""


def otp_configurado() -> bool:
    """True when a secure, independent OTP_SECRET is configured."""
    try:
        _secreto()
        return True
    except OtpConfigError:
        return False


def _secreto() -> bytes:
    secreto = settings.otp_secret or ""
    if not secreto or len(secreto) < _MIN_SECRET_LEN:
        raise OtpConfigError("OTP_SECRET ausente o demasiado corto")
    if settings.jwt_secret and secreto == settings.jwt_secret:
        raise OtpConfigError("OTP_SECRET no debe ser igual a JWT_SECRET")
    return secreto.encode("utf-8")


def generar_otp() -> str:
    """Return a fresh OTP of exactly `OTP_LENGTH` ASCII digits."""
    numero = secrets.randbelow(10**OTP_LENGTH)
    return f"{numero:0{OTP_LENGTH}d}"


def es_otp_valido(codigo: object) -> bool:
    """True when `codigo` is exactly `OTP_LENGTH` ASCII digits (no unicode digits)."""
    return (
        isinstance(codigo, str)
        and len(codigo) == OTP_LENGTH
        and codigo.isascii()
        and codigo.isdigit()
    )


def _exigir_otp_valido(codigo: object) -> str:
    if not es_otp_valido(codigo):
        raise OtpFormatoError("Código con formato inválido")
    return codigo  # type: ignore[return-value]


def _mensaje(id_precotizacion: int, nonce: str, codigo: str) -> bytes:
    # Unambiguous, length-prefixed binding of the fields.
    partes = (str(id_precotizacion), nonce, codigo)
    return "|".join(f"{len(p)}:{p}" for p in partes).encode("utf-8")


def hash_otp(id_precotizacion: int, codigo: str) -> str:
    """Return `v1$nonce$hmac` binding the pre-quotation, a new nonce and the code.

    Raises `OtpFormatoError` if `codigo` is not a valid OTP and `OtpConfigError`
    if the secret is missing/insecure.
    """
    _exigir_otp_valido(codigo)
    nonce = secrets.token_hex(_NONCE_BYTES)
    mac = hmac.new(_secreto(), _mensaje(id_precotizacion, nonce, codigo), hashlib.sha256)
    return f"{_VERSION}${nonce}${mac.hexdigest()}"


def _parsear(codigo_hash: object) -> tuple[str, str]:
    """Strictly parse `v1$nonce$hmac`; return (nonce, hmac) or raise."""
    if not isinstance(codigo_hash, str) or not codigo_hash.isascii():
        raise OtpFormatoError("codigo_hash inválido")
    partes = codigo_hash.split("$")
    if len(partes) != 3:
        raise OtpFormatoError("codigo_hash con formato inesperado")
    version, nonce, mac = partes
    if version != _VERSION or not _RE_HEX32.match(nonce) or not _RE_HEX64.match(mac):
        raise OtpFormatoError("codigo_hash con formato inesperado")
    return nonce, mac


def extraer_nonce(codigo_hash: str) -> str:
    """Return the issuance nonce of a valid stored representation (safe parser)."""
    return _parsear(codigo_hash)[0]


def verificar_otp(codigo_hash: str, id_precotizacion: int, codigo: object) -> bool:
    """Verify `codigo` against a stored `v1$nonce$hmac`.

    Raises `OtpFormatoError` for a malformed stored value or an invalid code.
    """
    nonce, esperado = _parsear(codigo_hash)
    codigo_ok = _exigir_otp_valido(codigo)
    calculado = hmac.new(
        _secreto(), _mensaje(id_precotizacion, nonce, codigo_ok), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(calculado, esperado)


# --- In-memory abuse control ------------------------------------------------

class ControlAbuso:
    """Thread-safe, in-memory request/attempt limiter (non-persistent).

    Per pre-quotation: a last-request time, a sliding window of request
    timestamps, and a sliding window of failed-attempt timestamps (cumulative).
    Per issuance `(id_precotizacion, nonce)`: a failed-attempt count plus a
    retention time so it can be purged. A monotonic clock is used, injectable
    for tests. Live counters are never evicted to admit new ones; when a dict is
    at capacity with nothing to free, the operation is rejected.
    """

    def __init__(self, reloj: Callable[[], float] | None = None) -> None:
        self._reloj = reloj or time.monotonic
        self._lock = threading.Lock()
        # id_precotizacion -> {"solicitudes": [ts], "fallos": [ts], "ultima": ts|None}
        self._pre: dict[int, dict] = {}
        # (id_precotizacion, nonce) -> {"count": int, "retener_hasta": ts}
        self._emision: dict[tuple[int, str], dict] = {}

    def _purgar(self, ahora: float) -> None:
        ventana = float(OTP_WINDOW_SECONDS)
        muertas_pre = []
        for pre, datos in self._pre.items():
            datos["solicitudes"] = [t for t in datos["solicitudes"] if ahora - t < ventana]
            datos["fallos"] = [t for t in datos["fallos"] if ahora - t < ventana]
            ultima = datos["ultima"]
            sin_actividad = (
                not datos["solicitudes"]
                and not datos["fallos"]
                and (ultima is None or ahora - ultima >= ventana)
            )
            if sin_actividad:
                muertas_pre.append(pre)
        for pre in muertas_pre:
            self._pre.pop(pre, None)

        muertas_em = [k for k, v in self._emision.items() if ahora >= v["retener_hasta"]]
        for k in muertas_em:
            self._emision.pop(k, None)

    def registrar_solicitud(self, id_precotizacion: int) -> None:
        """Enforce the interval and cumulative request limit, then record one."""
        with self._lock:
            ahora = self._reloj()
            self._purgar(ahora)
            datos = self._pre.get(id_precotizacion)
            if datos is None:
                if len(self._pre) >= _MAX_ENTRADAS:
                    raise OtpLimiteError("Capacidad de control de OTP alcanzada")
                datos = {"solicitudes": [], "fallos": [], "ultima": None}
                self._pre[id_precotizacion] = datos
            ultima = datos["ultima"]
            if ultima is not None and ahora - ultima < OTP_REQUEST_INTERVAL_SECONDS:
                raise OtpLimiteError("Debe esperar antes de solicitar otro código")
            if len(datos["solicitudes"]) >= OTP_MAX_REQUESTS_WINDOW:
                raise OtpLimiteError("Demasiadas solicitudes de código")
            datos["solicitudes"].append(ahora)
            datos["ultima"] = ahora

    def verificar_intentos(self, id_precotizacion: int, nonce: str) -> None:
        """Raise if this issuance or the cumulative window is over its limit."""
        with self._lock:
            ahora = self._reloj()
            self._purgar(ahora)
            em = self._emision.get((id_precotizacion, nonce))
            if em is not None and em["count"] >= OTP_MAX_ATTEMPTS:
                raise OtpLimiteError("Demasiados intentos para este código")
            datos = self._pre.get(id_precotizacion)
            if datos and len(datos["fallos"]) >= OTP_MAX_ATTEMPTS_WINDOW:
                raise OtpLimiteError("Demasiados intentos fallidos")

    def registrar_fallo(self, id_precotizacion: int, nonce: str) -> None:
        """Record a failed attempt; cap per-issuance growth and respect capacity."""
        with self._lock:
            ahora = self._reloj()
            self._purgar(ahora)
            clave = (id_precotizacion, nonce)
            em = self._emision.get(clave)
            if em is None:
                if len(self._emision) >= _MAX_ENTRADAS:
                    raise OtpLimiteError("Capacidad de control de OTP alcanzada")
                em = {"count": 0, "retener_hasta": ahora + OTP_WINDOW_SECONDS}
                self._emision[clave] = em
            # Do not grow unbounded once the per-issuance cap is reached.
            if em["count"] < OTP_MAX_ATTEMPTS:
                em["count"] += 1
            em["retener_hasta"] = ahora + OTP_WINDOW_SECONDS

            datos = self._pre.get(id_precotizacion)
            if datos is None:
                if len(self._pre) >= _MAX_ENTRADAS:
                    raise OtpLimiteError("Capacidad de control de OTP alcanzada")
                datos = {"solicitudes": [], "fallos": [], "ultima": None}
                self._pre[id_precotizacion] = datos
            # Cap the cumulative failure list so it cannot grow without bound.
            if len(datos["fallos"]) < OTP_MAX_ATTEMPTS_WINDOW:
                datos["fallos"].append(ahora)


# Process-wide singleton used by the endpoints (Block 2/3).
control_abuso = ControlAbuso()
