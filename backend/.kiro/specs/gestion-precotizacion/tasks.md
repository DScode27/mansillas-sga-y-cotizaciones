# Implementation Plan: Gestión de Precotización (HU-12, HU-13)

## Overview

Add pre-quotation management on the existing FastAPI + SQLAlchemy backend, no schema change, no new layers. Validation and pre-quotation creation are a single explicit action (`confirmar_validacion: true`). The unique link reuses `precotizacion.token`; email is synchronous SMTP (`smtplib`); the public consult reuses `registrar_acceso`. OTP (HU-15) and the quotation module (HU-16) are out of scope; the component checklist (Esteban) is only consumed if present.

Tests run against an isolated, disposable PostgreSQL (`TEST_DATABASE_URL`), never the shared Supabase DB; SMTP is faked (no real mail). DB-backed tests stay pending execution until an isolated instance is available (same constraint as HU-02/HU-10). No task is complete merely because it was planned.

Legend: **[now]** implementable now; **[dep]** depends on team decisions or other integrators' work.

## Tasks

- [x] 1. HU-12 — Consult and commercial edit of the survey  **[now]**
  - [x] 1.1 Add `GET /visitas/{id_visita}/levantamiento`
    - In `app/routers/precotizaciones.py` (new): COMERCIAL only; load visit (404); return `{visita, sillas:[SillaOut], tiene_precotizacion}`. Internal commercial may read any visit (Davidson's policy); no invented per-empresa restriction. Reuse the `Silla` model / `SillaOut`.
    - _Files: app/routers/precotizaciones.py (new), app/main.py (modify: include router)_
    - _Dependencies: app/deps.py, app/models (Visita, Silla, Precotizacion)_
    - _Acceptance: R1.1–R1.5_
    - _Implemented in `app/routers/precotizaciones.py`; `tiene_precotizacion` derived from an active pre-quotation; chairs ordered by `id_silla`. Static checks: import OK, endpoint in OpenAPI, explicit `LevantamientoOut` schema. Runtime needs DB (task 2.2)._
  - [x] 1.2 Add `PUT /sillas/{id_silla}/comercial`
    - In `app/routers/sillas.py`: COMERCIAL only; load chair (404); lock the chair's `visita` row `FOR UPDATE`; shared guard `_proposal_editable` (409 if the visit's pre-quotation is `ENVIADA`/`ACEPTADA`); update only the explicitly provided fields among `cargo`/`serial_antiguo`/`observaciones` (omitted vs. explicit `null` distinguished); keep immutables; 409 on duplicate `serial_antiguo`. Put the shared guard in a small helper (e.g. `app/services/precotizacion_rules.py`) to avoid circular imports between routers. Do NOT change the technician `PUT /sillas/{id}`.
    - _Files: app/routers/sillas.py (modify)_
    - _Dependencies: app/deps.py, app/models (Silla, Precotizacion, Visita), app/services/precotizacion_rules.py_
    - _Acceptance: R2.1–R2.7, R5.3 (owned route)_
    - _Implemented in `app/routers/sillas.py` (+ `SillaUpdateComercial`); Visit-row lock + `_proposal_editable` guard live in `app/services/precotizacion_rules.py` (no circular import). Omitted vs. explicit fields via `model_dump(exclude_unset=True)`; duplicate serial → 409. Technician `PUT /sillas/{id}` unchanged. Static checks: both PUTs coexist in OpenAPI, app imports clean._

