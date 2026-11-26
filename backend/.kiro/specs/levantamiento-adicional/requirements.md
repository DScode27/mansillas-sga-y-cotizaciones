# Requirements Document

## Introduction

This feature extends the existing Mansillas SIC backend (Python/FastAPI with SQLAlchemy over PostgreSQL, `mansillas` schema) to close two gaps in the field-survey workflow: reading the real number of chairs registered for a visit (HU-02) and attaching multiple photographs to a registered chair (HU-10). Chair registration itself already exists and already allows registering chairs beyond the visit's estimated count; this spec reuses that behaviour and adds only what the acceptance criteria still require.

The backend reuses the existing schema and the business RBAC in `app/deps.py`. Chairs carry `estado`, `fecha_registro`, an auto-generated `codigo_qr` and `token_publico`. The `fotografia` table (`id_fotografia`, `id_silla`, `ruta_archivo`, `fecha_subida`) already exists for photographs.

Out of scope: photo editing and deletion, image processing (thumbnails, compression, async queues), public exposure of photographs by QR, component checklist / chair evaluation (Esteban's module), a second chair-registration mechanism, redundant storage of counts that can be derived from existing rows, and any change to the database schema. The `nombre_archivo` field expected by the frontend is returned as a value derived from the stored file, not persisted as a schema column.

## Glossary

- **Backend_API**: The Mansillas SIC FastAPI service exposing the endpoints described in this document.
- **Visit**: A record in table `visita` linking an empresa, sede, commercial user, technician user, and an estimated chair count (`cantidad_estimada`).
- **Chair**: A record in table `silla` representing a physical chair registered within a visit.
- **Photograph**: A record in table `fotografia` linking a Chair (`id_silla`) to a stored file path (`ruta_archivo`) and an upload timestamp (`fecha_subida`).
- **Comercial**: An authenticated user whose role literal is `COMERCIAL_MANSILLAS`.
- **Tecnico**: An authenticated user whose role literal is `TECNICO`.
- **Current_User**: The authenticated principal resolved by the `get_current_user` dependency (`app/deps.py`), exposing `id`, `rol`, and `empresa_id`.
- **Cantidad_Estimada**: The value `visita.cantidad_estimada` set when the visit is created and preserved unchanged thereafter (RN-04).
- **Cantidad_Real**: The current count of Chairs whose `id_visita` equals a given visit, derived from the `silla` rows and never stored redundantly.
- **Owned_Visit**: A Visit whose `id_tecnico` equals the requesting Tecnico's `id`, as enforced by `require_tecnico_owns_visita`.

## Requirements

### Requirement 1: Register chairs beyond the estimated count (existing behaviour)

**User Story:** As a Tecnico, I want to register chairs beyond the estimated count of a visit, so that the registry reflects the real inventory found during the survey. (HU-02)

#### Acceptance Criteria

1. WHEN a Tecnico registers a Chair in an Owned_Visit whose Cantidad_Real already equals or exceeds Cantidad_Estimada, THE Backend_API SHALL create the Chair without rejecting it for exceeding the estimate. *(Already implemented in `POST /visitas/{id_visita}/sillas`.)*
2. WHEN a Chair is registered, THE Backend_API SHALL preserve the visit's original Cantidad_Estimada unchanged. (RN-04) *(Already implemented; `cantidad_estimada` is not writable on visit update.)*
3. THE Backend_API SHALL NOT expose a second chair-registration mechanism to register additional chairs.

### Requirement 2: Consult the real number of registered chairs

**User Story:** As a Tecnico, I want to consult how many chairs are actually registered for a visit, so that I can compare the real inventory against the estimate. (HU-02)

#### Acceptance Criteria

1. WHEN a Tecnico requests the registered chairs of an Owned_Visit, THE Backend_API SHALL return all Chairs belonging to that visit so that Cantidad_Real can be determined from the response.
2. THE Backend_API SHALL derive Cantidad_Real from the `silla` rows and SHALL NOT store it as a separate persisted field.
3. WHERE the requested visit exists but has no registered Chair, THE Backend_API SHALL return an empty collection.
4. IF the requested visit does not exist, THEN THE Backend_API SHALL return a not-found response.
5. IF a Tecnico requests the registered chairs of a visit that is not an Owned_Visit, THEN THE Backend_API SHALL reject the request with an authorization error.
6. WHERE the Current_User role is `COMERCIAL_MANSILLAS`, THE Backend_API SHALL return all registered Chairs of the requested visit.
7. IF a chairs request is made by a Current_User whose role is neither `TECNICO` nor `COMERCIAL_MANSILLAS`, THEN THE Backend_API SHALL reject the request with an authorization error.

### Requirement 3: Attach multiple photographs to a chair

**User Story:** As a Tecnico, I want to attach multiple photographs to a registered chair during the survey, so that visual evidence is preserved for later consultation. (HU-10)

#### Acceptance Criteria

1. WHEN a Tecnico uploads a photograph for a Chair in one of their Owned_Visits, THE Backend_API SHALL store the file and SHALL create a `fotografia` row linking it to that Chair via `id_silla` with its `ruta_archivo` and `fecha_subida`.
2. THE Backend_API SHALL allow a Chair to hold more than one Photograph, each successful upload adding a new `fotografia` row for the same `id_silla`.
3. IF the uploaded file is missing or is not an accepted image type, THEN THE Backend_API SHALL reject the request and SHALL NOT create a `fotografia` row.
4. IF the referenced Chair does not exist, THEN THE Backend_API SHALL return a not-found response.
5. IF a photograph upload is requested by a Current_User who is not the Tecnico owning the Chair's visit, THEN THE Backend_API SHALL reject the request with an authorization error and SHALL NOT create a `fotografia` row.
6. IF the `fotografia` row cannot be persisted after the file has been stored, THEN THE Backend_API SHALL roll back the database transaction and attempt to remove the stored file.
7. WHERE a compensating file removal fails after a database error, THE Backend_API SHALL log the failure.
8. IF writing the file to storage fails, THEN THE Backend_API SHALL reject the request without creating a `fotografia` row and SHALL avoid leaving a partial file when possible.

### Requirement 4: Consult the photographs of a chair

**User Story:** As an authorized user, I want to consult all photographs registered for a chair, so that I can review the visual evidence. (HU-10)

#### Acceptance Criteria

1. WHEN an authorized Current_User requests the photographs of a Chair, THE Backend_API SHALL return all `fotografia` entries for that Chair, each identifying the photograph and its stored path.
2. WHEN an authorized Current_User retrieves a photograph of a Chair, THE Backend_API SHALL make the stored image file effectively retrievable through an authorized path, not only its metadata.
3. WHERE a Chair has no Photograph, THE Backend_API SHALL return an empty collection.
4. THE Backend_API SHALL apply to the photograph query the same access rules used to read the Chair: a `COMERCIAL_MANSILLAS` may read any Chair's photographs, and a `TECNICO` may read only the photographs of Chairs within their Owned_Visits.
5. IF a photograph query is requested by a Current_User not authorized to read the Chair, THEN THE Backend_API SHALL reject the request with an authorization error.
6. IF the referenced Chair does not exist, THEN THE Backend_API SHALL return a not-found response.
7. THE Backend_API SHALL NOT expose Chair photographs through the public chair-by-token endpoint within this feature, and SHALL NOT expose stored files through any path that bypasses authorization.

### Requirement 5: Reuse of existing schema, auth and conventions

**User Story:** As a maintainer, I want HU-02 and HU-10 built on the existing architecture, so that the MVP stays simple and consistent. (HU-02, HU-10)

#### Acceptance Criteria

1. THE Backend_API SHALL reuse the existing `silla` and `fotografia` tables without altering the database schema.
2. THE Backend_API SHALL resolve authorization through the business RBAC in `app/deps.py` (`get_current_user`, `require_role`, `require_tecnico_owns_visita`).
3. THE Backend_API SHALL store each photograph file in a single storage mechanism, chosen during design as the simplest option sufficient for the MVP deployment, recording its location in `fotografia.ruta_archivo`.
