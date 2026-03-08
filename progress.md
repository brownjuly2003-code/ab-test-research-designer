# Project Progress

## Current Phase

Post-phase cleanup completed

---

## Completed

- project structure created
- documentation prepared
- codex setup planned

### Architecture analysis completed

- local orchestrator at `D:\Perplexity_Orchestrator2` analyzed
- HTTP integration selected as the backend communication strategy
- preferred MVP path identified: `POST /api/gk/orchestrate` with Claude
- architecture risks and phased development plan documented and later archived after consolidation

### Phase 1 completed

- created backend configuration loader
- created FastAPI application skeleton
- implemented `/health` endpoint
- added backend dependency list
- added basic backend health test

### Phase 2 completed

- added deterministic binary metric sample size calculation
- added deterministic continuous metric sample size calculation
- added duration estimator based on effective traffic and smallest variant share
- added calculation service to assemble MVP calculation response
- added backend tests for binary, continuous, and duration calculations

### Phase 3 completed

- added warning catalog with MVP rule codes and severities
- added rules engine for duration, traffic, seasonality, campaign, and power warnings
- connected warnings to deterministic calculation results
- added backend tests for warning generation scenarios

### Phase 4 completed

- added deterministic report schema for final experiment output
- added design composer service for full report generation without LLM
- assembled executive summary, calculations, design, metrics, risks, recommendations, and open questions
- added backend test for report generation fallback flow

### Phase 5 completed

- added structured prompt builder for local orchestrator requests
- added JSON parser for AI advice response normalization
- added thin HTTP adapter for `POST /api/gk/orchestrate`
- added graceful fallback for timeout, transport, and parse failures
- added backend tests for successful parsing and fallback behavior

### Phase 6 completed

- added `POST /api/v1/calculate` for deterministic calculations
- added `POST /api/v1/design` for deterministic report generation
- added `POST /api/v1/llm/advice` for optional local orchestrator advice
- added API tests for calculation, design, and graceful AI fallback routes

### Phase 7 completed

- added local SQLite repository for project persistence
- added project list, create, get, and update endpoints
- added API test covering save, load, list, and update flows
- kept storage local and independent from the LLM layer

### Phase 8 completed

- added frontend Vite + React skeleton in `app/frontend`
- added multi-step experiment form covering project, hypothesis, setup, metrics, and constraints
- wired frontend form to backend calculation, design, and AI advice endpoints
- kept AI advice visually separate from deterministic output

### Phase 9 completed

- added results presentation for deterministic calculations
- added warnings block for heuristic checks
- added report block for deterministic experiment design output
- added dedicated AI advice block with graceful unavailable state

### Phase 10 completed

- improved frontend empty, save, success, and error states
- added local save action in the frontend wizard
- updated README with backend, frontend, and optional orchestrator run instructions
- clarified that deterministic functionality works without AI availability

### Export functionality completed

- added backend export service for Markdown and HTML report output
- added `POST /api/v1/export/markdown`
- added `POST /api/v1/export/html`
- added backend tests for both export flows

### End-to-end UX improvement completed

- added saved projects loading flow in the frontend
- added report export buttons for Markdown and HTML
- completed a closed local workflow: fill form, run analysis, save project, reload project, export report

### Post-phase cleanup completed

