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

- `app/frontend/src/App.tsx` renders the shell (language/theme switchers, wizard + sidebar grid) and delegates state to the stores below.
- `components/` holds the wizard, sidebar, results dashboard, comparison views, and UI primitives such as accordion, metric cards, tooltips, spinner, and status dot.
- `stores/` (zustand) isolates stateful logic:
  - `analysisStore` for validation, loading, and current result state
  - `draftStore` for browser draft restore/autosave and storage warnings
  - `projectStore` for backend health, SQLite project CRUD, history, and comparison
  - `wizardStore` for step navigation and onboarding state
  - `themeStore` for light/dark/system theme persistence
- `hooks/` keeps the remaining view-local logic: `useCalculationPreview` (debounced live estimate) and `useToast`.
- `lib/experiment.ts` re-exports the typed form model layer, split into `lib/types.ts`, `lib/validation.ts`, `lib/payload.ts`, and `lib/field-config.ts`.
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
- `repository/` owns persistence. `ProjectRepository` is the entry point; it forwards to a backend chosen from the database URL (`SQLiteBackend`, or `PostgresBackend` which overrides only the dialect and the queries that cannot be translated). The backend is composed from per-domain mixins — `_projects`, `_history`, `_templates`, `_api_keys`, `_webhooks`, `_slack`, `_audit`, `_workspace`, `_diagnostics`, `_execution` — over a shared `_core` (connection, schema bootstrap, revision helpers), with DDL and migrations in `_schema.py` and row mappers in `_rows.py`.

## Data model

The schema (18 tables, versioned through `schema_migrations`) groups into five domains:

- **Design & history** — `projects`, `project_revisions`, `project_templates`, `analysis_runs`, `export_events`. `projects.last_analysis_run_id` points to the latest persisted snapshot; historical snapshots stay normalized in `analysis_runs` instead of being duplicated into the main project row.
- **Execution / live experiment data** — `exposures`, `conversions`, `identity_map`, `excluded_users`, `user_strata`, `pre_period_values`, `pre_period_covariates`. Analytical rollups (primary, holdout, strata, event-timing) share one population contract in `repository/execution/population.py` (`analytical_population_v1`: identity one-hop, first-exposure-wins, manual + rate-spike exclusions).
- **Access control & audit** — `api_keys`, `audit_log`.
- **Integrations** — `webhook_subscriptions`, `webhook_deliveries`, `slack_installations`.
- **Infrastructure** — `schema_migrations` (applied migration ledger; readiness compares it against the version the build expects).

DDL lives in `repository/_schema.py`, migrations in `repository/_migrations.py`.

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
