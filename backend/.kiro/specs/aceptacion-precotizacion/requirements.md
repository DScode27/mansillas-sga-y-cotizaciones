# Requirements Document

## Introduction

This feature lets a client accept a pre-quotation through its public link by verifying identity with a one-time code (OTP) sent to the stored client email (HU-15), and enables the quotation operations for a Comercial only after that acceptance (HU-16). It builds on the existing Mansillas SIC backend (FastAPI + SQLAlchemy over the `mansillas` schema), reusing the pre-quotation `token`, the public proposal endpoint, the SMTP helper, the access log, and the database acceptance/quotation triggers. No schema change.

HU-15: request + verify OTP and record the acceptance. HU-16: gate quotation operations behind an accepted pre-quotation.

### Existing functionality reused (not re-implemented)
- Public proposal endpoint `GET /propuesta/{token}` and the `Precotizacion` model (`token`, `estado`, `correo_cliente`, `fecha_aceptacion`).
- SMTP helper `app/services/email.py` (`enviar_correo`, `validar_destinatario`). Note: it currently enforces TLS only for authentication and MAY send without TLS when no credentials are configured. A minimal, backward-compatible extension (an optional `exigir_tls` parameter) is added so OTP sends require TLS regardless of whether SMTP authenticates.
- Shared lock/consistency rules `app/services/precotizacion_rules.py` (`lock_visita`, `precotizacion_activa`, `propuesta_congelada`).
- Business RBAC `app/deps.py` (`get_current_user`, `require_role`).
- `registrar_acceso` access logging.

### Database guarantees reused (verified against `database/SQLMansillasSIC.sql`)
- `codigo_verificacion`: `id_precotizacion` (FK, nullable per the CHECK), `correo_destino`, `codigo_hash` (TEXT), `fecha_expiracion`, `utilizado` (bool, default FALSE). CHECK: exactly one of `id_precotizacion` / `id_empleado`.
- `aceptacion_precotizacion`: `id_precotizacion` **UNIQUE**, `id_codigo` **UNIQUE**, `nombre_aceptante`, `cargo_aceptante`, `correo_aceptante`, `fecha_aceptacion`.
- Trigger `registrar_aceptacion_precotizacion` (BEFORE INSERT on `aceptacion_precotizacion`): requires a `codigo_verificacion` row for the same pre-quotation with `utilizado = TRUE` and not expired, then sets `precotizacion.estado = 'ACEPTADA'` only when it was `ENVIADA` (raises otherwise). The backend must NOT set `ACEPTADA` manually.
- Trigger `impedir_edicion_precotizacion_aceptada`: blocks UPDATE/DELETE of an `ACEPTADA` pre-quotation row.
- `cotizacion`: `id_precotizacion` **UNIQUE**; trigger `validar_cotizacion_tras_aceptacion` blocks INSERT/UPDATE unless the pre-quotation is `ACEPTADA`.

### New functionality (this spec)
- Models for `codigo_verificacion` and `aceptacion_precotizacion` (mapping existing tables, no schema change).
- An OTP request endpoint and an acceptance endpoint on the public link.
- A reusable quotation-enablement guard and a read endpoint reporting it.

### Pending decisions (resolved in design, not assumed here)
- OTP security parameters are **provisional MVP values** (documented constants, not unnecessarily configurable), not official criteria, and need team approval: OTP length (6 digits), expiry (10 minutes), minimum interval between OTP requests (60 s), maximum failed attempts per issuance (5), cumulative requests per pre-quotation (5 / hour), cumulative failed attempts per pre-quotation (15 / hour), and invalidation of previous codes when a new one is requested by **explicitly expiring prior unused codes** (not marking them used). `OTP_SECRET` is read from the environment.
- The schema has **no columns** for attempt counts or request timestamps beyond `fecha_expiracion`/`utilizado`; persistent attempt/rate limits cannot be fully represented without a schema change. This is recorded as a limitation; the spec does not claim persistent protection the schema cannot store.
- Public route paths (`/propuesta/{token}/otp`, `/propuesta/{token}/aceptar`) are provisional, to coordinate with Nicolás.
- Whether a quotation is created on acceptance (default: NO; only enablement is gated).