- verified backend tests locally after recent hardening changes
- verified frontend production build locally after dependency install
- added backend CORS support for the local Vite frontend
- added explicit Pydantic request/response schemas for core backend routes
- corrected multi-variant total sample size calculation and payload validation
- escaped user-provided content in HTML export
- added client-side form validation before save and analysis requests
- split frontend app into focused modules and centralized API calls
- auto-loaded saved projects on frontend startup
- added frontend unit tests for experiment helpers and API wrapper
- added a real frontend review step before analysis
- restored missing constraint fields and fuller deterministic recommendation rendering in the UI
- added frontend component tests for startup, review, validation, and result rendering flows
- linked form labels to inputs for better accessibility and DOM-test stability
- added secondary and guardrail metric inputs to the frontend wizard
- expanded frontend report rendering to include experiment design, metrics plan, and risks
- expanded frontend AI advice rendering to include risks, metric recommendations, pitfalls, and additional checks
- added project delete support across repository, API, frontend sidebar, and tests
- added frontend backend-health status card with startup check and manual refresh
- added draft JSON import/export support for frontend payload transfer
- added browser-local draft restore/autosave on the frontend
- added confirmation before destructive project deletion in the frontend
- archived outdated workspace artifacts and earlier file-tree notes
- updated frontend save flow to update loaded projects instead of always creating duplicates
- made frontend API base configurable through `VITE_API_BASE_URL`
- tightened frontend payload typing and aligned test fixtures with normalized API payloads
- added select-based controls and conditional field visibility in the wizard
- cleaned up optional numeric field handling so blank values do not silently coerce to zero
- added dirty-state feedback for loaded projects plus sidebar search/filter and update timestamps
- tightened frontend save/update flow to use the returned project record and refresh the sidebar without a follow-up list request
- added optional backend serving for the built frontend dist
- added a Playwright-based local smoke script covering save, reload, analysis, and export in a real browser
- split the large frontend wizard rendering into focused draft, review, and results components
- added a combined backend analysis endpoint and switched the frontend analysis flow to a single request
- hardened orchestrator response parsing for fenced JSON, normalized text lists, and structured fallback error codes
- added repository migrations for project activity metadata and payload schema versioning
- added saved-project analysis snapshot and export timestamp routes
- added separate SQLite history tables for analysis runs and export events
- added `GET /api/v1/projects/{project_id}/history` for saved-project activity history
- backfilled legacy `last_analysis_json` snapshots into analysis run history during migration
- wired frontend analysis/export flows to persist saved-project metadata when the draft is in sync
- added repository migration tests plus frontend regressions for project activity metadata
- rendered saved-project history in the frontend sidebar and results view
- linked export metadata to the latest saved analysis run when available
- persisted a current analysis snapshot right after first save when the analysis was done before project creation
- added edge-case statistical regression tests for boundary baselines, invalid MDE, zero std dev, unsupported variant counts, and zero traffic
- tightened backend request validation for continuous metrics and supported variant counts
- replaced wildcard CORS methods and headers with explicit backend configuration
- added shared backend constants for supported variant count and long-duration warning threshold
- added global backend exception handling for structured 400 and 500 API responses
- added local orchestrator retries with exponential backoff for transient request failures
- added generated frontend API contracts from FastAPI OpenAPI components
- added `python scripts/generate_frontend_api_types.py` and a generated TS contract file in the frontend
- added `scripts/verify_all.cmd` as a single local verification entrypoint for the Windows workflow
- added saved-project comparison by latest persisted analysis snapshots across backend and frontend
- replaced repository `SELECT *` usage with explicit project column selection and added latest-analysis lookup
- extended saved-project history with totals and progressive loading metadata
- added compare support for specific saved analysis run ids instead of only latest/latest comparisons
- added frontend opening of historical analysis snapshots without rerunning analysis
- wired historical snapshot preview into report export and compare flows
- normalized runtime snapshot metadata to rely on `last_analysis_run_id` and `analysis_runs`, leaving `last_analysis_json` as migration-only legacy data
- extracted frontend App state orchestration into dedicated `useAnalysis`, `useDraftPersistence`, and `useProjectManager` hooks
- moved App-level CSS into `app/frontend/src/App.css`
- surfaced browser localStorage autosave failures in the UI and clear them after a later successful save
- disabled pytest cache artifacts at the repo level with `pytest.ini`
- consolidated older split docs, setup notes, prompt pack, and env template into `archive/2026-03-08-recommendations-cleanup/`
- redesigned the frontend into a dashboard-style UI with metric cards, accordion sections, timeline history, live backend indicator, tooltips, progress bar, and dark mode support
- surfaced browser draft storage failures as dismissible UI toasts instead of only inline error text
- added explicit `bonferroni_note` to calculation responses for multivariant sizing
- added architecture, API, rules, and changelog documentation plus demo import payload assets
- added a deterministic backend benchmark script and Docker packaging for the full stack
- added a quota-specific localStorage autosave warning for browser storage exhaustion
- updated the smoke flow to import `docs/demo/sample-project.json` before save, reload, analysis, export, and screenshot refresh
- added backend performance regression tests for binary and continuous deterministic calculations
- added a GitHub Actions workflow covering generated contracts, pytest, benchmark assertion, frontend checks, and Docker startup
- archived root `recommendations*.md` audit files into a dedicated archive folder after the checklist was applied
- turned the Node-side Playwright smoke spec into a real `npm run test:e2e` path with a dedicated backend launcher and CI browser step
- added extra backend boundary regressions for invalid variant uplift, invalid audience share, invalid baseline mean, and invalid traffic weights
- added `GET /api/v1/diagnostics` for runtime visibility into SQLite state, frontend-dist serving, LLM adapter settings, and uptime
- added request-level `X-Request-ID` and `X-Process-Time-Ms` headers for lightweight local observability
- expanded saved-project comparison output with executive summaries, warning severity, overlap sections, recommendation highlights, and frontend rendering for those deltas
- added `GET /readyz` to distinguish runtime readiness from basic health checks
- added workspace export/import routes, repository support, and sidebar actions for full project/history backup and restore
- added config validation for malformed env values and extended CI verification to Windows plus generated API docs
- added saved-project revision history across create, update, and workspace import flows
- added `GET /api/v1/projects/{project_id}/revisions` plus frontend restore of older payload revisions into the wizard
- added `docs/RUNBOOK.md` and `docs/RELEASE_CHECKLIST.md` for local operations and release hygiene
- added SQLite schema versioning and runtime diagnostics for journal mode, synchronous mode, and busy-timeout
- added structured backend logging with configurable plain/json output
- added `scripts/verify_workspace_backup.py` and wired backup roundtrip verification into local/CI checks

---

## Next Phase

Optional production hardening

Goals:

- expand Docker usage into a fuller deployment/devcontainer story
- broader deployment/ops hardening if the project moves beyond local-demo scope

---

## Future Phases

No mandatory MVP phases left

---

## Notes

LLM provider:
Claude Sonnet 4.6 Thinking

Access via local orchestrator:

D:\Perplexity_Orchestrator2
