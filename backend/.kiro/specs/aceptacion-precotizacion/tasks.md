# Implementation Plan: Aceptación de Precotización (HU-15, HU-16)

## Overview

OTP acceptance of a pre-quotation through its public link (HU-15) and the quotation-enablement guard (HU-16), on the existing stack with no schema change. OTP: `secrets` + HMAC-SHA256 keyed by an independent `OTP_SECRET`, stored only as a hash; acceptance consumes the code and lets the existing trigger transition `ENVIADA → ACEPTADA` in one transaction. Attempt/request limits are in-memory with documented, non-persistent limitations.

Tests run against an isolated, disposable PostgreSQL (`TEST_DATABASE_URL`); never the shared Supabase DB. SMTP is faked (no real mail). Writing tests is separated from executing them. All implementation tasks start unchecked. Sequential tests are not concurrency proofs. `conftest.py` is not modified.

Legend: **[now]** implementable now; **[dep]** depends on team decisions / other integrators.

## Block 1 — Existing models, config and OTP service (+ isolated unit tests)  [DONE]

- [x] 1.1 Map the existing verification/acceptance tables  **[now]**
  - Create `app/models/codigo_verificacion.py` (`CodigoVerificacion`) and `app/models/aceptacion_precotizacion.py` (`AceptacionPrecotizacion`) mapping the existing tables unchanged (`id_*` identity + `fecha_aceptacion` default as `FetchedValue`); export both from `app/models/__init__.py` (alphabetical). Inspect types/defaults/nullability/UNIQUE before defining. No ORM table creation, no migration.
  - _Files: app/models/codigo_verificacion.py (new), app/models/aceptacion_precotizacion.py (new), app/models/__init__.py (modify)_
  - _Acceptance: R5.1_
  - _Implemented: both models map the existing tables (verified: schema `mansillas`, columns, `id_*` + `fecha_aceptacion` as FetchedValue, UNIQUE on `aceptacion_precotizacion.id_precotizacion`/`id_codigo`); exported alphabetically. No create_all/migration. App imports OK._
- [x] 1.2 Add OTP config, `.env.example`, and the OTP service  **[now, OTP_SECRET dep]**
  - `app/config.py`: ONLY `otp_secret` is env-configurable (independent, empty default; reject reuse of `JWT_SECRET` and too-short secrets via a controlled error at use time, never at import). The numeric OTP parameters are FIXED constants in `app/services/otp.py` (`OTP_LENGTH=6`, `OTP_TTL_MINUTES=10`, `OTP_REQUEST_INTERVAL_SECONDS=60`, `OTP_MAX_ATTEMPTS=5`, `OTP_MAX_REQUESTS_WINDOW=5`, `OTP_MAX_ATTEMPTS_WINDOW=15`, `OTP_WINDOW_SECONDS=3600`), not env-overridable; secure-config check is the module function `otp_configurado()`. Update `.env.example` with an empty `OTP_SECRET` and a short note on generating a secure secret (no real credentials; do not touch `.env`).
  - `app/services/otp.py`: generate with `secrets` (6-digit ASCII string, leading zeros); `hash_otp` → versioned `v1$nonce$hmac` (HMAC-SHA256 keyed by `OTP_SECRET`, binding pre-quotation id + issuance nonce + code, nonce from `secrets`); `verify_otp` parses the versioned value, recomputes, compares with `hmac.compare_digest`, rejects malformed stored values; raise a controlled error when `OTP_SECRET` is missing/insecure/equal to `JWT_SECRET`; never log/return the plain OTP or the secret. In-memory, thread-safe (`threading.Lock`) store for the 60 s interval, per-issuance attempts (5), cumulative requests (5/h) and cumulative attempts (15/h, not reset by re-issuance); monotonic clock with an injectable time source for deterministic tests; bounded capacity, purge expired, never evict live counters, reject when full; do not derive issue time from `fecha_expiracion`. Documented as non-persistent / not production-grade.
  - _Files: app/config.py (modify), app/services/otp.py (new), .env.example (modify)_
  - _Acceptance: R3.1–R3.4, R1.5, R1.6_
  - _[dep]: a real OTP_SECRET must be provisioned before use._
  - _Implemented: config OTP settings + `.env.example` note; `otp.py` with `generar_otp`/`es_otp_valido`/`hash_otp` (`v1$nonce$hmac`)/`verificar_otp` (compare_digest, malformed→error), controlled error when secret missing/short/equal-JWT, and `ControlAbuso` (threading.Lock, monotonic injectable clock, per-issuance + cumulative window limits, capacity-bounded, purges expired, never evicts live). Documented as non-persistent._