### Out of scope
The full quotation module (prices, calculations, PDF, approvals), ticket flows, OTP for the employee QR flow, components/`sugerir_cambio` (Esteban), schema changes, queues/Redis/Celery, and any feature not required by HU-15/HU-16.

### Open dependencies and unknowns (not assumed resolved)
- **BUG-A05 (SCRUM-54)**: no information in the repository; open unknown.
- **BUG-A06**: official criteria for OTP rejection to be reviewed; not assumed resolved.
- **CR-01 (SCRUM-65)**: under analysis; possible impact on HU-15/HU-16.
- **Accepted-proposal content consistency**: the public consult shows live survey data; routes that can change it are not all guarded (see Requirement 6). Blocking for the definitive functional acceptance of HU-15.
- Real SMTP account, final public route, proposal content tied to HU-08/HU-09, and the quotation-guard integration with real quotation endpoints.

## Glossary

- **Backend_API**: The Mansillas SIC FastAPI service.
- **Comercial**: An authenticated user whose role literal is `COMERCIAL_MANSILLAS`.
- **Pre_Quotation**: A `precotizacion` row; relevant states `ENVIADA` (consultable/acceptable) and `ACEPTADA`.
- **Link_Token**: The UUID `precotizacion.token` used in the public URL.
- **OTP**: A one-time numeric code sent to the stored `correo_cliente`; only a hash is stored (`codigo_verificacion.codigo_hash`).
- **Verification_Code**: A `codigo_verificacion` row for a Pre_Quotation.
- **Acceptance_Record**: An `aceptacion_precotizacion` row capturing who accepted and when.
- **Quotation_Enabled**: The condition that a Pre_Quotation is `ACEPTADA` and has an Acceptance_Record.

## Requirements

### Requirement 1: Request an OTP for a sent proposal

**User Story:** As a client, I want to request a verification code for my proposal, so that I can prove my identity before accepting. (HU-15)

#### Acceptance Criteria

1. WHEN an OTP is requested for a valid Link_Token whose Pre_Quotation is `ENVIADA`, THE Backend_API SHALL generate a cryptographically secure OTP using the standard library `secrets`, store only its hash in `codigo_verificacion.codigo_hash`, set `fecha_expiracion` and `utilizado = FALSE`, link it to the Pre_Quotation (`id_precotizacion`), and email the plain OTP to the stored `correo_cliente`.
2. THE Backend_API SHALL send the OTP only to the stored `correo_cliente` and SHALL NOT accept a client-supplied destination.
3. IF the Link_Token is malformed, unknown, or the Pre_Quotation is not `ENVIADA` (`BORRADOR`/`ACEPTADA`/`ANULADA`), THEN THE Backend_API SHALL return an indistinguishable not-found response.
4. THE Backend_API SHALL NOT return the OTP in any HTTP response nor write it (or its hash) to logs.
5. WHEN a new OTP is requested, THE Backend_API SHALL invalidate previously issued unused codes for that Pre_Quotation by **explicitly expiring** them (setting `fecha_expiracion` to the past), reserving `utilizado = TRUE` for the actual consumption of a code at acceptance, so at most one code is usable at a time. This respects the acceptance trigger, which requires `utilizado = TRUE` and a non-expired code.
6. THE Backend_API SHALL throttle OTP requests per the approved minimum interval; WHERE the schema cannot persist the throttle state, the limitation SHALL be recorded and the protection SHALL NOT be claimed as persistent.
7. IF email sending fails, THEN THE Backend_API SHALL report the failure and SHALL NOT leave a usable code that was never delivered beyond what the invalidation policy dictates.
8. THE Backend_API SHALL require a TLS-protected SMTP transport for OTP delivery regardless of whether SMTP authenticates, using the email helper's TLS-required mode.

