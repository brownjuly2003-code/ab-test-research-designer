# Changelog

## 2026-03-08

### UI modernization

- redesigned the frontend into a dashboard-style interface with metric cards, accordion sections, timeline history, live backend status, progress bar, tooltips, and loading spinners
- added a workspace status board that summarizes saved-project coverage, snapshot depth, export reach, revision depth, and current draft sync state
- made the frontend auth-aware so read-only API sessions disable save, analysis, report export, workspace import, and delete actions instead of failing at runtime
- upgraded typography to Inter + JetBrains Mono and added dark-mode support
- surfaced browser draft storage issues as dismissible UI toasts
- added a quota-specific autosave warning for `QuotaExceededError` while keeping generic storage failure details for other browser-local errors

### Backend and contracts

- added explicit `bonferroni_note` to calculation responses for multivariant designs
- regenerated frontend API contracts from FastAPI OpenAPI
- kept deterministic calculations, warnings, saved-project history, and comparison flows aligned with the new UI
- added backend performance regression coverage with a `<100ms` p95 guard for deterministic calculations
- added `GET /api/v1/diagnostics` with storage/frontend/LLM runtime summary
- added `X-Request-ID` and `X-Process-Time-Ms` headers for lightweight request tracing
- expanded saved-project comparison contracts with executive summaries, warning severity, overlap sections, and comparison highlights
- added `GET /readyz` for runtime readiness checks with `503` on degraded dependencies
- added workspace export/import APIs and UI actions for project/history backup and restore
- added saved-project revision history across create, update, and workspace import flows
- added `GET /api/v1/projects/{project_id}/revisions` plus frontend restore of older payload revisions
- added SQLite schema version reporting plus configurable journal mode, synchronous mode, and busy-timeout diagnostics
- added structured backend logging with configurable plain/json output
- added config validation for invalid ports and broken LLM retry/backoff settings
- expanded CI to also verify the repo on Windows and to check generated API docs
- added workspace backup roundtrip verification to the local/CI verify path
- added optional API token auth for `/api/v1/*`, `/readyz`, and local API docs
- added frontend bearer-token support through `VITE_API_TOKEN`
- added optional read-only API token support for safe runtime requests while keeping mutations behind the write token
- hardened Docker packaging with build-time frontend token injection, runtime defaults, container healthchecks, and secure compose verification
- added workspace backup integrity manifests with entity counts and SHA-256 checksum validation on import
- added `POST /api/v1/workspace/validate` so workspace bundles can be preflight-checked before SQLite writes begin
- added structured API error payloads with `error_code`, `status_code`, `request_id`, and `X-Error-Code`
- added in-memory runtime request/error counters to diagnostics for lightweight observability
- extended diagnostics and readiness with SQLite write-probe, db-size, parent-path, and free-disk reporting

### Documentation and packaging

- added architecture, API, and rules documentation
- aligned the Python verify entrypoint with the Windows batch verify flow, including generated API docs and optional Playwright E2E
- added benchmark script and Docker packaging
- consolidated docs and demo assets for README-driven walkthroughs
- added `docs/RUNBOOK.md` and `docs/RELEASE_CHECKLIST.md` for local operations and release hygiene
- added documented backup roundtrip drill for SQLite workspace restore verification
- added GitHub Actions verification and refreshed smoke/demo automation around the sample import payload
- added a runnable Playwright E2E command, backend launcher, CI browser step, and a few extra statistical boundary regressions

## Earlier milestones

- local SQLite project CRUD, export, history, and comparison flows
- combined `POST /api/v1/analyze`
- local smoke test coverage against the backend-served frontend
- OpenAPI-generated frontend contracts and one-command verification
