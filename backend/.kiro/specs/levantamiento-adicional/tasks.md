# Implementation Plan: Levantamiento Adicional (HU-02, HU-10)

## Overview

Extend the existing Mansillas SIC backend to close two gaps on the current FastAPI + SQLAlchemy + PostgreSQL stack, with no schema change and no new architectural layers. Tasks are ordered incrementally: HU-02 first (a read endpoint on top of behaviour that already exists), then HU-10 (new `Fotografia` model, local storage + validation, upload, listing/retrieval), closing with an integration/security/contract verification pass.

Chair registration beyond `cantidad_estimada` and the preservation of `cantidad_estimada` are **already implemented** (Davidson's module); those are not re-implemented, only reused and verified. Storage is a single local folder (`PHOTO_STORAGE_DIR`, default `var/fotos/`); Supabase Storage is out of scope for this stage.

Tests run against an **isolated, disposable** PostgreSQL (`TEST_DATABASE_URL`) and never against the shared Supabase database. Integration tests that need that instance stay pending execution until one is available; such tasks note it. No task is complete merely because the plan was generated.

## Tasks

- [x] 1. HU-02 — Chairs-by-visit query (consult real count)
  - [x] 1.1 Verify and reuse the existing chair registration (no new code)
    - Confirm by code inspection that `POST /visitas/{id_visita}/sillas` (`app/routers/sillas.py`) creates chairs without comparing against `visita.cantidad_estimada`, and that visit update in `app/routers/visitas.py` never rewrites `cantidad_estimada` (RN-04). Do NOT add a second registration mechanism. Record the finding; execution of the related test is in task 2.
    - _Files: app/routers/sillas.py, app/routers/visitas.py (read-only)_
    - _Requirements: 1.1, 1.2, 1.3_
    - _Verified by code inspection: `registrar_silla` has no count/estimate comparison; `actualizar_visita` does `datos.pop("cantidad_estimada", None)` and writes only `EDITABLE_FIELDS` (no `cantidad_estimada`). No new code added._
  - [x] 1.2 Add `GET /sillas?id_visita=` to the sillas router
    - In `app/routers/sillas.py` add a chairs-by-visit endpoint: required `id_visita` query param (missing/empty → 422). Load the visit (404 if unknown). Authorize via `app/deps.py`: `COMERCIAL_MANSILLAS` any visit; `TECNICO` only own visit (`require_tecnico_owns_visita`); any other role → 403. Return all `silla` rows of the visit as the existing `SillaOut` (empty list when none). Derive the real count from the list length; store no redundant counter. Do not add component/`sugerir_cambio` fields (Esteban's scope).
    - _Files: app/routers/sillas.py (modify)_
    - _Dependencies: app/deps.py, app/models/silla.py, SillaOut (existing)_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
    - _Implemented. Static checks passed: module import OK (no DB connection), route order correct (`GET /sillas` before `/sillas/token/{token}` and `/sillas/{id_silla}`), endpoint present in the OpenAPI schema. Runtime behaviour not yet executed (needs DB; see task 2)._

- [x] 2. HU-02 — Tests (2.1 written; 2.2 executed 21/21)
  - [x] 2.1 Reuse and extend chair tests
    - Reuse the existing `tests/test_sillas.py::test_sillas_no_se_limitan_por_cantidad_estimada` (Req 1). Add a test asserting `cantidad_estimada` is preserved after registering additional chairs (Req 1.2). Add tests for the listing: returns all chairs of a visit and the count matches (2.1/2.2); existing visit with no chairs → empty list (2.3); unknown visit → 404 (2.4); foreign-visit technician → 403, commercial any → 200, other role → 403 (2.5/2.6/2.7).
    - _Files: tests/test_sillas.py (modify)_
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
    - _Tests written (8 new) and statically checked (syntax + no undefined names). EXECUTED against an isolated, disposable PostgreSQL: `tests/test_sillas.py` 21/21 PASSED (see task 2.2)._
  - [x] 2.2 Execute the HU-02 integration tests
    - Run `uv run pytest tests/test_sillas.py` against an isolated, disposable PostgreSQL (`TEST_DATABASE_URL`), never the shared Supabase database.
    - _Files: tests/test_sillas.py (execute)_
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
    - _Executed by the developer against an independent Supabase project: `tests/test_sillas.py` 21/21 PASSED. HU-02 validated at the integration-test level; end-to-end team integration still pending (see below)._

- [x] 3. HU-10 — Fotografia model
  - [x] 3.1 Map the Fotografia model over the existing table
    - Create `app/models/fotografia.py` mapping the existing `fotografia` table (`id_fotografia` PK, `id_silla`, `ruta_archivo`, `fecha_subida` as `FetchedValue()`), `__table_args__ = {"schema": settings.db_schema}`, mirroring `app/models/silla.py`. Export `Fotografia` from `app/models/__init__.py` (alphabetical order). No schema change.
    - _Files: app/models/fotografia.py (new), app/models/__init__.py (modify)_
    - _Requirements: 5.1_
    - _Implemented. Static checks: imports OK, table `fotografia` with columns `id_fotografia`/`id_silla`/`ruta_archivo`/`fecha_subida`, schema `mansillas`; `id_fotografia` and `fecha_subida` marked `FetchedValue()`; exported in `__all__`._

- [x] 4. HU-10 — Local storage and file validation
  - [x] 4.1 Add storage settings and the `.gitignore` exclusion
    - In `app/config.py` add `photo_storage_dir` (default `var/fotos/` resolved under `BACKEND_DIR`), `photo_max_bytes` (10 MB) and `photo_allowed_formats` (JPEG/PNG/WEBP). Add `backend/var/fotos/` to the repo-root `.gitignore` so stored photos are not versioned (limited to HU-10 generated files).
    - _Files: app/config.py (modify), .gitignore (modify, HU-10 scope only)_
    - _Requirements: 5.3_
    - _Implemented. Added `photo_storage_dir`/`photo_max_bytes`/`photo_allowed_formats` and a `photo_storage_path` property; `.gitignore` excludes `backend/var/fotos/`._
  - [x] 4.2 Implement the storage + validation helper
    - A small helper (e.g. `app/services/fotos_storage.py`) that: reads the upload with a hard cap of `photo_max_bytes + 1` and rejects over-limit files (→ 413) before decoding; validates the upload by real content with Pillow (`Image.open` + `verify()`, reusing `qrcode[pil]`), accepting only JPEG/PNG/WebP and treating `DecompressionBombWarning`/`DecompressionBombError` as validation failures (→ 400 on corrupt/non-image/bomb); writes the bytes under a UUID filename + validated extension inside `PHOTO_STORAGE_DIR` (write-then-rename or delete-partial on write failure); exposes helpers to resolve a stored relative path safely (reject paths escaping the directory), to check file existence, and to delete a stored file. No processing, compression, or thumbnails.
    - _Files: app/services/fotos_storage.py (new)_
    - _Dependencies: app/config.py, Pillow (via qrcode[pil], already installed)_
    - _Requirements: 3.3, 5.3_
    - _Implemented. Executed in isolation (no DB): valid PNG accepted, corrupt/non-image rejected (FotoInvalida), oversize rejected (FotoDemasiadoGrande), UUID save, safe path resolve, path-traversal rejected, delete works._

- [x] 5. HU-10 — Photo upload endpoint
  - [x] 5.1 Implement `POST /sillas/{id_silla}/fotos`
    - Create `app/routers/fotos.py` following the `sillas.py` pattern. `multipart/form-data`, single field `archivo`. Resolve current user; load chair (404 if missing); authorize: only the `TECNICO` owning the chair's visit may upload (else 403), no row created. Validate the file (task 4.2). On success store the file with a UUID name and insert a `fotografia` row (relative path in `ruta_archivo`), allowing multiple photos per chair. Consistency: if the DB commit fails, roll back the transaction and attempt to delete the stored file; if the compensating delete fails, log it; if the file write itself fails, reject with 500 leaving no partial file. Return `201 FotografiaOut` `{id_fotografia, id_silla, ruta_archivo, nombre_archivo, fecha_subida}` where `nombre_archivo` is derived from the stored filename. Wire the router in `app/main.py`.
    - _Files: app/routers/fotos.py (new), app/main.py (modify)_
    - _Dependencies: app/deps.py, app/models/fotografia.py, app/models/silla.py, app/services/fotos_storage.py_
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 5.2_
    - _Implemented. Separates pre-commit failure (file deleted) from post-commit errors (file kept). Route registered in OpenAPI. Runtime behaviour needs DB (see task 7.2)._

- [x] 6. HU-10 — Photo listing and authorized retrieval
  - [x] 6.1 Implement `GET /sillas/{id_silla}/fotos`
    - In `app/routers/fotos.py`: load chair (404 if missing); authorize read with the same rule as reading the chair (`COMERCIAL_MANSILLAS` any, `TECNICO` own visit, else 403); return all `fotografia` rows for the chair as `FotografiaOut` (empty list when none), `nombre_archivo` derived consistently with upload.
    - _Files: app/routers/fotos.py (modify)_
    - _Dependencies: app/deps.py, app/models/fotografia.py_
    - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6_
  - [x] 6.2 Implement `GET /sillas/{id_silla}/fotos/{id_fotografia}` (image stream)
    - Stream the stored image file with the correct image media type, only when the photo exists, its `id_silla` matches the URL (else 404), and the user is authorized to read the chair (else 403/401). Resolve the path through the safe resolver (stay inside `PHOTO_STORAGE_DIR`); if the physical file is missing → 404; do not expose a static public mount; do not add photos to `GET /sillas/token/{token}`. 500 on unexpected read failure without internal detail.
    - _Files: app/routers/fotos.py (modify)_
    - _Dependencies: app/services/fotos_storage.py, app/deps.py_
    - _Requirements: 4.2, 4.4, 4.5, 4.6, 4.7_
    - _Implemented. Streams via `FileResponse` with image media type; missing physical file → 404; both retrieval routes registered in OpenAPI._

- [x] 7. HU-10 — Tests (7.1 written + isolated unit checks run; 7.2 executed 29/29)
  - [x] 7.1 Write `tests/test_fotos.py`
    - Point `PHOTO_STORAGE_DIR` at a pytest `tmp_path`. Setup helpers assert `201` before using chair/photo responses. Cover: upload stores row (checked in PostgreSQL, linked to the chair) and physical file (3.1); two uploads → distinct ids/paths and the listing contains exactly them (3.2); missing multipart `archivo` field → 422 no row; non-image content → 400; valid extension + invalid content → 400; truncated image → 400; disallowed format (GIF) → 400; over-size → 413 — each asserting no row and no file (3.3); unknown chair → 404 no row (3.4); non-owner technician / wrong role → 403 no row/file (3.5); listing all/empty (4.1/4.3); retrieval returns the exact uploaded bytes (4.2); a different commercial can list and retrieve (4.4); photo of another chair via mismatched URL → 404; missing physical file on disk → 404; retrieval by foreign technician → 403, wrong role → 403, unauthenticated → 401; listing unauthorized → 403, unauthenticated → 401 (4.5); unknown chair on query → 404 (4.6); photos absent from the public token endpoint, starting from a successful upload (4.7).
    - Consistency is covered at two levels: (a) **router-level** (dependency override on `get_db`, overrides snapshotted and restored) — a confirmed pre-commit failure compensates (no row, file removed) (3.6); an **uncertain** commit (`DBAPIError` with `connection_invalidated=True`) KEEPS the file (3.6 residual); a post-commit failure (`refresh` raises, re-raised by TestClient and asserted with `pytest.raises`) keeps the committed row and file and does NOT compensate; (b) **storage-helper** isolated cases — write failure leaves no file (3.8) and a failing compensating delete is logged, not raised (3.7).
    - _Files: tests/test_fotos.py (new)_
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
    - _29 tests written and statically checked (syntax + no undefined names + module import). EXECUTED in true isolation (no DB): the 3 storage-helper consistency cases (3.6/3.7/3.8) and the Pillow validation branches (allowed formats, GIF rejected, truncated rejected, unmapped-format config safe). NOT executed: all DB-backed HTTP cases, including the three router-level compensation tests (confirmed pre-commit, uncertain commit, post-commit), which need the isolated PostgreSQL (see 7.2)._
  - [x] 7.2 Execute the HU-10 integration tests
    - Run `uv run pytest tests/test_fotos.py` against an isolated, disposable PostgreSQL (`TEST_DATABASE_URL`), never the shared Supabase database.
    - _Files: tests/test_fotos.py (execute)_
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
    - _Executed by the developer against an independent Supabase project: `tests/test_fotos.py` 29/29 PASSED (one non-blocking deprecation warning). HU-10 validated at the integration-test level; end-to-end team integration still pending._

- [ ] 8. Integration, contracts and security verification (static done; runtime pending)
  - [x] 8.1 Verify endpoints, contracts and security for both HUs (static)
    - Confirm routers are wired in `app/main.py` and visible in Swagger (`/docs`). Check the frontend contracts (read-only) match: `GET /sillas?id_visita=` returns `SillaOut` fields the frontend consumes; `POST /sillas/{id_silla}/fotos` uses multipart field `archivo` and returns `{id_fotografia, ruta_archivo, nombre_archivo, fecha_subida}`; the image endpoint is retrievable via the existing `Authorization: Bearer` mechanism (documented for the frontend owner, no frontend change). Confirm no stored file is reachable without authorization and photos are not exposed publicly by QR. Record which checks were executed vs. verified by inspection; do not declare validated on appearance alone.
    - _Files: app/main.py, app/routers/sillas.py, app/routers/fotos.py (verify)_
    - _Requirements: 2.1, 3.1, 4.1, 4.2, 4.7, 5.1, 5.2, 5.3_
    - _Static checks executed: all routers wired; the three photo routes and `GET /sillas` present in the OpenAPI schema; response model matches the frontend contract (field `archivo`, fields `id_fotografia`/`ruta_archivo`/`nombre_archivo`/`fecha_subida`); no static public mount added; photos absent from the token endpoint by construction. Runtime end-to-end verification over HTTP remains pending the isolated PostgreSQL._

## Technical-closure note

- **Swagger/OpenAPI**: `responses` added to `GET /sillas` and the three `/sillas/{id}/fotos*` endpoints documenting their real codes (`GET /sillas` → 401/403/404; `POST /fotos` → 400/401/403/404/413/500; `GET .../fotos/{id}` → 401/403/404/500 + image media types). Error bodies are the real `{"detail": "..."}`; no invented codes; logic/contracts unchanged.
- **Executed at closure**: `compileall` OK; the developed modules import OK; OpenAPI 3.1.0 generates; the 4 HU-02/HU-10 routes remain registered. The 55 isolated unit tests (`test_otp.py`/`test_email.py`) cover HU-13/HU-15 helpers, not these HUs.
- **Executed (integration)**: against an isolated, disposable PostgreSQL (an independent Supabase project, not the shared team DB) — `tests/test_sillas.py` **21/21 PASSED** (HU-02) and `tests/test_fotos.py` **29/29 PASSED** (HU-10, one non-blocking deprecation warning). HU-02 and HU-10 validated at the integration-test level.
- **Still pending (team integration)**: end-to-end wiring with the other modules and the accepted-content-consistency guard on routes owned by other integrators (documented as a cross-cutting dependency in `gestion-precotizacion`/`aceptacion-precotizacion`).
