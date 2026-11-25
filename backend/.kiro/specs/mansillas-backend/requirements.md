# Requirements Document

## Introduction

This feature delivers the Mansillas SIC backend (Python/FastAPI with SQLAlchemy over PostgreSQL) covering the chair-inventory field workflow: commercial staff schedule visits, technicians register chairs with auto-generated QR codes, and downloadable QR labels are produced. It also logs public pre-quotation link accesses and establishes deployment and role-based access rules. The backend reuses the existing PostgreSQL schema (`mansillas` schema), including the `secuencia_qr` sequence, the `generar_codigo_qr` trigger, and the `acceso_precotizacion` table.

Out of scope: chair change history, photographs, component checklist, tickets, pre-quotation CRUD, authentication/user management, empresa/sede CRUD, pre-quotation rejection, payments, SaaS multi-tenancy, offline mode, caches, queues, microservices, and generic abstractions.

## Glossary

- **Backend_API**: The Mansillas SIC FastAPI service exposing the endpoints described in this document.
- **Visit**: A record in table `visita` linking an empresa, sede, commercial user, technician user, and an estimated chair count (`cantidad_estimada`).
- **Chair**: A record in table `silla` representing a physical chair with its QR code, public token, and attributes.
- **Comercial**: An authenticated user whose role literal is `COMERCIAL_MANSILLAS`.
- **Tecnico**: An authenticated user whose role literal is `TECNICO`.
- **Current_User**: The authenticated principal resolved by the `get_current_user` dependency, exposing `id`, `rol`, and `empresa_id`.
- **Codigo_QR**: The human-readable chair identifier in format `SIC-00000001` (prefix `SIC-` plus eight zero-padded digits) generated from sequence `secuencia_qr` by trigger `generar_codigo_qr`.
- **Token_Publico**: The UUID value in `silla.token_publico` used to reference a chair in public, non-guessable URLs.
- **Serial_Antiguo**: The optional legacy serial stored in `silla.serial_antiguo`, unique per empresa via `UNIQUE (id_empresa, serial_antiguo)`.
- **Acceso_Record**: A row in table `acceso_precotizacion` capturing one access to a public pre-quotation link.

## Requirements

### Requirement 1: Visit creation by Comercial

**User Story:** As a Comercial, I want to create a visit for a company, so that a technician can later register chairs against it. (RF-01, HU-01)

#### Acceptance Criteria