### Requirement 2: Accept the proposal with the OTP

**User Story:** As a client, I want to accept my proposal by entering the code and my identity, so that the proposal becomes accepted. (HU-15)

#### Acceptance Criteria

1. WHEN acceptance is submitted for a valid Link_Token with the correct, unexpired `codigo`, and the acceptant's `nombre_aceptante` and `cargo_aceptante`, THE Backend_API SHALL, in a single transaction: verify the OTP, mark the Verification_Code `utilizado = TRUE`, and insert the Acceptance_Record so that trigger `registrar_aceptacion_precotizacion` validates the code and transitions the Pre_Quotation to `ACEPTADA`. The client supplies ONLY `nombre_aceptante`, `cargo_aceptante`, and `codigo`; `correo_aceptante` is taken from the Pre_Quotation's stored `correo_cliente` and is never supplied or substituted by the client.
2. THE Backend_API SHALL NOT set `estado = 'ACEPTADA'` manually; the existing trigger performs that transition.
3. THE Backend_API SHALL perform the OTP consumption, the Acceptance_Record insert, and the state transition with no intermediate commit, holding the locks until a single commit or rollback.
4. IF the OTP is wrong, expired, already used, or not linked to this Pre_Quotation, THEN THE Backend_API SHALL reject the acceptance without recording an Acceptance_Record, count the failed attempt per the approved policy, and return an error that does not reveal the correct code or internal detail.
5. THE Backend_API SHALL record `nombre_aceptante`, `cargo_aceptante` (validated against the schema: `VARCHAR(150)` and `VARCHAR(100)`, non-empty), `correo_aceptante` (from the stored `correo_cliente`), and `fecha_aceptacion` in the Acceptance_Record. It SHALL also verify that `codigo_verificacion.correo_destino` matches the Pre_Quotation's authorized `correo_cliente` before accepting.
6. IF the Pre_Quotation is not `ENVIADA` at acceptance time (already `ACEPTADA`, or `ANULADA`/`BORRADOR`), THEN THE Backend_API SHALL reject the acceptance (the `UNIQUE` on `aceptacion_precotizacion.id_precotizacion` and the trigger prevent a duplicate acceptance).
7. WHERE two acceptance requests run concurrently, THE Backend_API SHALL ensure at most one succeeds, using the Visit-row lock first then the Pre_Quotation/code rows (consistent lock order), relying on the `UNIQUE` constraints as the final guarantee.
8. THE Backend_API SHALL NOT expose the OTP, its hash, other clients' data, or unnecessary internal information in the response.

### Requirement 3: OTP security parameters

**User Story:** As a maintainer, I want the OTP parameters configurable and safe, so that the MVP is secure without over-engineering. (HU-15)

#### Acceptance Criteria

1. THE Backend_API SHALL generate the OTP with the standard library `secrets` and store in `codigo_verificacion.codigo_hash` an **HMAC-SHA256** of the code, keyed by an independent `OTP_SECRET`, cryptographically bound to the Pre_Quotation (and an issuance identifier where applicable). It SHALL verify with `hmac.compare_digest` and SHALL never store or log the plain OTP.
2. THE Backend_API SHALL NOT reuse `JWT_SECRET` as `OTP_SECRET` and SHALL NOT use an insecure default secret. The application SHALL start without `OTP_SECRET`, but OTP operations SHALL fail with a controlled error when no secure secret is configured.
3. THE Backend_API SHALL treat OTP length (6 digits), expiry (10 minutes), minimum request interval (60 s), maximum failed attempts per issuance (5), and previous-code invalidation (expire prior unused codes) as fixed, documented MVP values — provisional technical decisions, NOT official acceptance criteria — avoiding unnecessary configurability.
4. WHERE a limit cannot be persisted with the current schema (no attempt/request-count columns), THE Backend_API SHALL record the limitation and SHALL NOT assert a persistent guarantee it cannot store.