- [x] 2. HU-12 — Tests (2.1 written; 2.2 executed, 68/68)
  - [x] 2.1 Write `tests/test_precotizaciones.py` survey cases
    - Survey read (chairs + `tiene_precotizacion`, empty visit, 404, commercial reads any visit, role 403, unauthenticated 401, `tiene_precotizacion` false for `ANULADA`/true for active); commercial edit (persists the three fields, fresh consult reflects them, omitted fields preserved, immutables unchanged, 404, role 403, duplicate serial 409, allowed in `BORRADOR`, rejected in `ENVIADA`/`ACEPTADA`, technician `PUT` unaffected).
    - _Files: tests/test_precotizaciones.py (new)_
    - _Acceptance: R1, R2, R5.3_
    - _Tests written; statically checked (syntax + no undefined names + module import). Pre-quotation rows inserted via the `db` fixture. EXECUTED against an isolated PostgreSQL: `tests/test_precotizaciones.py` 68/68 PASSED (HU-12 + HU-13 cases; see task 2.2)._
  - [x] 2.2 Execute HU-12 tests
    - `uv run pytest tests/test_precotizaciones.py` against an isolated PostgreSQL.
    - _Executed by the developer against an independent Supabase project: `tests/test_precotizaciones.py` 68/68 PASSED (covers HU-12 and HU-13). HU-12 validated at the integration-test level; end-to-end team integration still pending._

- [x] 3. HU-12/HU-13 — Explicit validation + pre-quotation creation  **[now, ownership dep]**
  - [x] 3.1 Add `POST /precotizaciones`
    - COMERCIAL only; require `confirmar_validacion: true` (422 otherwise); lock the Visit row with `precotizacion_rules.lock_visita` (404 if the visit does not exist); with the lock held, check `precotizacion_rules.precotizacion_activa` and reject (409) if an active one (`BORRADOR`/`ENVIADA`/`ACEPTADA`) exists (`ANULADA` does not block); insert `BORRADOR` with `creada_por=user.id`, `id_empresa`/`id_visita` from the visit, DB-generated `token` and date defaults; same transaction, lock held until commit/rollback; `201 PrecotizacionOut`.
    - _Files: app/routers/precotizaciones.py (modify)_
    - _Dependencies: app/deps.py, app/models (Precotizacion, Visita)_
    - _Acceptance: R3.1–R3.6, R4.1–R4.6_
    - _[dep]: ownership of pre-quotation create to confirm with Davidson._
    - _Implemented in `app/routers/precotizaciones.py` (`PrecotizacionCreate`/`PrecotizacionOut`). Requires `confirmar_validacion is True` (422 otherwise); locks the Visit row then checks `precotizacion_activa` (409, ANULADA allows a new one); `BORRADOR`, `creada_por=user.id`, DB-generated `token`/dates; no email/no ENVIADA. `Precotizacion` model reused as-is (no change needed). Static checks: import OK, route + explicit schemas in OpenAPI._

- [x] 4. HU-13 — Retrieve existing pre-quotations  **[now]**
  - [x] 4.1 Add `GET /precotizaciones?id_visita=`
    - COMERCIAL only; return `[PrecotizacionOut]` for the visit (empty if none). Matches the frontend contract.
    - _Files: app/routers/precotizaciones.py (modify)_
    - _Dependencies: app/deps.py, app/models (Precotizacion)_
    - _Acceptance: R8.1–R8.3_
    - _Implemented; filtered by `id_visita`, ordered by `id_precotizacion`, empty list when none, internal commercial any visit. Discrepancy documented: the backend makes `id_visita` REQUIRED, while Nicolás's `listPrecotizaciones(idVisita)` sends it only when provided (it can call with no filter). For the MVP the portal-comercial flow always passes `id_visita`; a no-filter listing is out of scope here and flagged for coordination._

- [x] 5. HU-13 — SMTP configuration and email helper  **[now, credentials dep]**
  - [x] 5.1 Add SMTP settings and the email helper
    - `app/config.py`: add `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_from`, `smtp_tls`, `smtp_timeout`, and the proposal path (default `/propuesta`). No credentials in source/versioned files. `app/services/email.py` (new): a thin `smtplib` sender building the message and honouring TLS/timeout; raises a domain error on failure. Validate recipient email format (stdlib, no new dependency).
    - _Files: app/config.py (modify), app/services/email.py (new)_
    - _Acceptance: R6.8, R6.12, R9.4_
    - _[dep]: an authorized SMTP account/credentials must be provided before real sending._
    - _Implemented: `app/config.py` SMTP settings + `smtp_configurado`/`proposal_path`; `app/services/email.py` (stdlib `smtplib`+`EmailMessage`): generic `enviar_correo(dest, asunto, cuerpo)` (reusable for HU-15 OTP), `validar_destinatario` (rejects control chars/CRLF injection/multiple recipients/bad format), STARTTLS when configured (no silent downgrade), finite timeout, no secrets logged, `EmailNoConfigurado`/`EmailInvalido`/`EmailEnvioError`. `.env.example` documents the vars (no real credentials). Isolated unit checks executed (fake SMTP): message build, TLS, timeout, missing config, injection rejection._

