# Implementation Plan: Mansillas SIC Backend

## Overview

Build the FastAPI backend over the **existing** `mansillas` PostgreSQL schema. Tasks are ordered strictly by dependency: the schema wiring, SQLAlchemy engine/session, base models, and the `get_current_user` dependency come first because every other feature (and other teammates) depend on them. Chairs depend on visits; serial/observations extend chairs; the QR PDF reads chairs; access logging comes last because it depends on a teammate's `precotizacion` table. Deployment is a single closing task.

Scope is a 2-day MVP. Only three tests are required (critical business rules); everything else is optional and marked with `*`.

## Tasks

- [x] 1. DB schema, engine/session, base models, and current-user dependency
  - [x] 1.1 Set up config and SQLAlchemy engine/session
    - Create `app/config.py` reading `DATABASE_URL` and `FRONTEND_URL` from env (no secrets in source).
    - Create `app/db.py` with the engine using driver `postgresql+psycopg`, `connect_args` setting `options=-c search_path=mansillas`, `SessionLocal`, `Base`, and `get_db`.
    - _Requirements: 8.1_
  - [x] 1.2 Verify the existing mansillas schema is applied
    - Connect to the target DB and confirm tables `empresa`, `sede`, `departamento`, `usuario`, `empleado`, `visita`, `silla`, `acceso_precotizacion`, the `secuencia_qr` sequence, and the `generar_codigo_qr` trigger exist. Apply `backend/database/SQLMansillasSIC.sql` only if missing. Do NOT define a new model.
    - _Requirements: 4.1, 5.2_
  - [x] 1.3 Map base SQLAlchemy models for shared tables
    - One model per table for `empresa`, `sede`, `departamento`, `usuario`, `empleado` under `app/models/`, each with `schema="mansillas"`, mapping only the columns this module uses.
    - _Requirements: 3.1, 8.3_
  - [x] 1.4 Implement get_current_user dependency, dev stub, and role guards
    - `app/deps.py` exposing `get_current_user() -> CurrentUser(id, rol, empresa_id)` with a configurable dev stub, role literals `COMERCIAL_MANSILLAS`/`TECNICO`/`ADMIN_CLIENTE`/`EMPLEADO_CLIENTE`, plus `require_role` and `require_tecnico_owns_visita` helpers.
    - _Requirements: 8.3, 8.4, 8.5, 8.6_
  - [x] 1.5 Create the FastAPI app and wire the session
    - `app/main.py` creating the FastAPI app and reserving `include_router` wiring for each resource router added later.
    - _Requirements: 8.1_
  - [x] 1.6 Seed minimal dev data
    - Insert one `empresa`, one `sede`, one `departamento`, one `empleado`, and two `usuario` rows (one `COMERCIAL_MANSILLAS`, one `TECNICO`) for local development.
    - _Requirements: 8.3_

- [x] 2. Visitas model and CRUD router
  - [x] 2.1 Map the Visita model
    - `app/models/visita.py` mapping `id_visita`, `id_empresa`, `id_sede`, `id_comercial`, `id_tecnico`, `fecha_programada`, `cantidad_estimada`, `estado`, `observaciones`, with `schema="mansillas"`.
    - _Requirements: 1.1, 1.4_
  - [x] 2.2 Implement the visitas router (CRUD + scoping + guards)
    - `app/routers/visitas.py`: `POST /visitas` (COMERCIAL only), `GET /visitas` (COMERCIAL all / TECNICO own via `id_tecnico`), `GET /visitas/{id}` (COMERCIAL any / TECNICO own, else 403/404), `PUT /visitas/{id}` (COMERCIAL, never rewrite `cantidad_estimada` per RN-04), `DELETE /visitas/{id}` (COMERCIAL, 204). Reject missing required fields identifying them. Wire router in `main.py`.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 8.4, 8.6_
  - [x]* 2.3 Write property test — technician sees only their own visits (CRITICAL/REQUIRED)
    - **Property 3: A technician sees only their own visits**
    - **Validates: Requirements 2.1, 2.2**
  - [x]* 2.4 Write unit tests for visita validation and role errors
    - Missing fields → 422/400 listing fields; non-comercial create → 403; `cantidad_estimada` unchanged across PUT (RN-04).
    - _Requirements: 1.2, 1.3, 1.4_

- [x] 3. Sillas with codigo_qr and token_publico
  - [x] 3.1 Map the Silla model
    - `app/models/silla.py` mapping `id_silla`, `id_empresa`, `id_visita`, `id_sede`, `id_departamento`, `id_empleado`, `cargo`, `numero_qr`, `codigo_qr`, `token_publico`, `serial_antiguo`, `observaciones`, with `schema="mansillas"`.
    - _Requirements: 3.1, 4.1, 4.3_
  - [x] 3.2 Implement chair registration endpoint
    - `app/routers/sillas.py`: `POST /visitas/{id_visita}/sillas` (TECNICO on own visit). Require `id_empleado`, `cargo`; derive `id_empresa`/`id_sede`/`id_departamento` from the empleado; validate derived empresa/sede match the visita; insert with empty/null `codigo_qr` so the trigger assigns it; let `token_publico` default to `gen_random_uuid()`; refresh and return `{id_silla, id_empresa, id_sede, id_departamento, id_empleado, cargo, codigo_qr, token_publico}`. Reject missing fields and foreign visit (403). Wire router in `main.py`.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 4.1, 4.3_
  - [x] 3.3 Implement chair read endpoint and token helper
    - `GET /sillas/{id}` (COMERCIAL any / TECNICO own visit) returning `id_empresa, id_sede, id_departamento, id_empleado, cargo` plus `codigo_qr` and `token_publico`. Add internal `get_silla_by_token(db, token) -> Silla | None` (valid token → public fields, unknown → None); `GET` by unknown token returns 404.
    - _Requirements: 3.5, 4.4, 4.5_
  - [x]* 3.4 Write property test — QR codes are never reused (CRITICAL/REQUIRED)
    - **Property 1: QR codes are never reused**
    - **Validates: Requirements 4.1, 4.2**
  - [x]* 3.5 Write unit tests for chair registration
    - Missing fields → error listing them; foreign visit → 403; derived empresa/sede mismatch rejected; token round-trip via `get_silla_by_token`.
    - _Requirements: 3.2, 3.3, 3.4, 4.4, 4.5_

