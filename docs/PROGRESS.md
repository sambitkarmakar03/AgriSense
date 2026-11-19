# Development Progress

## Current status
- Phase 0 project initialization and documentation: complete.
- Local Git repository initialized on `main`; no commit or remote created.
- Specification and cross-platform project scaffold are in place; application code is not implemented.

## Verification and source note
- `docs/SPEC.md` was extracted unchanged from the marked specification block in `AgriSense_Prompt_Pack.md`.
- `Pasted text.txt` was not present in the supplied folder; the prompt pack contains the complete marked specification.

## Next and outstanding
- Phase 1 backend work has not started, as requested.
- GitHub repository creation, authentication, and publishing remain outstanding and were not attempted.


## Phase 1 backend implementation
- Implemented FastAPI auth, field CRUD, manual/CSV readings, weather fallback, irrigation decisions/history/overrides, KB retrieval/versioning, health, and system-about endpoints.
- Added SQLAlchemy 2 models for all seven specification entities and an initial Alembic migration.
- Added YAML-driven irrigation KB v1/v2 with IR-1 through IR-6; disease detection remains a structured stub.
- Added pytest coverage for both sets of golden cases, IR-6, auth, ownership, readings, weather fallback, overrides, and KB versioning.
- Verification: 19 tests passed; one upstream Starlette TestClient/httpx deprecation warning.
- Alembic upgrade/check passed; PostgreSQL dialect generated DDL for all seven tables.
- Generated `docs/openapi.json` from FastAPI; all 15 API paths validated.
- Frontend files were not changed. Phase 2 has not started.
- Runtime authentication requires a generated `JWT_SECRET`; root `.env.example` was outside this task's edit scope and remains unchanged.
- Root `README.md` still describes the initial scaffold; left unchanged because it is outside this task's edit scope.


## Backend quality audit (2026-11-19)
- Verified the active Phase 1 API contract: 21 operations across 15 paths; only the account-delete route extends the listed paths and supports the account-deletion privacy requirement.
- Fixed PostgreSQL URL normalization in Alembic so migrations use the installed psycopg 3 driver.
- Hardened KB threshold/action validation, preserved IR-2 priority, and enabled retrieval of packaged and saved historical KB versions.
- Required field properties reject explicit nulls; CORS rejects wildcard origins; CSV uploads are limited to 10 per user per minute.
- JWT configuration now fails before registration writes; Argon2id hashing and token expiry are covered by tests.
- Final pytest result: 29 passed; one upstream Starlette TestClient/httpx deprecation warning remains.
- Fresh Alembic upgrade/downgrade/re-upgrade, schema check, and PostgreSQL offline DDL generation passed.
- `docs/openapi.json` exactly matches the FastAPI schema and documents authentication and CSV rate-limit responses.
- Source audit found no non-empty literal secrets or heavy ML/data dependencies.
- Disease diagnosis, diagnosis feedback/history/review, review queue, and analytics remain deferred; no disease-detection code was added.
- Limitation: CSV throttling is process-local; a multi-worker deployment should also rate-limit at its gateway.


## Phase 0 + Phase 1 GitHub handoff
- Reconciled the README with the implemented backend and explicitly deferred frontend, disease, CI, and deployment work.
- Reviewed the Phase 0 root files, `.env.example`, ignore rules, backend artifacts, tests, migrations, and OpenAPI before staging.
- Configured `origin` to the requested AgriSense GitHub URL; the read-only fetch returned no branch refs at handoff inspection.
- Existing Phase 1 commits are preserved; the handoff adds the remaining Phase 0 foundation without rewriting existing history.

## Phase 2 frontend (2026-11-19)
- Built a responsive React, Vite, TypeScript, Tailwind, and React Router farmer workspace with light and dark themes.
- Added registration and login with backend consent validation, password visibility, form feedback, and session-scoped JWT handling.
- Generated TypeScript API types from `docs/openapi.json` and added a central typed API client with timeout and error handling.
- Added protected routes and a bounded `/health` wake sequence with manual retry and session restoration after recovery.
- Implemented the dashboard with field totals, latest readings, weather, irrigation advice, and recent activity.
- Implemented user-owned field listing, creation, editing, deletion confirmation, crop stages, and location details.
- Added field history charts, manual readings, CSV upload, weather fallback display, and reading history.
- Implemented irrigation decisions, farmer-friendly rule explanations, KB version display, history, and reasoned manual overrides.
- Added system architecture/about content and a limitations/privacy notice linked to official DPDP Act 2023 and Rules 2025 sources.
- Isolated typed preview data behind `VITE_ENABLE_API_MOCKS`; preview mode is visibly labelled and off by default.
- Verification: `npm run lint` passed; `npm run build` passed with route-level code splitting and no chunk-size warning.
- No browser end-to-end session or frontend test suite was run; the repository had no frontend test setup and E2E was excluded by the task.
- Disease diagnosis, agronomist review, rule editing, and analytics remain deferred because those API workflows are not implemented in Phase 1.

## Phase 3 ML training pipeline (2026-11-19)
- Added the MobileNetV2 PlantVillage training, evaluation, quantization, and five-image ONNX parity pipeline under `ml/`.
- Verified the Kaggle PlantVillage source folder names and fixed model output order; mapping is centralized in `ml/train.py`.
- Added Kaggle notebook, separate training requirements, usage instructions, and report directory placeholder. Backend requirements and Phase 0–2 code remain unchanged.
- Local verification: 4 ML helper tests passed; backend pytest passed (29); Python compile and notebook JSON/code-cell parsing passed.
- At the initial pipeline handoff, no dataset/GPU was available and no model artifacts had been generated; the user later supplied the actual Kaggle outputs.

## Phase 3 model and inference integration (2026-11-19)
- Inspected the supplied training notebook and artifact ZIP; confirmed ONNX metadata, float32 tensor names/shapes, four-class order, Softmax output, and QDQ graph nodes.
- Installed the supplied 2.67 MB ONNX model, matching labels, and 11 report files. Model SHA-256: `315b53e105e29331391dc0b3a66bf8d6f965ae6d1981dc217f4b0817ff994779`.
- Supplied report records 12 CUDA epochs and 100% accuracy on 749 held-out PlantVillage images; these split metrics do not establish field-photo accuracy.
- Added CPU-only ONNX inference with metadata validation, RGB conversion, EXIF orientation handling, ImageNet normalization, probability passthrough, and batching.
- Wired authenticated `POST /fields/{field_id}/diagnose`; validates field ownership, image size, and upload rate, and stores prediction plus an EXIF-free 224x224 JPEG thumbnail.
- The endpoint records raw CNN results only. Disease-rule fusion, confidence bands, feedback/history, and human review remain outstanding.
- Verification: actual ONNX CPU smoke/batch inference passed; backend pytest passed (40); OpenAPI regenerated and matches the app; dependency check passed.
