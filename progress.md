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
- architecture risks and phased development plan documented in `docs/dev_plan.md`

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
- updated frontend save flow to update loaded projects instead of always creating duplicates
- made frontend API base configurable through `VITE_API_BASE_URL`

---

## Next Phase

Optional manual end-to-end validation

Goals:

- run the UI against a live backend in a browser
- optionally validate the AI advice path with the local orchestrator running

---

## Future Phases

No mandatory MVP phases left

---

## Notes

LLM provider:
Claude Sonnet 4.6 Thinking

Access via local orchestrator:

D:\Perplexity_Orchestrator2
