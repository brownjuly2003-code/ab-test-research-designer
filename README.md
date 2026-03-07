# AB Test Research Designer

Local web service for planning A/B experiments.

## Main capabilities

- collect experiment context
- calculate deterministic statistical parameters
- generate deterministic experiment design
- analyze risks with rules
- request optional recommendations from a local LLM orchestrator
- save projects locally in SQLite with activity metadata

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
- project payload schema versioning plus last-analysis and last-export metadata in SQLite
- frontend wizard and results page
- local save, load, update, and export flow verified
- client-side validation before save and analysis requests
- frontend API requests centralized in a dedicated module
- frontend unit tests for helpers and API wrapper
- dedicated review step before analysis with fuller frontend report rendering
- frontend component tests for startup, review, validation, and result rendering flows
- frontend metric inputs now support secondary and guardrail lists
- frontend renders experiment design, metrics plan, and risks from backend reports
- frontend renders the full AI advice payload when the orchestrator returns structured output
- local project management now supports delete from backend to sidebar UI
- frontend shows live backend health, version, and environment status in the sidebar
- frontend supports draft JSON import/export for payload transfer outside SQLite
- frontend restores and autosaves unsaved browser drafts via localStorage
- destructive project deletion in the frontend now asks for confirmation
- saved project editing now surfaces dirty-state before local update
- saved project sidebar now supports search/filter and shows recent update timestamps
- save/update now refreshes the sidebar locally from the returned project record without an extra list round-trip
- backend can optionally serve the built frontend dist for same-origin local smoke and prod-like runs
- Playwright-based local smoke script now verifies a real browser flow against the backend-served frontend
- frontend analysis flow now uses a single combined backend endpoint
- saved-project analysis runs now persist the latest combined analysis snapshot back into SQLite
- report export can now stamp the saved project with the latest export timestamp
- orchestrator parsing now tolerates fenced JSON and returns structured `error_code` values on fallback
- frontend production build verified after dependency install

Remaining:

- optional manual browser walkthrough with a live backend and optional orchestrator
- optional stronger frontend validation beyond build verification

---

## Project structure

- `docs/` specifications and plans
- `archive/` archived non-runtime artifacts moved out of the active tree
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
AB_FRONTEND_DIST_PATH=D:\AB_TEST\app\frontend\dist
AB_SERVE_FRONTEND_DIST=true
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

Run the local browser smoke flow:

```bash
npm run test:smoke
```

Optional frontend env var:

```text
VITE_API_BASE_URL=http://127.0.0.1:8008
```

Behavior:

- in development, frontend defaults to `http://127.0.0.1:8008` if `VITE_API_BASE_URL` is not set
- in production builds, frontend defaults to same-origin requests unless `VITE_API_BASE_URL` is provided
- when `app/frontend/dist` exists, the backend can serve the built frontend from `/`

Open:

```text
http://127.0.0.1:5173
```

The frontend currently supports:

- wizard-based experiment input
- explicit review step before analysis
- client-side validation for the main experiment inputs
- label-to-input bindings for better keyboard/accessibility behavior
- optional secondary and guardrail metrics in the wizard
- run deterministic calculations and report generation
- optional AI advice request
- one-request combined analysis flow via `POST /api/v1/analyze`
- saved project activity routes for analysis snapshots and export metadata
- full AI advice rendering for risks, metric recommendations, pitfalls, and checks
- local project save, update, and delete
- saved project metadata for payload schema, last analysis, and last export timestamps
- local project list/load with automatic load on app start
- startup backend health check with manual refresh in the sidebar
- draft JSON import/export from the wizard without backend round-trips
- browser-local draft restore and autosave between page reloads
- dirty-state feedback when editing a loaded project
- saved project search/filter with updated-at context in the sidebar
- sidebar updates immediately after save/update from the backend save response
- saved-project analysis runs update snapshot metadata in the sidebar when the draft is in sync
- local browser smoke coverage for save, reload, analysis, and export through the backend-served frontend
- Markdown and HTML export from the results block
- full deterministic recommendation rendering for before/during/after test phases
- experiment design, metrics plan, and risks rendering from the backend report

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