- [x] 1.3 Extend the email helper for TLS-required OTP sends  **[now]**
  - Add an optional keyword `exigir_tls=False` to `enviar_correo`; when true, a non-TLS SMTP config raises `EmailNoConfigurado`. Backward compatible with existing callers.
  - _Files: app/services/email.py (modify)_
  - _Acceptance: R1.8_
  - _Implemented: `enviar_correo(..., *, exigir_tls=False)`; when true and `smtp_tls=False`, raises `EmailNoConfigurado` before connecting (TLS required even without credentials). Backward compatible; keeps `ssl.create_default_context()`; no clear-text fallback._
- [x] 1.4 Unit tests for the OTP service and TLS-required send (written + executed isolated)  **[now]**
  - `tests/test_otp.py`: generation/format, leading zeros, HMAC + compare, missing/insecure secret → controlled error, expiry, attempt/request limits, in-memory cleanup/thread safety, no OTP in outputs. `tests/test_email.py` (extend): `exigir_tls` forces TLS even without credentials.
  - _Files: tests/test_otp.py (new), tests/test_email.py (modify)_
  - _Acceptance: R1.8, R3.1–R3.4_
  - _Executed in true isolation (no DB/SMTP/sleeps, conftest bypassed): `tests/test_otp.py` 21/21 PASS; the 3 new `exigir_tls` cases in `tests/test_email.py` PASS. Thread-safety test runs 8 threads without error (a thread test, NOT a PostgreSQL transactional-concurrency proof)._

Block 1 marked complete (1.1–1.4). HU-15/HU-16 are NOT fully implemented: the OTP request/accept endpoints and the HU-16 guard/endpoint remain (Blocks 2–4), plus integration tests (Block 5).

## Block 2 — OTP request and send, invalidation, abuse controls  [DONE]

