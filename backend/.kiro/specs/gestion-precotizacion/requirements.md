# Requirements Document

## Introduction

This feature lets a Comercial review and edit the survey (levantamiento) information, mark it as validated, create a pre-quotation from the validated data, and generate and send a unique public link so the client can consult the proposal. It is built on the existing Mansillas SIC backend (FastAPI + SQLAlchemy over the `mansillas` schema) and reuses existing tables, authentication, the pre-quotation `token`, and the access-logging service.

HU-12 covers reviewing/editing/validating the survey; HU-13 covers generating and emailing the unique link and the public consult of the proposal. Acceptance by OTP (HU-15) and the definitive quotation module (HU-16) are out of scope.

### Existing functionality reused (not re-implemented)
- `silla` registration/read/update endpoints and `SillaOut` (`app/routers/sillas.py`): the survey's chair data.
- `GET /sillas?id_visita=` (HU-02): listing the chairs of a visit.
- Chair photographs (HU-10): part of the survey content.
- `Precotizacion` model (`app/models/precotizacion.py`): already maps `precotizacion` including `token`, `estado`, `correo_cliente`, `fecha_envio`, `creada_por`, `observaciones`.
- `registrar_acceso` service and `GET /precotizaciones/{id}/accesos` (`app/routers/accesos.py`): access logging for the public link.
- Business RBAC in `app/deps.py` (`get_current_user`, `require_role`, `require_tecnico_owns_visita`) and the `COMERCIAL_MANSILLAS`/`TECNICO` roles.
- Database guarantees: `precotizacion.token` default `gen_random_uuid()` (unique); trigger `impedir_edicion_precotizacion_aceptada` (blocks edit/delete once `ACEPTADA`); `UNIQUE (id_empresa, id_visita)` composite FK scoping.

### New functionality (this spec)
- A pre-quotation creation endpoint from a visit's validated survey (`BORRADOR`).
- A survey-validation action available to the Comercial before pre-quotation.
- Link generation and email sending for a pre-quotation (`BORRADOR` → `ENVIADA`).
- A public, token-based endpoint to consult the proposal without login, logging the access.

### Dependencies on teammates
- **Davidson**: owns the `precotizacion` table, its `token`, and `registrar_acceso`. This spec reuses them; any pre-quotation CRUD not yet present must be agreed as belonging to this spec (see Pending decisions).
- **Esteban**: owns the component checklist (`componente`, `silla_componente`, `vista_estado_mantenimiento`) and the `sugerir_cambio` evaluation. This spec does NOT implement them and only reads them if available (see Pending decisions and R3.5).

