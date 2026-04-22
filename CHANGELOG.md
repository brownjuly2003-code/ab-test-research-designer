# Changelog

## Unreleased

### Added

- Added Checkout-redesign case study section to README with reproducible numbers from backend calculation and Bayesian interim check.
- Regenerated demo screenshots to match v1.1.0 UI (comparison dashboard, webhook manager).
- Seeded the Hugging Face Space demo workspace on startup with an idempotent backend hook so the public demo loads with pre-populated projects.
- Added GitHub Actions workflow `docker-publish.yml` to publish multi-arch Docker images to `ghcr.io/brownjuly2003-code/ab-test-research-designer` on every `v*` tag push.
- Added dynamic shields.io badges (tests count, backend coverage, Lighthouse performance) in README, refreshed by a new CI job `update-metrics-badges` that commits `badges/*.json` back to `main` after green verify + lighthouse runs.
- Added `scripts/collect_badge_metrics.py` plus `--with-coverage` and `--artifacts-dir` flags on `scripts/verify_all.{py,cmd}` so the same collector can run locally and in CI.

## [1.1.0] - 2026-04-21

### Added

- multi-project comparison dashboard with lazy-loaded React chunk, power curves, sensitivity grid, forest-plot observed effects, and shared/unique insight panels, plus `POST /api/v1/projects/compare` and `POST /api/v1/export/comparison` (Markdown and PDF)
- outbound webhook subscriptions (Slack and generic JSON) with admin-guarded CRUD, delivery history, retry/dead-letter tracking, and HMAC-signed `X-AB-Signature` headers for generic consumers
- property-based statistical test suite (`hypothesis==6.152.1`) covering monotonicity and round-trip invariants for binary, continuous, SRM, group-sequential, and Bayesian calculators
- German (`de`) and Spanish (`es`) UI and report locales with `Accept-Language` regional fallback on the backend; header switcher now ships all four languages

### Changed

- `resolve_language` now accepts any registered primary language tag and returns it directly instead of an explicit `en`/`ru` ladder
- bumped backend `app_version` default and frontend `package.json` to `1.1.0`

## [1.0.0] - 2026-04-22

### Added

- experiment template gallery with five YAML presets for common test scenarios (`319820a0`)
- shareable HTML and Markdown reports plus stored project PDF/CSV/XLSX exports for deterministic analysis output (`8413328e`)
- project list filters for faster workspace triage (`0cdfa379`)
- keyboard shortcut help for save, run, and export flows (`0cdfa379`)
- project audit log endpoint and persisted request trail metadata (`7eac8f59`)
- deterministic SRM checks, Bayesian sizing, group sequential boundaries, and CUPED-aware calculations in the shipped analysis stack (`8413328e`)
- multi-metric guardrail planning and report sections across backend and UI (`8413328e`)
- Recharts-powered visualisations, result cards, and sensitivity views in the redesigned frontend (`5ea60181`)
- theme toggle for the refreshed dashboard interface (`5ea60181`)
- expanded axe accessibility coverage across wizard, results, sidebar, and modal flows (`9882d079`)
- Lighthouse CI verification against the backend-served frontend with enforced thresholds (`7a156794`)

### Changed

- decomposed `App` and `ResultsPanel` into smaller route- and store-backed frontend modules for the BCG release wave (`8413328e`)
- moved wizard, analysis, project, draft, and theme state into dedicated Zustand stores (`8413328e`)
- refreshed the UI icon system around Lucide components and the new visual design layer (`5ea60181`)
- regenerated the frontend API contract and backend API docs alongside templates, filters, audit, and report endpoints (`7eac8f59`)
- hardened the workspace backup and recovery flow for local verification and restore drills (`a1d8606c`)

### Fixed

- resolved wizard, dialog, and menu accessibility regressions surfaced by the expanded axe suite (`9882d079`)

## 2026-03-09

### Release hardening

- removed build-time frontend token injection and switched the UI to browser-session API tokens
- made the frontend fail closed for write actions until backend diagnostics explicitly confirm write-capable access
- split soft archive from permanent delete so `POST /api/v1/projects/{id}/archive` preserves history while `DELETE /api/v1/projects/{id}` hard-deletes it
- added optional HMAC-signed workspace backups via `AB_WORKSPACE_SIGNING_KEY`, plus signed import/validate enforcement and runtime diagnostics for backup-signing mode
- extended local verify wrappers, Docker verification, and CI wiring to cover signed workspace backup flows and removed the obsolete `VITE_API_TOKEN` path from CI
- made `scripts/verify_all.ps1` a thin delegation wrapper to the canonical batch verify path so Windows verification no longer drifts
- fixed workspace export/import round-trip regressions so exported bundles now validate and reimport cleanly with matching checksums
- normalized repository boolean fields for project list responses and closed the broken workspace import SQL insert path
- regenerated frontend API contracts and API docs to match the current backend/archive schema
- stabilized the smoke flow around free-port backend startup, browser draft persistence checks, and refreshed demo screenshots
- replaced the Playwright E2E launch path with a self-contained runner that builds the frontend when needed, starts a temporary backend on a free port, and cleans it up after the run
- aligned local verify scripts and CI Playwright installation syntax with the hardened E2E path
- re-ran full local verification, including `python scripts/verify_all.py --with-e2e`

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
- added frontend bearer-token support through `VITE_API_TOKEN` at that stage; this path was later superseded by browser-session tokens
- added optional read-only API token support for safe runtime requests while keeping mutations behind the write token
- hardened Docker packaging with build-time frontend token injection, runtime defaults, container healthchecks, and secure compose verification; the build-time token path was later removed
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