- [x] 6. HU-13 — Generate and send the unique link  **[now, SMTP dep]**
  - [x] 6.1 Add `POST /precotizaciones/{id}/enviar`
    - COMERCIAL only; validate `correo_cliente` (422); load the pre-quotation (404) and lock its `visita` row `FOR UPDATE` (Visit first); 409 if `ACEPTADA`/`ANULADA`; first send from `BORRADOR` requires `confirmar_validacion: true` (422 otherwise, no email/no state change), resend from `ENVIADA` does not; recipient: first send uses the provided email, resend keeps the stored `correo_cliente` unless explicit authorization; build `{FRONTEND_URL}{proposal_path}/{token}`; send via the helper; on success set `correo_cliente`/`fecha_envio`/`estado='ENVIADA'` and commit; email failure → `502` no change; DB commit failure after send → `500` logged (not unsent). No atomicity promised.
    - _Files: app/routers/precotizaciones.py (modify)_
    - _Dependencies: app/services/email.py, app/deps.py, app/models (Precotizacion)_
    - _Acceptance: R6.1–R6.12_
    - _Implemented: COMERCIAL only; 404 if missing; lock Visit row then `db.refresh(pre)`; 409 on ACEPTADA/ANULADA; first send from BORRADOR requires StrictBool `confirmar_validacion=true` (422 otherwise); resend from ENVIADA reuses token + stored recipient and rejects recipient change (409); link `{FRONTEND_URL}{proposal_path}/{token}`; email then persist ENVIADA/`correo_cliente`/`fecha_envio` (last send); SMTP failure → 502 no transition; missing config → 503; DB failure after send → 500 logged (email not reverted). No retries, no exactly-once claim._

- [x] 7. HU-13 — Public consult and access logging  **[now, route/content dep]**
  - [x] 7.1 Add `GET /propuesta/{token}`
    - Public (no auth); look up by `token`; return only `ENVIADA`/`ACEPTADA` via the explicit `PropuestaPublicaOut` (own visit/empresa only; no other tokens, photos, or personal data); unknown or `BORRADOR`/`ANULADA` → indistinguishable `404`; call `registrar_acceso(db, id_precotizacion, user_agent)` (which commits on its own). No OTP.
    - _Files: app/routers/precotizaciones.py (modify)_
    - _Dependencies: app/routers/accesos.py (`registrar_acceso`), app/models (Precotizacion, Silla, Empresa)_
    - _Acceptance: R7.1–R7.5_
    - _[dep]: public route path `/propuesta/{token}` to confirm with Nicolás; exact proposal content depends on HU-08/HU-09 and Esteban (omit components/photos by default)._
    - _Implemented: public, no auth; malformed/unknown token → 404; only ENVIADA/ACEPTADA (BORRADOR/ANULADA → indistinguishable 404); explicit `PropuestaPublicaOut`/`SillaPublicaOut` (no internal model, no other tokens/photos/personal data); chairs filtered by `id_visita` AND `id_empresa`, ordered by `id_silla`; empresa name via relation; `Cache-Control: no-store`; `registrar_acceso` called only after the proposal is consultable; if logging fails the consult still succeeds (no false "logged"). No OTP._