- [x] 2.1 Add `POST /propuesta/{token}/otp`  **[now, SMTP dep]**
  - Public; `Cache-Control: no-store` on success AND errors (header set on each `HTTPException`); resolve by token (malformed/unknown or non-`ENVIADA` → indistinguishable 404); `lock_visita` then `db.refresh` + re-check `ENVIADA`; recipient only from stored `correo_cliente` (validated); throttle via `control_abuso.registrar_solicitud` counted BEFORE SMTP (provisional policy, 429 on limit); generate OTP + HMAC (`v1$nonce$hmac`); expire this pre-quotation's previous unused, still-valid codes by setting `fecha_expiracion = func.now()` (DB clock; not employee codes, not other pre-quotations, not marked used); insert `codigo_verificacion` with `fecha_expiracion = func.now() + make_interval(mins=10)`, `utilizado=FALSE`, `correo_destino=correo_cliente`; `db.flush()`; send with `exigir_tls=True`; single commit after a successful send; SMTP failure → full rollback + 502 (previous codes restored in the same transaction); OTP/SMTP not configured/TLS → 503; commit-after-send failure → 500 logged. Returns 202 `{mensaje}`; no OTP/hash/nonce/email/ids in the response or logs.
  - _Files: app/routers/precotizaciones.py (modify)_
  - _Dependencies: app/services/otp.py, app/services/email.py, app/services/precotizacion_rules.py, app/models_
  - _Acceptance: R1.1–R1.8_
  - _Implemented. Correction applied: the endpoint now resolves the token and checks ENVIADA BEFORE the OTP-config 503 (indistinguishable 404). The OTP insert expiry uses the PostgreSQL clock (`func.now()` / `make_interval`, = the trigger's `CURRENT_TIMESTAMP`); the acceptance expiry re-check uses `clock_timestamp()` (actual wall clock, after the lock). Reproducible isolated run: `uv run pytest --noconftest tests/test_otp.py tests/test_email.py -q` → 55 passed (no DB/SMTP). Runtime DB cases in Block 5._

## Block 3 — Transactional OTP acceptance  [DONE]

- [x] 3.1 Add `POST /propuesta/{token}/aceptar`  **[now]**
  - Public; `Cache-Control: no-store` on success AND errors; body parsed locally from `Request` and validated with a strict `AceptarRequest{nombre(1..150), cargo(1..100), codigo:StrictStr}` (`extra=forbid`), so a Pydantic 422 never echoes the code; JSON/size/shape errors → generic 422; the body contract is still published in OpenAPI via `openapi_extra`. Resolve by token (404); `lock_visita` + `db.refresh`; require `ENVIADA` (409, covers already-ACEPTADA/BORRADOR/ANULADA); reject if an acceptance already exists (409); OTP not configured → 503. Deterministically select the most recent valid code for THIS pre-quotation `FOR UPDATE` (unused, not expired by `clock_timestamp()`, `id_empleado` NULL, `correo_destino == stored correo_cliente`); a malformed stored hash → 500 (internal, not counted as a client failure); enforce per-issuance + cumulative attempt limits (429) BEFORE verifying; `verificar_otp` with `compare_digest`; on wrong code record the in-memory failed attempt (survives rollback), do NOT consume/insert/transition, return generic 400. On success: set `utilizado=TRUE` → `db.flush()` → insert `aceptacion_precotizacion` (`correo_aceptante` = stored email) → `db.flush()` (fires the trigger ENVIADA→ACEPTADA) → read `estado`/`fecha_aceptacion` → single commit. `IntegrityError` on the UNIQUE constraints → 409 (concurrent acceptance); other failures → rollback + 500 (uncertain-commit not claimed as "never happened"). Never set `ACEPTADA` manually; no intermediate commit; no quotation created.
  - _Files: app/routers/precotizaciones.py (modify)_
  - _Dependencies: app/services/otp.py, app/services/precotizacion_rules.py, app/models (CodigoVerificacion, AceptacionPrecotizacion, Precotizacion)_
  - _Acceptance: R2.1–R2.8_
  - _Implemented. Static checks: endpoint in OpenAPI (24 routes), `AceptarRequest` body documented (3 required fields, additionalProperties=false) + `AceptacionOut`, app imports. 23 acceptance tests WRITTEN in `tests/test_aceptacion_precotizacion.py` (41 total in the file); DB-backed, NOT executed (need the isolated PostgreSQL)._

## Block 4 — Quotation enablement guard and endpoint (HU-16)  [DONE]

- [x] 4.1 Add the enablement guard and `GET /precotizaciones/{id}/habilitacion-cotizacion`  **[now, cotizacion-endpoints dep]**
  - `cotizacion_habilitada(db, id_precotizacion)` (reusable): true iff the pre-quotation exists, `estado=='ACEPTADA'`, and an acceptance record exists. Endpoint: COMERCIAL only (existing policy, any visit), 404 if the pre-quotation is missing, returns `{habilitado, estado}`. Do not create a quotation. Consult vs. enforce distinction documented.
  - _Files: app/routers/precotizaciones.py (modify), app/services/precotizacion_rules.py (modify)_
  - _Dependencies: app/deps.py, app/models (Precotizacion, AceptacionPrecotizacion)_
  - _Acceptance: R4.1–R4.6_
  - _[dep]: real quotation operations must call the guard; no such endpoints exist yet — module not claimed protected until then._
  - _Implemented in `app/services/precotizacion_rules.py`: single-rule `estado_habilitacion_cotizacion` (one state query + one acceptance query), `cotizacion_habilitada` (consult) and `exigir_cotizacion_habilitada`/`CotizacionNoHabilitada` (enforce). Endpoint `GET /precotizaciones/{id}/habilitacion-cotizacion` (COMERCIAL): 404 if missing, else 200 `{habilitado, estado}`; `ACEPTADA` without a record → `habilitado=false`; read-only (no commit). Static: 25 routes, `HabilitacionOut{habilitado, estado}` in OpenAPI._

## Block 5 — Integration, security and final verification

- [x] 5.1 Integration tests (written and executed; a real transactional-concurrency test remains pending)  **[executed]**
  - `tests/test_aceptacion_precotizacion.py`: OTP request ok; unknown/invalid token; non-allowed states; authorized-recipient only; previous-code invalidation; SMTP failure; acceptance with wrong/expired/used/foreign code; successful acceptance via the real trigger; persistence of nombre/cargo/correo/fecha; rollback on acceptance-insert failure; duplicate-acceptance prevention; concurrent requests with independent connections; enablement across all states; `ACEPTADA` without acceptance record; auth/authorization of the enablement endpoint. SMTP faked.
  - _Files: tests/test_aceptacion_precotizacion.py (new)_
  - _Acceptance: R1, R2, R4, R6_
  - _65 tests in `tests/test_aceptacion_precotizacion.py` — OTP-request, acceptance and HU-16 enablement. Covers success/leak/TLS/expiry/invalidation/isolation/rollback/duplicate/limits/malformed-hash/503/502/500/422 (incl. code-as-number/null/list/object/invalid-JSON/extra-fields), accepted-proposal edit freeze, and the full ENVIADA→accept→ACEPTADA enablement flow. Wrong-OTP tests use deterministic monkeypatched codes (no accidental match); two-issuance tests force distinct codes; `control_abuso` reset per test. EXECUTED against an isolated PostgreSQL: 65/65 PASSED (see 5.2)._
  - _The duplicate-acceptance case here is SEQUENTIAL and is NOT evidence of transactional concurrency safety; a true test with independent connections racing the Visit lock / the same OTP remains pending (see 5.2)._
- [x] 5.2 Execute integration tests  **[dep]**
  - Run `uv run pytest tests/test_aceptacion_precotizacion.py tests/test_precotizaciones.py tests/test_sillas.py tests/test_fotos.py` against an isolated PostgreSQL.
  - _Executed by the developer against an independent Supabase project (not the shared team DB): `tests/test_aceptacion_precotizacion.py` 65/65 PASSED, `tests/test_precotizaciones.py` 68/68, `tests/test_sillas.py` 21/21, `tests/test_fotos.py` 29/29; isolated units `tests/test_otp.py` 34/34, `tests/test_email.py` 21/21. HU-15/HU-16 validated at the integration-test level._
  - _STILL PENDING (not done): a real transactional-concurrency test with independent connections (the shared-session fixtures do not allow it; left unwritten rather than faked), and the end-to-end team integration (accepted-content consistency on routes owned by others, real SMTP/OTP_SECRET, Nicolás's public routes, Esteban's components, guard enforcement in real quotation operations)._
- [x] 5.3 Static and security verification (done to the extent possible without DB)  **[now]**
  - _Executed: syntax OK for all modified files; imports OK (app + test modules); no real undefined names; Pydantic schemas explicit (`OtpResponse`, `AceptarRequest` documented via `openapi_extra`, `AceptacionOut`, `HabilitacionOut`); 25 routes in OpenAPI incl. the three HU-15/HU-16 endpoints; endpoint authorization reviewed (public OTP/accept; COMERCIAL-only enablement); responses carry `Cache-Control: no-store` incl. errors; no OTP/hash/secret in responses; no secret defaults (`otp_secret`/`smtp_password` empty, `otp_configurado()`/`smtp_configurado` False); no external connections. Isolated unit run: `uv run pytest --noconftest tests/test_otp.py tests/test_email.py -q` → 55 passed. PENDING: DB-backed verification (triggers, real transactions) in 5.2; not asserted via mocks._
  - _Acceptance: R1–R6_

## Dependencies / open unknowns (not assumed resolved)
- BUG-A05 (SCRUM-54), BUG-A06 (OTP rejection criteria), CR-01 (SCRUM-65).
- Accepted-content consistency (unguarded routes) — blocking for definitive HU-15 acceptance.
- Real SMTP account; final public routes with Nicolás; proposal content (HU-08/HU-09); guard integration with real quotation operations; persistent OTP limits (schema change, not applied); integration tests pending the isolated PostgreSQL.

## Technical-closure note

- **Swagger/OpenAPI**: `responses` added to the HU-15/HU-16 endpoints with their real codes and `Cache-Control: no-store` documented — OTP request (202/404/429/502/503/500); accept (200/400/404/409/422/429/500/503) with the custom 422 example `{"detail": "Datos de aceptacion invalidos"}`; enablement (401/403/404). `AceptarRequest` body already published via `openapi_extra`. Error bodies are the real `{"detail": "..."}`; no invented codes; logic unchanged.
- **Implementation facts (design/tasks already aligned)**: `OtpResponse{mensaje}`; OTP numeric params are constants in `app/services/otp.py` (only `OTP_SECRET` from env); HU-16 guard in `app/services/precotizacion_rules.py`; bounded body read + synchronous acceptance handler; most-recent-issuance selection re-validated after `FOR UPDATE`.
- **Executed at closure (unit)**: `uv run pytest --noconftest tests/test_otp.py tests/test_email.py -v` -> 55 passed. User manual Swagger checks (5 requests) succeeded, incl. the 3-digit OTP -> 422 without exposing the code and `Cache-Control: no-store` on the 4 public responses.
- **Executed at closure (integration)**: `test_aceptacion_precotizacion.py` -> 65 passed against an isolated, disposable PostgreSQL (independent Supabase project, not the shared/production DB), covering OTP request/throttle/expiry, acceptance transition `ENVIADA -> ACEPTADA`, invalid/expired/reused OTP, and the HU-16 enablement guard. This run surfaced and fixed two naive/aware datetime issues, now resolved with the `clock_timestamp()` read (cast to naive `TIMESTAMP`) and the strictly-past invalidation.
- **STILL PENDING**: the real transactional-concurrency test (two independent DB connections racing on the same acceptance) is NOT covered; the existing sequential duplicate-acceptance test does NOT demonstrate real transactional concurrency. Also pending: accepted-content consistency across unguarded routes, the enforce-side guard integration in real quotation operations, a real SMTP/`OTP_SECRET` in the target environment, and team-integration dependencies (Nicolás public routes, Esteban components). BUG-A05/BUG-A06/CR-01 remain open.
