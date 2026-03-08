# History

## Current state

AB Test Research Designer is a local single-user experiment planning tool.

The current stack:

- FastAPI backend with typed Pydantic contracts
- React + TypeScript + Vite frontend
- deterministic stats engine for binary and continuous metrics
- rules engine for feasibility and risk warnings
- optional local orchestrator adapter for advisory AI output
- SQLite project storage with analysis and export history

## Delivery timeline

### Foundation

- backend skeleton, config, health, and typed schemas
- deterministic calculation endpoints and report generation
- optional LLM advice endpoint with graceful fallback
- local project CRUD and Markdown/HTML export

### Product workflow

- combined `POST /api/v1/analyze`
- saved-project analysis snapshots and export metadata
- saved-project history and comparison flows
- browser draft restore/autosave and draft JSON import/export
- backend-served frontend smoke coverage

### Hardening

- stricter validation for experiment inputs and variant ranges
- CORS tightened to explicit methods and headers
- generated frontend API contracts from FastAPI OpenAPI
- retry/backoff for transient orchestrator failures
- paginated history metadata and snapshot-based comparison
- runtime snapshot state normalized around `analysis_runs` and `last_analysis_run_id`
- lightweight runtime diagnostics endpoint plus request-id / process-time headers
- repo-level pytest cache suppression to stop root cache artifacts from reappearing
- quota-specific browser draft autosave warnings instead of a single generic storage failure message
- backend performance regression coverage with deterministic latency thresholds
- runnable Playwright E2E coverage with a backend-served frontend launcher and CI browser execution

### Product polish

- dashboard-style results with metric cards, accordion sections, and severity styling
- improved form UX with tooltips, inline validation, progress bar, and loading micro-interactions
- sidebar modernization with live backend indicator, project cards, and history timeline
- richer saved-snapshot comparison with overlap sections, summaries, and recommendation highlights
- dismissible storage warning UI for local draft autosave failures
- Docker packaging and deterministic benchmark script
- architecture, API, rules, changelog, and demo assets added for portfolio-style documentation
- smoke automation now verifies `docs/demo/sample-project.json` import before refreshing README screenshots
- GitHub Actions verification covers contracts, backend tests, frontend checks, benchmark assertion, and Docker startup
- backend boundary tests now explicitly cover invalid variant-rate uplifts, invalid audience shares, invalid baseline means, and invalid traffic weights

## Verification baseline

The working verification path on Windows is:

```bat
cmd /c scripts\verify_all.cmd
```

This runs:

- generated API contract check
- backend pytest suite
- frontend typecheck
- frontend unit tests
- frontend production build
- local smoke flow
- optional Playwright E2E flow via `cmd /c scripts\verify_all.cmd --with-e2e`

## Notes

- `progress.md` remains the running changelog for implementation passes.
- This file replaces the old split between build-plan style notes and current-state history.