### Pending decisions (resolved in design, not assumed here)
- How a Validated_Survey is represented **without a schema change**. `visita.estado = 'FINALIZADA'` is NOT assumed to mean "commercially validated" (different business concepts). The first simple alternative is that an explicit commercial validation action creates the `BORRADOR` pre-quotation from the current survey (validation = the act of generating the pre-quotation). IF validation must exist independently of pre-quotation creation, that is a limitation of the current schema and a minimal change would be required; it is identified, not applied. No validation indicator is stored in free-text `observaciones` and no state is invented.
- Email delivery mechanism: no email sender exists in the codebase today. SMTP is the first simple MVP alternative, subject to an authorized account and credentials; the provider is a design/team decision, and this spec requires the behaviour, not a specific provider. No atomicity between SMTP and PostgreSQL is promised.
- Ownership of pre-quotation create/list endpoints (Davidson vs. this spec); a minimal pre-quotation CRUD is treated as provisional to HU-13, subject to coordination.
- The full content a proposal must present is not assumed to be just `codigo_qr`/`cargo`/`estado`. The required proposal fields are driven by the official HUs and available contracts; survey content depends functionally on HU-08/HU-09 (survey capture) and on Esteban's component evaluation where it forms part of the proposal. Missing proposal data is recorded as an integration dependency, not invented.
- Whether the public proposal view includes component states (depends on Esteban's data) or only chair identification data.
- The public route path is coordinated with Nicolás (frontend); the backend defines the token-based contract.
- **BUG-A05 (SCRUM-54)**: no information about this defect is available in the repository. It is recorded as an open unknown; its resolution is neither invented nor assumed.

### Out of scope
OTP acceptance (HU-15), the definitive quotation module (HU-16), pre-quotation rejection/annulment flows, the component checklist and chair evaluation (Esteban), exposing another empresa's data, schema changes, new architectural layers, queues, and generic abstractions.

## Glossary

- **Backend_API**: The Mansillas SIC FastAPI service.
- **Comercial**: An authenticated user whose role literal is `COMERCIAL_MANSILLAS`.
- **Current_User**: The principal resolved by `get_current_user` (`app/deps.py`), exposing `id`, `rol`, `empresa_id`.
- **Visit**: A `visita` row linking empresa, sede, commercial, technician and `cantidad_estimada`.
- **Survey (Levantamiento)**: The chairs (`silla`) registered for a Visit, with their editable data and photographs.
- **Pre_Quotation**: A `precotizacion` row for a Visit, with `estado` in `BORRADOR`/`ENVIADA`/`ACEPTADA`/`ANULADA`, a unique `token`, and `correo_cliente`.
- **Link_Token**: The UUID `precotizacion.token`, used in the public, non-guessable proposal URL.
- **Validated_Survey**: A Survey the Comercial has marked ready for pre-quotation, as represented by the mechanism chosen in design without a schema change.
- **Access_Record**: A row in `acceso_precotizacion` logged by `registrar_acceso`.

## Requirements

### Requirement 1: Consult the survey for review

**User Story:** As a Comercial, I want to consult the survey information of a visit, so that I can review it before building the pre-quotation. (HU-12)

#### Acceptance Criteria

1. WHEN a Comercial requests the survey of a Visit, THE Backend_API SHALL return the chairs of that Visit with their editable data (reusing the HU-02 chairs listing and the existing `SillaOut`).
2. WHERE the Visit does not exist, THE Backend_API SHALL return a not-found response.
3. IF the survey request is made by a Current_User whose role is not `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject the request with an authorization error.
4. THE Backend_API SHALL follow the existing authorization policy for internal commercials (as in Davidson's `visitas`/`sillas` endpoints, where `COMERCIAL_MANSILLAS` may access any visit) and SHALL NOT invent an additional per-empresa restriction for the internal Comercial. Strict per-empresa data isolation applies to the **public** link (Requirement 7), not to the internal Comercial.
5. THE Backend_API SHALL apply the authorization rules consistently across all authenticated endpoints of this spec (commercial-only for the survey/pre-quotation actions).

### Requirement 2: Edit the survey information

**User Story:** As a Comercial, I want to edit the survey information, so that the proposal is built from correct data. (HU-12)

#### Acceptance Criteria

1. WHEN a Comercial updates the editable survey fields of a chair, THE Backend_API SHALL store the changes and SHALL return the updated values.
2. WHEN the survey is consulted again after an edit, THE Backend_API SHALL present the updated information.
3. IF an edit targets a chair that does not exist, THEN THE Backend_API SHALL return a not-found response.
4. IF a survey edit is made by a Current_User whose role is not `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject the request with an authorization error.
5. THE Backend_API SHALL determine the commercially editable survey fields from HU-12 (the data the Comercial corrects before the proposal), chosen among the fields the existing `silla` schema already supports, and SHALL NOT be constrained to the technician's current `PUT /sillas/{id}` field set by default. The specific editable field list is settled in design.
6. THE Backend_API SHALL keep immutable: identifiers (`id_*`), `codigo_qr`, `numero_qr`, `token_publico`, empresa/visita ownership relations, and `visita.cantidad_estimada` (RN-04). Component states (`silla_componente`) are Esteban's and are not edited here.
7. WHERE the Comercial edit uses a different authorization than the technician's existing `PUT /sillas/{id}`, THE Backend_API SHALL NOT change that existing endpoint's authorization rules without justification and approval.

### Requirement 3: Explicit validation combined with pre-quotation creation

**User Story:** As a Comercial, I want to explicitly validate the survey when I generate the pre-quotation, so that the proposal is built from information I confirmed. (HU-12)

#### Acceptance Criteria

1. WHEN a Comercial creates a pre-quotation, THE Backend_API SHALL require an explicit `confirmar_validacion: true` in the request and SHALL treat that single action as both the explicit validation of the current survey and the creation of the `BORRADOR` pre-quotation (combined action for the MVP, no circular dependency and no SQL column added).
2. IF `confirmar_validacion` is absent or false, THEN THE Backend_API SHALL reject the request and SHALL NOT create the pre-quotation.
3. THE Backend_API SHALL define "validated" per pre-quotation state as: `BORRADOR` = the survey was confirmed at creation and may still be corrected; `ENVIADA`/`ACEPTADA` = the confirmed survey is frozen for the proposal (survey edits that affect the proposal are rejected, see Requirement 5); `ANULADA` = the proposal is void. The existence of a pre-quotation SHALL NOT, by itself, be taken as proof that a later survey modification was validated.
4. IF a validate/create request is made by a Current_User whose role is not `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject the request with an authorization error.
5. IF the request targets a Visit that does not exist, THEN THE Backend_API SHALL return a not-found response.
6. THE Backend_API SHALL NOT compute the component checklist or `sugerir_cambio` as part of validation; those belong to Esteban's module and are only read if available.
7. WHERE the Comercial corrects the survey after creation (while `BORRADOR`), THE Backend_API SHALL require a fresh explicit confirmation of the current information before sending (see Requirement 6). A persistent, independent validation flag or per-version validation is NOT representable without a schema change; that limitation is recorded and such a criterion is NOT declared satisfied if the official HUs require it.

### Requirement 4: Create a pre-quotation from the validated survey

**User Story:** As a Comercial, I want the pre-quotation to use the validated survey, so that the proposal reflects the reviewed information. (HU-12)

#### Acceptance Criteria

1. WHEN a Comercial creates a Pre_Quotation for a Visit with `confirmar_validacion: true`, THE Backend_API SHALL create a `precotizacion` row in state `BORRADOR` with `creada_por` set to the Current_User and `id_empresa`/`id_visita` derived from the Visit.
2. THE Backend_API SHALL treat the explicit confirmation at creation (Requirement 3) as the validation; it SHALL NOT require a separate prior "validated" state (removing the earlier circular dependency).
3. WHEN a Pre_Quotation is created, THE Backend_API SHALL reference the Visit whose survey was just confirmed, so the proposal reflects the current survey.
4. IF a pre-quotation create request is made by a Current_User whose role is not `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject the request with an authorization error.
5. THE Backend_API SHALL rely on the database default for `token` (`gen_random_uuid()`) rather than computing it.
6. WHERE at most one active (`BORRADOR`/`ENVIADA`/`ACEPTADA`) pre-quotation per Visit is required, THE Backend_API SHALL enforce it at the application level. There is NO SQL UNIQUE on `precotizacion.id_visita`. The table's UNIQUE constraints are `token` and `(id_empresa, id_precotizacion)`; per the SQL, the latter exists only to support the composite foreign keys that reference `precotizacion(id_empresa, id_precotizacion)` (it does not make a pre-quotation unique per visit, since `id_precotizacion` is already the primary key). The concurrency-safe handling of duplicates without a schema change is settled in design; a minimal schema change (a partial unique index on `id_visita`) is recorded as an option, not applied.

### Requirement 5: Consistency between survey and pre-quotation

**User Story:** As a Comercial, I want the pre-quotation to reflect the reviewed survey, so that the client sees consistent data. (HU-12)

#### Acceptance Criteria

1. WHEN the public proposal is consulted, THE Backend_API SHALL present the survey data of the pre-quotation's Visit as currently stored, so the survey consulted right after a confirmed creation is consistent with the pre-quotation.
2. THE Backend_API SHALL acknowledge that the `impedir_edicion_precotizacion_aceptada` trigger protects only the `precotizacion` row and does NOT freeze the related `silla`, `fotografia`, or `silla_componente` data.
3. THE Backend_API SHALL identify every route that can change what the proposal presents and apply a **shared business rule** that forbids modifying that data while the Visit's pre-quotation is `ENVIADA` or `ACEPTADA`. The routes considered are: commercial chair edit (this spec), technician chair edit (`PUT /sillas/{id}`, Davidson/HU), additional chair registration (`POST /visitas/{id}/sillas`, HU-02), component changes (Esteban, when part of the proposal), and photographs (HU-10, only if part of the proposal content).
4. WHERE a route belongs to another integrator, THE Backend_API SHALL NOT modify it without authorization; the consistency gap for those routes SHALL be recorded as a dependency, and consistency SHALL NOT be declared guaranteed while any such route can still modify a sent proposal.
5. WHERE validation and sending can occur concurrently, THE Backend_API SHALL use the minimal transactional mechanism compatible with PostgreSQL/SQLAlchemy (a single transaction that re-reads the pre-quotation state with a row lock, `SELECT ... FOR UPDATE`, before the state-changing step) to avoid lost updates, without introducing queues or external coordination.
6. THE Backend_API SHALL NOT snapshot or duplicate survey data into new tables/columns within this spec. A persistent proposal snapshot (for the case where the original survey must keep being edited after sending) is recorded as an alternative pending approval, not applied.

### Requirement 6: Generate and send the unique link

**User Story:** As a Comercial, I want to generate and email a unique link for the proposal, so that the client can consult the pre-quotation. (HU-13)

#### Acceptance Criteria

1. WHEN a Comercial sends a Pre_Quotation to a client email, THE Backend_API SHALL build a unique link from the Pre_Quotation's `token` and the configured frontend URL, and SHALL send it to the provided email.
2. WHEN the email is sent successfully, THE Backend_API SHALL store `correo_cliente` and `fecha_envio` and set `estado` to `ENVIADA`.
3. WHERE the send is a first send from `BORRADOR`, THE Backend_API SHALL require `confirmar_validacion: true` in the request (re-confirmation of the current survey before freezing it, per Requirement 3.7); IF it is absent or false, THE Backend_API SHALL reject with `422` and SHALL NOT send the email or change the state. WHERE the send is a resend from `ENVIADA`, THE Backend_API SHALL NOT require a new validation of the already-frozen survey.
4. THE Link_Token SHALL identify exactly one Pre_Quotation and SHALL NOT be derivable from the pre-quotation identifier.
5. IF the email send fails, THEN THE Backend_API SHALL report the failure and SHALL NOT mark the Pre_Quotation as sent for that attempt (no `estado`/`fecha_envio` change).
6. IF the database update fails AFTER the email was sent, THEN THE Backend_API SHALL report the failure and SHALL NOT attempt to "unsend" the email; it acknowledges that a database rollback does not revert a sent email, without promising atomicity between SMTP and PostgreSQL.
7. WHEN the same proposal is resent, THE Backend_API SHALL reuse the existing `token` (the link stays the same), provided the Pre_Quotation is not `ACEPTADA`/`ANULADA`. THE Backend_API SHALL keep the original `correo_cliente` once the proposal has been sent and SHALL NOT change the recipient on resend unless an explicit business authorization to change it is provided.
8. THE Backend_API SHALL validate the `correo_cliente` format before sending, without adding new dependencies.
9. WHERE the client opens the link after the email is sent but before `estado='ENVIADA'` is committed, THE public consult SHALL behave per Requirement 7 (it returns the proposal only once `ENVIADA`/`ACEPTADA`); this timing window is documented, not specially handled.
10. IF a send request is made by a Current_User whose role is not `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject the request with an authorization error.
11. IF a send request targets a Pre_Quotation that does not exist, THEN THE Backend_API SHALL return a not-found response.
12. THE Backend_API SHALL read SMTP configuration (host, port, user, password, from-address, TLS mode, timeout) and the frontend URL from environment variables and SHALL NOT place credentials in source or versioned files.

### Requirement 7: Public consult of the proposal via the link

**User Story:** As a client, I want to open the unique link and consult my proposal, so that I can review the pre-quotation. (HU-13)

#### Acceptance Criteria

1. WHEN a request supplies a valid Link_Token of a Pre_Quotation in state `ENVIADA` or `ACEPTADA`, THE Backend_API SHALL return the public proposal data without requiring login.
2. IF the Link_Token matches no Pre_Quotation, or matches one in state `BORRADOR` or `ANULADA`, THEN THE Backend_API SHALL return a not-found response that does not reveal whether the token exists or its internal state.
3. THE public proposal response SHALL use an explicit public schema (not the full internal model serialization) containing only the proposal's own data, scoped to the pre-quotation's own Visit and empresa, and SHALL NOT expose another empresa's data, other sillas' public tokens, private photographs, or personal information.
4. WHEN the public link is accessed, THE Backend_API SHALL log the access via the existing `registrar_acceso(db, id_precotizacion, user_agent)` service, respecting its signature and its own commit behaviour.
5. THE Backend_API SHALL NOT require or process an OTP in this spec; identity-verified acceptance is HU-15.

### Requirement 8: Retrieve existing pre-quotations

**User Story:** As a Comercial, I want to retrieve the pre-quotations of a visit, so that I can see and resend existing proposals. (HU-13)

#### Acceptance Criteria

1. WHEN a Comercial requests the pre-quotations filtered by `id_visita`, THE Backend_API SHALL return the matching `precotizacion` rows using the explicit `PrecotizacionOut` schema, following the frontend contract (`GET /precotizaciones?id_visita=`).
2. WHERE no pre-quotation matches, THE Backend_API SHALL return an empty collection.
3. IF the request is made by a Current_User whose role is not `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject the request with an authorization error.

### Requirement 9: Reuse of existing schema, auth and conventions

**User Story:** As a maintainer, I want HU-12 and HU-13 built on the existing architecture, so that the MVP stays simple and consistent. (HU-12, HU-13)

#### Acceptance Criteria

1. THE Backend_API SHALL reuse the existing `visita`, `silla`, `precotizacion`, and `acceso_precotizacion` tables without altering the database schema.
2. THE Backend_API SHALL resolve authorization through `app/deps.py` and SHALL NOT modify teammates' security modules.
3. THE Backend_API SHALL translate database guarantees (e.g. the `impedir_edicion_precotizacion_aceptada` trigger) into appropriate HTTP responses rather than duplicating those rules in application code.
4. THE Backend_API SHALL read the email and frontend-URL configuration from environment variables and SHALL NOT place secrets in source code.