### Requirement 4: Enable quotation only after acceptance (HU-16)

**User Story:** As a Comercial, I want quotation operations available only after the pre-quotation is accepted, so that no quotation precedes acceptance. (HU-16)

#### Acceptance Criteria

1. WHEN a Comercial requests whether quotation is enabled for a Pre_Quotation, THE Backend_API SHALL return enabled only if the Pre_Quotation exists, its `estado` is `ACEPTADA`, and an Acceptance_Record exists for it.
2. THE Backend_API SHALL provide a reusable guard that quotation operations depend on, so the backend enforces the rule regardless of the frontend.
3. IF the enablement request is made by a Current_User whose role is not `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject it with an authorization error.
4. IF the Pre_Quotation does not exist, THEN THE Backend_API SHALL return a not-found response.
5. THE Backend_API SHALL NOT create a quotation on acceptance unless the official criteria require it; the database trigger `validar_cotizacion_tras_aceptacion` already blocks quotations before acceptance.
6. WHERE no quotation endpoints exist yet in the codebase, THE guard integration SHALL be recorded as a dependency on the future quotation operations (owned by another integrator), not implemented here.

### Requirement 5: Reuse of existing architecture

**User Story:** As a maintainer, I want HU-15/HU-16 built on the existing stack, so that the MVP stays simple. (HU-15, HU-16)

#### Acceptance Criteria

1. THE Backend_API SHALL map the existing `codigo_verificacion` and `aceptacion_precotizacion` tables without altering the schema.
2. THE Backend_API SHALL reuse the SMTP helper, `app/deps.py`, `precotizacion_rules`, the public proposal endpoint, and `registrar_acceso`, and SHALL NOT duplicate SQL rules already enforced by triggers.
3. THE Backend_API SHALL read OTP and email configuration from environment variables and SHALL NOT place secrets in source.
4. THE Backend_API SHALL NOT add queues, Redis, Celery, microservices, or extra layers.

### Requirement 6: Consistency of the accepted proposal (blocking dependency)

**User Story:** As a stakeholder, I want the accepted proposal's content to be the content the client saw, so that acceptance is meaningful. (HU-15)

#### Acceptance Criteria

1. THE Backend_API SHALL distinguish three levels of immutability: (a) the `precotizacion` row (frozen against UPDATE/DELETE once `ACEPTADA` by `impedir_edicion_precotizacion_aceptada`); (b) the Acceptance_Record, which has no edit/delete route exposed by the API — the `UNIQUE` constraints prevent duplicates but do NOT by themselves make an existing row immutable at the database level, so absolute DB-level immutability is NOT claimed; (c) the **accepted content** (the survey data the public consult shows), which is NOT frozen by any current trigger. Keeping the accepted content consistent remains a blocking dependency.
2. THE Backend_API SHALL identify the operations that can still change the accepted content: additional chair registration (`POST /visitas/{id}/sillas`), technician chair edit (`PUT /sillas/{id}`), commercial chair edit (`PUT /sillas/{id}/comercial`), component/state changes (Esteban), deletion of relevant data, and photographs (if part of the proposal).
3. THE Backend_API SHALL NOT modify routes owned by other integrators without authorization; the shared `propuesta_congelada` guard already blocks the commercial edit once the proposal is `ENVIADA`/`ACEPTADA`, but the other routes remain a recorded gap.
4. THE Backend_API SHALL NOT claim the accepted proposal is fully immutable while any identified operation can still modify its content; this consistency gap is a blocking dependency for the definitive functional acceptance of HU-15.
5. THE Backend_API SHALL NOT snapshot survey data into new tables/columns within this spec; a persistent snapshot is a pending alternative requiring approval.