- [x] 4. Serial antiguo and observaciones
  - [x] 4.1 Add serial_antiguo and observaciones to create and update
    - Accept optional `serial_antiguo` and `observaciones` on `POST /visitas/{id_visita}/sillas`; add `PUT /sillas/{id}` (TECNICO own visit) to update them. Catch SQLAlchemy `IntegrityError` from `UNIQUE (id_empresa, serial_antiguo)`, roll back, and return `409` with no partial/mutated row. Return stored `serial_antiguo`/`observaciones` on chair queries.
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - [x]* 4.2 Write property test — duplicate serial rejected per empresa (CRITICAL/REQUIRED)
    - **Property 2: Duplicate legacy serials are rejected per empresa**
    - **Validates: Requirements 5.2**

- [x] 5. Checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. QR label PDF download
  - [x] 6.1 Implement the QR PDF endpoint
    - `app/routers/qr.py`: `POST /qr/pdf` accepting `{ids: [id_silla, ...]}`. Use `qrcode` (ECC level H) to render each chair's public URL `{FRONTEND_URL}/silla/{token_publico}` and `reportlab` to compose a grid, each module ≥ 3 cm × 3 cm with `codigo_qr` printed below; stream `application/pdf`. TECNICO own chairs only (foreign → 403); COMERCIAL any empresa. Keep a batch of 50 within 20 s. Wire router in `main.py`.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_
  - [x]* 6.2 Write unit test for PDF generation and authorization
    - Valid ids → non-empty `application/pdf`; technician requesting a foreign chair → 403.
    - _Requirements: 6.1, 6.5, 6.6_

- [x] 7. Pre-quotation access logging (depends on teammate's precotizacion table)
  - [x] 7.1 Map the acceso_precotizacion model and a reference-only precotizacion model
    - `app/models/acceso.py` mapping `id_acceso`, `id_precotizacion`, `fecha_acceso`, `ip`, `navegador`, `sistema_operativo`; `app/models/precotizacion.py` mapping `id_precotizacion`, `id_empresa` as read-only reference (never written here). Both `schema="mansillas"`.
    - _Requirements: 7.1_
  - [x] 7.2 Implement registrar_acceso and the access-log endpoint
    - `app/routers/accesos.py`: internal `registrar_acceso(db, precotizacion_id, user_agent)` parsing the User-Agent with the `user-agents` library into `navegador`/`sistema_operativo` and inserting one row with the timestamp. `GET /precotizaciones/{id}/accesos` (COMERCIAL) returning the records, or `{mensaje: "Sin accesos registrados"}` when empty; non-comercial → 403. Wire router in `main.py`.
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x]* 7.3 Write unit test for User-Agent parsing and empty access log
    - Known UA → expected `navegador`/`sistema_operativo`; empty log → the "sin accesos" message; non-comercial read → 403.
    - _Requirements: 7.1, 7.3, 7.4_

- [ ]* 8. Deployment and configuration (optional for MVP)
  - Add `requirements.txt`/`pyproject.toml` (fastapi, sqlalchemy, psycopg, qrcode, reportlab, user-agents); configure CORS from `FRONTEND_URL`; document env vars (`DATABASE_URL`, secrets, `FRONTEND_URL`); deploy a pilot on Render or Railway using the same env-var configuration as the Latinoamerican Hosting target.
  - _Status: dependencies, CORS and env var documentation are done (see `backend/README.md`); the pilot deployment was not executed (needs the host credentials)._
  - _Requirements: 8.1, 8.2_

- [x] 9. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional. The three property tests (2.3, 3.4, 4.2) are the only required/critical tests — they cover the three business rules: technician visit isolation, QR codes never reused, and duplicate serial rejected per empresa.
- The schema is reused as-is: `codigo_qr` is filled by the `generar_codigo_qr` trigger and `token_publico` by the `gen_random_uuid()` default — the backend never computes them.
- Access logging (task 7) is last because it depends on another teammate's `precotizacion` table.
- Each task references the specific requirements it implements for traceability.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["1.5", "1.6"] },
    { "id": 3, "tasks": ["2.1"] },
    { "id": 4, "tasks": ["2.2"] },
    { "id": 5, "tasks": ["2.3", "2.4", "3.1"] },
    { "id": 6, "tasks": ["3.2"] },
    { "id": 7, "tasks": ["3.3"] },
    { "id": 8, "tasks": ["3.4", "3.5"] },
    { "id": 9, "tasks": ["4.1"] },
    { "id": 10, "tasks": ["4.2"] },
    { "id": 11, "tasks": ["5"] },
    { "id": 12, "tasks": ["6.1"] },
    { "id": 13, "tasks": ["6.2"] },
    { "id": 14, "tasks": ["7.1"] },
    { "id": 15, "tasks": ["7.2"] },
    { "id": 16, "tasks": ["7.3"] },
    { "id": 17, "tasks": ["8"] },
    { "id": 18, "tasks": ["9"] }
  ]
}
```