- [x] 8. HU-13 — Tests (8.1 written; 8.2 executed, 68/68)
  - [x] 8.1 Extend `tests/test_precotizaciones.py` with HU-13 cases
    - Create requires `confirmar_validacion` (422), `BORRADOR`/`creada_por`/DB `token`, second active per visit → 409; list by visit; send success/invalid-email/send-failure(502)/post-send-DB-failure(500)/resend-reuses-token-and-recipient/`ACEPTADA`-`ANULADA`→409; public consult `ENVIADA`/`ACEPTADA`→200 with only own data, `BORRADOR`/`ANULADA`/unknown→404, access logged; email helper unit-tested with a fake sender (TLS/timeout/message), no real mail; concurrency guards (`FOR UPDATE`) where feasible.
    - _Files: tests/test_precotizaciones.py (modify)_
    - _Acceptance: R3, R4, R6, R7, R8_
    - _Written (68 cases in `tests/test_precotizaciones.py`): survey read/edit; create (incl. StrictBool "true"/"yes"/1 → 422); length limits for cargo/serial (100 ok, 101 → 422); list; send first-ok/no-confirm/false/non-bool/invalid-email(422)/SMTP-not-configured(503)/SMTP-failure(502 no transition)/post-send DB failure(500)/404/401/403/resend-same-token-recipient/recipient-change(409)/ACEPTADA-ANULADA(409); public consult ENVIADA + no private fields + Cache-Control, BORRADOR/ANULADA/malformed/unknown → 404, empresa isolation, access logged, access-log-failure still 200. SMTP mocked (no real mail). Sequential tests do NOT prove transactional concurrency. EXECUTED against an isolated PostgreSQL: `tests/test_precotizaciones.py` 68/68 PASSED._
  - [x] 8.2 Execute HU-13 tests
    - `uv run pytest tests/test_precotizaciones.py` against an isolated PostgreSQL.
    - _Executed by the developer against an independent Supabase project: `tests/test_precotizaciones.py` 68/68 PASSED. HU-13 validated at the integration-test level; end-to-end team integration still pending._

- [ ] 9. Integration and security verification (static done; runtime pending)  **[static now / runtime pending]**
  - [x] 9.1 Verify endpoints, contracts and security (static)
    - Confirm routers wired in `app/main.py` and visible in Swagger; the five+one endpoints present in the OpenAPI schema; response schemas match Nicolás's contracts; the public endpoint exposes no other empresa's data, no other tokens, no photos; authorization applied consistently; the shared consistency guard noted for other integrators' routes as a dependency (not implemented). Record executed vs. inspected checks; do not declare validated on appearance alone.
    - _Files: app/main.py, app/routers/precotizaciones.py, app/routers/sillas.py (verify)_
    - _Acceptance: R1, R6, R7, R8, R9_
    - _Static checks executed: syntax, imports (no circular), no undefined names, Pydantic schemas explicit, 22 routes in OpenAPI with the 6 new ones, internal endpoints COMERCIAL-guarded, public endpoint uses `PropuestaPublicaOut`/`SillaPublicaOut` (not the internal model) with no private fields, no secret defaults (`smtp_password=""`, `smtp_configurado=False`), no external connections. Runtime end-to-end over HTTP remains pending the isolated PostgreSQL (tasks 2.2/8.2). HU-12/HU-13 NOT declared fully validated._

## Technical-closure note

- **Swagger/OpenAPI**: `responses` added to the HU-12/HU-13 endpoints documenting real codes — levantamiento (401/403/404); `POST /precotizaciones` (401/403/404/409/422); `GET /precotizaciones` (401/403); enviar (401/403/404/409/422/500/502/503); public consult (200 + 404 with `Cache-Control: no-store`). Error bodies are the real `{"detail": "..."}`; no invented codes; logic/contracts unchanged.
- **Manual Swagger check (by the user)**: `GET /propuesta/<invalid>` -> 404; `POST /propuesta/<invalid>/otp` -> 404; all public responses carried `Cache-Control: no-store`. Consistent with the implementation.
- **Executed (integration)**: `tests/test_precotizaciones.py` **68/68 PASSED** against an isolated Supabase project (not the shared team DB). HU-12/HU-13 validated at the integration-test level.
- **Still pending (team integration)**: accepted-content consistency on routes owned by others, real SMTP account, Nicolás's final public routes, and the guard integration with real quotation operations.
    - _Open unknown: BUG-A05 (SCRUM-54) — no information in the repository; not assumed resolved._
