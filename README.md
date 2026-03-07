# AB Test Research Designer

Local web service for planning A/B experiments.

## Main capabilities

- collect experiment context
- calculate deterministic statistical parameters
- generate deterministic experiment design
- analyze risks with rules
- request optional recommendations from a local LLM orchestrator
- save projects locally in SQLite

LLM provider target:
Claude Sonnet 4.6 Thinking

Local orchestrator path:
`D:\Perplexity_Orchestrator2`

---

## Current status

Implemented:

- backend skeleton
- deterministic statistical engine
- rules engine
- deterministic design composer
- local orchestrator adapter
- backend API routes
- Pydantic-validated request/response contracts for core API routes
- local SQLite project storage
- frontend wizard and results page
- local save, load, update, and export flow verified
- client-side validation before save and analysis requests
- frontend API requests centralized in a dedicated module
- frontend unit tests for helpers and API wrapper
- dedicated review step before analysis with fuller frontend report rendering
- frontend component tests for startup, review, validation, and result rendering flows
- frontend production build verified after dependency install

Remaining:

- optional manual browser walkthrough with a live backend and optional orchestrator
- optional stronger frontend validation beyond build verification

---

## Project structure

- `docs/` specifications and plans
- `app/backend/` FastAPI backend
- `app/frontend/` Vite + React frontend
- `exports/` generated reports
- `scripts/` helper scripts
- `tests/` repo-level tests if added later

---

## Run locally

### Backend

Install dependencies:

```bash
cd app/backend
python -m pip install -r requirements.txt
```

Start the API:

```bash
cd D:\AB_TEST
python -m uvicorn app.backend.app.main:app --host 127.0.0.1 --port 8008
```

Optional backend env vars:

```text
AB_DB_PATH=D:\AB_TEST\app\backend\data\projects.sqlite3
AB_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

Health check:

```text
http://127.0.0.1:8008/health
```

API validation:

- request bodies for calculation, design, projects, and export routes are validated by Pydantic
- malformed payloads fail early with `422 Unprocessable Entity`

### Frontend

Install dependencies:

```bash
cd app/frontend
npm install
```

Start Vite:

```bash
npm run dev
```

Run frontend unit tests:

```bash
npm run test:unit
```

Optional frontend env var:

```text
VITE_API_BASE_URL=http://127.0.0.1:8008
```

Behavior:

- in development, frontend defaults to `http://127.0.0.1:8008` if `VITE_API_BASE_URL` is not set
- in production builds, frontend defaults to same-origin requests unless `VITE_API_BASE_URL` is provided

Open:

```text
http://127.0.0.1:5173
```

The frontend currently supports:

- wizard-based experiment input
- explicit review step before analysis
- client-side validation for the main experiment inputs
- label-to-input bindings for better keyboard/accessibility behavior
- run deterministic calculations and report generation
- optional AI advice request
- local project save and update
- local project list/load with automatic load on app start
- Markdown and HTML export from the results block
- full deterministic recommendation rendering for before/during/after test phases

### Optional AI advice

If you want the AI advice block to work, start the local orchestrator:

```bash
cd D:\Perplexity_Orchestrator2
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
```

If the orchestrator is unavailable, deterministic calculations, warnings, design generation, and local project storage still work.

---

## Development notes

Codex CLI is used as the coding agent.

Before coding, read:

1. `progress.md`
2. `AGENT_INSTRUCTIONS.md`
3. `docs/BUILD_PLAN.md`

Detailed architecture is in `docs/`.
