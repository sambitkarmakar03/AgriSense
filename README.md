# AgriSense

AgriSense is a decision-support project for farmers. Its first implemented module provides explainable smart-irrigation recommendations; the broader specification also describes crop-disease diagnosis and agronomist review.

> **Current status:** Phase 0 and Phase 1 are complete. The backend, irrigation rules, database schema, tests, and OpenAPI artifact are implemented. The frontend, disease-detection workflow, CI, and deployment are not implemented. There are no live service URLs.

## What Phase 1 provides

- FastAPI with JWT bearer authentication, Argon2id password hashing, farmer/agronomist roles, consent logging, and account deletion.
- Farmer-owned field management and sensor readings, including CSV import and reading history.
- Open-Meteo weather lookup with a graceful fallback to the latest reading when the service or field coordinates are unavailable.
- YAML-driven irrigation knowledge bases v1 and v2, forward-chaining inference, fired-rule explanations, decision history, and manual overrides.
- Versioned irrigation knowledge-base retrieval and updates by an agronomist.
- SQLAlchemy 2 models and an Alembic initial migration for SQLite locally and PostgreSQL in deployment.
- A disease-inference integration stub only; image diagnosis and related endpoints are deferred.

The full technical requirements remain in [docs/SPEC.md](docs/SPEC.md), and [docs/PROGRESS.md](docs/PROGRESS.md) records completed work, verification, and known limitations.

## Architecture

```mermaid
flowchart LR
    Farmer[Farmer] --> Web[Planned React web app]
    Agronomist[Agronomist] --> Web
    Web --> API[Implemented FastAPI API]
    API --> Rules[YAML irrigation knowledge bases + inference engine]
    API --> DB[(SQLite locally / PostgreSQL target)]
    API --> Weather[Open-Meteo]
    API -. future integration .-> Disease[Crop-disease inference stub]
```

## Repository layout

- `backend/app/` — FastAPI routes, configuration, security, SQLAlchemy models, irrigation engine, and disease-inference stub.
- `backend/alembic/` — initial database migration and Alembic configuration.
- `backend/tests/` — API, security, ownership, versioning, and irrigation tests.
- `docs/SPEC.md` — complete requirements; `docs/openapi.json` — generated API contract.
- `frontend/`, `ml/`, `scripts/`, and `.github/workflows/` — Phase 0 placeholders for later work.
- `AGENTS.md` and `GEMINI.md` — project guidance for Codex and Antigravity.

## Run the backend locally

Requires Python 3.11 or newer. These commands run from the repository root and do not require Docker.

### macOS

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
alembic upgrade head
uvicorn app.main:app --reload
```

### Windows PowerShell

```powershell
Set-Location backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:JWT_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(48))")
alembic upgrade head
uvicorn app.main:app --reload
```

The local database defaults to `backend/agrisense.db`. Settings load the repository-root `.env` when present. Use `.env.example` as the variable-name reference, set a private `JWT_SECRET`, and never commit `.env`. The first account matching `ADMIN_EMAIL` is promoted to agronomist.

Once the API is running, interactive documentation is at `http://127.0.0.1:8000/docs`; the generated contract is [docs/openapi.json](docs/openapi.json).

Run backend tests from `backend/`:

```sh
python -m pytest -q
```

The latest audit passed 29 tests. It also verified the SQLite migration cycle and generated PostgreSQL migration DDL. No live PostgreSQL deployment has been tested.

## Available API areas

Authentication and current-user management; field CRUD; manual and CSV readings; weather; irrigation decisions, history, and overrides; irrigation knowledge-base retrieval/versioning; `/health`; and `/about/system`.

Disease diagnosis, diagnosis feedback/history/review, review queue, and analytics are specified but intentionally not implemented yet. The disease module remains a stub, and the frontend and later project phases have not started.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Project structure, rules, specification, environment example, and Git foundation | Complete |
| 1 | Backend, irrigation expert system, migrations, tests, and OpenAPI contract | Complete |
| 2 | Frontend and integration | Not started |
| 3 | Crop-disease model training | Not started |
| 4 | Disease inference and diagnosis workflows | Not started |
| 5 | Frontend integration and browser verification | Not started |
| 6 | Cross-platform CI and deployment configuration | Not started |
| 7 | Deployment and live smoke test | Not started |
| 8 | Final report and viva preparation | Not started |

Codex is assigned backend and CI work; Antigravity is assigned frontend work. Keep changes within the folder named by each task, use `docs/openapi.json` as the frontend/backend contract, and update `docs/PROGRESS.md` after each phase.
