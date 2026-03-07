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
- local SQLite project storage
- frontend wizard and results page

Remaining:

- final manual verification of frontend build
- optional deeper frontend validation after dependency install

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

Health check:

```text
http://127.0.0.1:8008/health
```

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

Open:

```text
http://127.0.0.1:5173
```

The frontend currently supports:

- wizard-based experiment input
- run deterministic calculations and report generation
- optional AI advice request
- local project save
- local project list/load
- Markdown and HTML export from the results block

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
