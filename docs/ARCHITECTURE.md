# Architecture

## System shape

AB Test Research Designer is a local-first experiment planning tool. The product is intentionally split into deterministic logic, heuristic warnings, optional AI advice, and local persistence.

```text
React + Vite frontend
        |
        v
FastAPI API layer
        |
        +--> deterministic calculator
        |      - binary sample size
        |      - continuous sample size
        |      - duration estimator
        |
        +--> rules engine
        |      - duration / traffic warnings
        |      - contamination / seasonality warnings
        |      - multivariant Bonferroni warning
        |
        +--> report composer
        |      - experiment design
        |      - metrics plan
        |      - risk framing
        |
        +--> local orchestrator adapter
        |      - optional AI recommendations
        |      - retry + backoff + structured fallback
        |
        +--> SQLite repository
               - saved projects
               - analysis run history
               - export event history
```

## Frontend

- `app/frontend/src/App.tsx` coordinates the shell, draft import/export, save/load/archive/restore flows, and result export.
- `components/` holds the wizard, sidebar, results dashboard, and UI primitives such as accordion, metric cards, tooltips, spinner, and status dot.
- `hooks/` isolates stateful logic:
  - `useAnalysis` for validation, loading, and current result state
  - `useDraftPersistence` for browser draft restore/autosave and storage warnings
  - `useProjectManager` for backend health, SQLite project CRUD, history, and comparison
- `lib/experiment.ts` is the typed form model layer, including field config, review rendering, and payload normalization.
- `lib/api.ts` is the network layer. Its contracts are generated from FastAPI OpenAPI into `lib/generated/api-contract.ts`.
- frontend accessibility is gated inside the unit suite with `src/test/a11y-wizard.test.tsx`, `src/test/a11y-results.test.tsx`, and `src/test/a11y-sidebar.test.tsx`
- those tests target WCAG 2.1 AA and fail the frontend gate when wizard, results, sidebar, or modal states regress to critical/serious axe violations

## Backend

- `main.py` wires FastAPI routes, CORS, exception handling, optional frontend dist serving, and request validation.
- `services/calculations_service.py` is the deterministic entry point for statistics + duration + warning assembly.
- `stats/` contains the actual statistical formulas.
- `rules/` holds warning catalog metadata and trigger logic.
- `services/design_service.py` builds the deterministic report used by export and the UI dashboard.
- `llm/adapter.py` calls the local orchestrator and normalizes unreliable responses through `parser.py`.
- `repository.py` owns SQLite schema, migrations, saved projects, history, and comparison inputs.

## Data model

Runtime persistence is centered around:

- `projects`
- `analysis_runs`
- `export_events`

`projects.last_analysis_run_id` points to the latest persisted snapshot. Historical snapshots stay normalized in `analysis_runs` instead of being duplicated into the main project row.

## Runtime modes

- Dev mode: Vite serves the frontend, FastAPI serves the backend on `127.0.0.1:8008`.
- Smoke / demo mode: FastAPI can serve the built frontend dist same-origin.
- Docker mode: one container serves both the backend API and the built frontend.
- Secure Docker mode: the same container path can be protected with `AB_API_TOKEN`, while the frontend accepts a browser-session token at runtime instead of baking secrets into the image.
- Split-access mode: `AB_READONLY_API_TOKEN` can expose read-only diagnostics/docs/project reads while mutations stay behind the write token.
- Signed-backup mode: `AB_WORKSPACE_SIGNING_KEY` adds HMAC signatures to workspace exports and forces signature verification before import on that runtime.

## Design principles

- deterministic math is always available, even when AI is offline
- warnings are heuristic and explicitly separated from calculations
- advisory AI stays optional and never replaces the deterministic report
- optional token protection is transport-level hardening with write and read-only scopes, not a user/role system
- workspace backup authenticity is optional and key-based: checksum-only bundles protect integrity, while signed bundles additionally protect provenance on runtimes that share the signing key
- local persistence is first-class, with project history and export auditability
- the UI keeps current in-memory analysis separate from historical saved snapshots