1. WHEN a Comercial submits a visit creation request with empresa, sede, technician, and `cantidad_estimada`, THE Backend_API SHALL create a `visita` record with those values.
2. IF a visit creation request omits empresa, sede, technician, or `cantidad_estimada`, THEN THE Backend_API SHALL reject the request and return an error response identifying the missing required fields.
3. IF a visit creation request is made by a Current_User whose role is not `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject the request with an authorization error. (RN-05)
4. WHEN any later operation reads or updates a visit, THE Backend_API SHALL preserve the original `cantidad_estimada` value unchanged. (RN-04)

### Requirement 2: Technician visit scoping

**User Story:** As a Tecnico, I want to list only the visits assigned to me, so that I work only within my own assignments. (RF-01, HU-01)

#### Acceptance Criteria

1. WHEN a Tecnico requests the visit list, THE Backend_API SHALL return only visits whose `id_tecnico` equals the Current_User identifier.
2. WHERE a visit is assigned to a different technician, THE Backend_API SHALL exclude that visit from the response returned to the requesting Tecnico.

### Requirement 3: Chair registration

**User Story:** As a Tecnico, I want to register a chair within one of my visits, so that the chair is captured with its location and owner data. (RF-06, HU-06)

#### Acceptance Criteria

1. WHEN a Tecnico registers a chair, THE Backend_API SHALL require `id_visita`, `id_empleado`, and `cargo` from the request and SHALL derive `id_empresa`, `id_sede`, and `id_departamento` from the referenced empleado.
2. THE Backend_API SHALL validate that the derived `id_empresa` and `id_sede` match the referenced `visita` before creating the Chair.
3. IF the chair registration request omits `id_visita`, `id_empleado`, or `cargo`, THEN THE Backend_API SHALL reject the request and return an incomplete-information error identifying the missing fields.
4. IF the referenced `id_visita` is not assigned to the requesting Tecnico, THEN THE Backend_API SHALL reject the request with an authorization error.
5. WHEN a chair query is served, THE Backend_API SHALL return `id_empresa`, `id_sede`, `id_departamento`, `id_empleado`, and `cargo` for the Chair.
6. THE Backend_API SHALL create a Chair regardless of how many chairs already exist for the visit relative to `cantidad_estimada`.

### Requirement 4: QR code and public token generation

**User Story:** As a system stakeholder, I want each chair to receive a consecutive QR code and an unguessable public token, so that chairs are uniquely identified and safely referenced in public. (RF-03, RN-02, HU-03)

#### Acceptance Criteria

1. WHEN a Chair is created, THE Backend_API SHALL submit an empty or null `codigo_qr` so that trigger `generar_codigo_qr` assigns a consecutive Codigo_QR in format `SIC-00000001` from sequence `secuencia_qr`.
2. THE Backend_API SHALL treat each assigned Codigo_QR as permanent and SHALL NOT reuse or reassign a Codigo_QR to a different Chair.
3. WHEN a Chair is created, THE Backend_API SHALL store a Token_Publico UUID that is not derivable from the Codigo_QR or the chair identifier.
4. WHEN a request supplies a valid Token_Publico, THE Backend_API SHALL return the corresponding Chair's public query data through a chair-by-token endpoint.
5. IF a request supplies a Token_Publico that matches no Chair, THEN THE Backend_API SHALL return a not-found response.

### Requirement 5: Legacy serial and observations

**User Story:** As a Tecnico, I want to record an optional legacy serial and free-text observations for a chair, so that prior identification and notes are preserved. (RF-04, RN-03, HU-04, RF-07, HU-07)

#### Acceptance Criteria

1. WHERE a `serial_antiguo` value is provided, THE Backend_API SHALL store that value on the Chair.
2. IF a provided `serial_antiguo` already exists for the same `id_empresa`, THEN THE Backend_API SHALL reject the request without creating a duplicate Chair. (RN-03)
3. WHERE an `observaciones` value is provided, THE Backend_API SHALL store that free text on the Chair and SHALL allow updating it on an existing Chair.
4. WHEN a chair query is served, THE Backend_API SHALL return the stored `serial_antiguo` and `observaciones` values.

### Requirement 6: QR label PDF download

**User Story:** As a Comercial or Tecnico, I want to download printable QR labels for selected chairs, so that labels can be affixed to the physical chairs. (RF-05, HU-05)

#### Acceptance Criteria

1. WHEN a QR download request supplies one or more chair identifiers, THE Backend_API SHALL return a PDF document arranging the requested QR labels in a grid.
2. THE Backend_API SHALL generate each QR label at error-correction level H, at a module area of at least 3 cm by 3 cm, with the Codigo_QR printed below the QR image.
3. THE Backend_API SHALL produce QR labels that are scannable by a phone native camera application.
4. WHEN a QR download batch contains up to 50 chairs, THE Backend_API SHALL return the PDF within 20 seconds.
5. IF a Tecnico requests QR labels for a chair outside the visits assigned to that Tecnico, THEN THE Backend_API SHALL reject the request with an authorization error.
6. WHERE the Current_User role is `COMERCIAL_MANSILLAS`, THE Backend_API SHALL allow QR label downloads for chairs of any empresa.

### Requirement 7: Pre-quotation access logging

**User Story:** As a Comercial, I want public pre-quotation link accesses to be logged and reviewable, so that I can see client engagement. (RF-14, HU-14)

#### Acceptance Criteria

1. WHEN the `registrar_acceso` service is invoked with a pre-quotation identifier and a User-Agent string, THE Backend_API SHALL insert an Acceso_Record with the parsed `navegador` and `sistema_operativo` and the access timestamp.
2. WHEN a Comercial requests the access log for a pre-quotation, THE Backend_API SHALL return the stored Acceso_Record entries for that pre-quotation.
3. IF no Acceso_Record exists for the requested pre-quotation, THEN THE Backend_API SHALL return a response indicating that no accesses are recorded.
4. IF an access-log read request is made by a Current_User whose role is not `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject the request with an authorization error.

### Requirement 8: Deployment configuration and role-based access

**User Story:** As an operator, I want the backend to be configurable through environment variables and enforce role-based access, so that it can be deployed to a pilot host and restrict each endpoint to the correct roles. (RNF-01, HU-26)

#### Acceptance Criteria

1. THE Backend_API SHALL read its database connection from a `DATABASE_URL` environment variable and its secrets from environment variables rather than source code.
2. WHERE a pilot deployment host is Render or Railway, THE Backend_API SHALL operate using the same environment-variable configuration used for the Latinoamerican Hosting target.
3. THE Backend_API SHALL provide a `get_current_user` dependency that resolves a Current_User exposing `id`, `rol`, and `empresa_id`, with role literals limited to `COMERCIAL_MANSILLAS`, `TECNICO`, `ADMIN_CLIENTE`, and `EMPLEADO_CLIENTE`.
4. WHERE an endpoint is restricted to commercial actions, THE Backend_API SHALL grant access to a Current_User with role `COMERCIAL_MANSILLAS`.
5. WHERE an endpoint is restricted to technician actions, THE Backend_API SHALL grant access to a Current_User with role `TECNICO` limited to resources within that technician's assigned visits.
6. IF a request to a commercial-only or technician-only endpoint is made by a Current_User whose role is neither `COMERCIAL_MANSILLAS` nor `TECNICO` as applicable, THEN THE Backend_API SHALL reject the request with an authorization error.
