# Changelog

## Unreleased

### Added

- Added Checkout-redesign case study section to README with reproducible numbers from backend calculation and Bayesian interim check.
- Regenerated demo screenshots to match v1.1.0 UI (comparison dashboard, webhook manager).
- Seeded the Hugging Face Space demo workspace on startup with an idempotent backend hook so the public demo loads with pre-populated projects.
- Added GitHub Actions workflow `docker-publish.yml` to publish multi-arch Docker images to `ghcr.io/brownjuly2003-code/ab-test-research-designer` on every `v*` tag push.
- Added dynamic shields.io badges (tests count, backend coverage, Lighthouse performance) in README, refreshed by a new CI job `update-metrics-badges` that commits `badges/*.json` back to `main` after green verify + lighthouse runs.
- Added `scripts/collect_badge_metrics.py` plus `--with-coverage` and `--artifacts-dir` flags on `scripts/verify_all.{py,cmd}` so the same collector can run locally and in CI.
- Full de/es UI translation (1157 lines, 887 leaf keys per locale, terminology anchors for A/B-Test / Variante / Referenz and test A/B / variante / línea base).
- Hugging Face Dataset snapshot service (`SnapshotService`) pushing SQLite to a private HF Dataset with sha256 verification, atomic rename, startup restore, and opt-in through `AB_HF_SNAPSHOT_REPO` / `AB_HF_TOKEN` / `AB_HF_SNAPSHOT_INTERVAL_SECONDS`.
- mkdocs-material documentation site at [brownjuly2003-code.github.io/ab-test-research-designer](https://brownjuly2003-code.github.io/ab-test-research-designer/), sourced from `docs-site/` and deployed via `.github/workflows/docs.yml` on main push.
- Expanded the template library to 10 industry presets (`email_campaign`, `push_notification_reactivation`, `app_onboarding_drop_off`, `search_ranking_ctr`, `trial_to_paid` added on top of the original 5), with a `TemplateGallery` UI entry point from the sidebar.
- Optional OpenAI / Anthropic LLM adapter with browser-session token routing (`X-AB-LLM-Provider` + `X-AB-LLM-Token` headers, CORS-aware), token masking in logs, and a Settings panel to configure credentials client-side.
- Monte-Carlo distribution view in the comparison dashboard: `simulate_comparison` service (parametric Beta-Bernoulli for binary, Normal bootstrap for continuous, deterministic with `seed=42`), `POST /api/v1/projects/compare?include_monte_carlo=true&monte_carlo_simulations=<1000..50000>` opt-in query, 50-bucket histogram + interactive probability-above-threshold slider.
- French / Simplified-Chinese / Arabic locales with RTL layout support for Arabic (`document.documentElement.dir = "rtl"`, ~10 CSS modules switched to `inset-inline-*` / `margin-inline-*` / `border-inline-*` logical properties), 913 frontend leaf keys and 235 backend keys per locale, 7-button language switcher with `aria-pressed`.
- Extended Hypothesis property-test coverage for numerical stability (degenerate conversions, zero variance, ultra-strict alpha), Bayesian prior edge cases, SRM imbalance, sequential boundary monotonicity, and Monte-Carlo determinism + cap boundaries.
- Optional Postgres backend via `AB_DATABASE_URL` with pluggable `DatabaseBackend` protocol (SQLite default, Postgres via `psycopg[binary]` when URL scheme is `postgresql://`), connection pooling through `AB_DB_POOL_SIZE`, `/healthz` and `/readyz` probes backend-aware, dedicated `verify-postgres` CI matrix job spinning `postgres:16-alpine` via testcontainers.
- Slack App integration bundled alongside Postgres: `slack/app-manifest.yml` for manifest install, OAuth flow with CSRF state, HMAC SHA256 request signature verification with 5-minute replay guard, `/ab-test projects | status <id> | run <id>` slash commands returning Blocks-formatted responses, interactive approve/request-review buttons.
- `scripts/cleanup_test_artifacts.py` — `--dry-run` aware sweeper for pytest temp roots, `.coverage`, the cxkm sandbox, and the local mkdocs `site/` build. Documented in `docs/RUNBOOK.md` under "Local cleanup".
- `scripts/sync_doc_screenshots.py` — mirrors `docs/demo/*.png` (the smoke source of truth, referenced by README via `raw.githubusercontent.com`) into `docs-site/assets/screenshots/` (where mkdocs needs them to be inside `docs_dir`). Compares SHA-256 to skip unchanged pixels. Wired into `.github/workflows/docs.yml` before `mkdocs gh-deploy`. Documented in `docs/RUNBOOK.md` under "Screenshots".
- `docs/RUNBOOK.md` Slack section now documents the token-at-rest posture: bot/user tokens are stored plaintext in SQLite/Postgres under the local-first threat model, with explicit guidance for hosted setups (filesystem permissions, sandbox workspaces, rotation via re-running `/slack/install`).

### Changed

- Lazy-loaded locale JSONs via `i18next-http-backend` (moved to `app/frontend/public/locales/`); main JS chunk dropped from 247.88 KB to 122.18 KB gzip (-50%). Vendor libs split into `vendor-react` / `vendor-i18n` / `vendor-state` chunks for long-term caching.
- Centralized the noop `ResizeObserver` jsdom stub in `app/frontend/src/test/setup.ts`; removed the per-file `vi.stubGlobal('ResizeObserver', …)` boilerplate that was duplicated across 10 chart/a11y test files.
- Postgres CI was extended from a project-creation smoke into a contract suite covering workspace import/export, audit log, API key lifecycle, webhook subscription CRUD, Slack installation upsert, and query-filter pagination. A shared `postgres_repository` module-scoped fixture amortizes the testcontainer pull across the suite.
- `_betacf` (the regularized-beta continued fraction backing Student-t) now emits `StudentTConvergenceWarning` if it ever exhausts its 200-iteration budget; this never fires for `df ≥ 1` and `x ∈ [0, 1]` in practice but guards future numerical regressions instead of returning a silent best-estimate.

### Fixed

- **Continuous post-test math:** `analyze_results` for continuous metrics now uses Welch Student-t for both the p-value and the confidence interval (was returning a normal-approximation p-value with a z-critical CI regardless of `df`). New `app/backend/app/stats/student_t.py` implements `t_cdf`/`t_ppf` via stdlib regularized incomplete beta (zero scipy dep); 24 unit cases assert ≤1e-7 / ≤1e-4 vs scipy. Continuous `power_achieved` is now computed (was hardcoded `0.0`) using a two-sided expression (upper + lower tail) so it equals α at zero observed effect instead of α/2.
- **Workspace import atomicity:** `import_workspace()` now opens a `BEGIN IMMEDIATE` transaction explicitly. Default Python `sqlite3` deferred-mode transactions could race across concurrent imports.
- **Snapshot loop resilience:** the periodic HF snapshot push is now wrapped in `try/except` so a transient failure logs and continues instead of killing the background task silently.
- **Rate limiter memory:** `SlidingWindowRateLimiter` periodically prunes buckets whose last event is outside the window. Long-uptime deployments no longer accumulate state for rotated client IPs/API keys.
- **Pytest on Windows:** `pytest.ini` now sets `--basetemp=.pytest_basetemp` so the default `python -m pytest` command works without manual flags. Legacy `app/backend/tests/.tmp/` (~990 MB on long-lived checkouts) removable via new `scripts/cleanup_test_artifacts.py`.
- **Locale parity:** ar/de/es/fr/zh receive the missing `sidebarPanel.slackApp.*` block (12 keys); locale leaf-key counts now match en for all shipped locales.
- **OpenAPI metadata:** `license_info` is now `MIT` (was `UNLICENSED`); the placeholder contact email was removed, eliminating the `email-validator not installed` warning during contract/API-doc generation.
- **Cross-backend audit log:** `log_audit_entry` now uses `INSERT … RETURNING id` instead of `cursor.lastrowid`, which `_PostgresCursorResult` always returns as `None`; audit events were silently dropped from API responses when running on Postgres.
- **Rate limiter prune correctness:** `_prune_locked` now respects the per-call `window_seconds` override stored on each bucket. Previously a bucket with an API-key-specific longer window would be evicted at the global window boundary; the next call with the override saw an empty bucket and silently bypassed its limit.
- `.env.example`: `AB_DB_PATH` and `AB_FRONTEND_DIST_PATH` are now commented templates (the backend already derives absolute defaults from the package location). The earlier relative-path defaults broke through `Path('./...').as_posix()` → `sqlite:///app/...` resolving to absolute `/app/...`. `AB_ADMIN_TOKEN=` added so secure self-hosted setup works from copy-paste.
- mkdocs `--strict` no longer warns: `docs-site/features/database.md` is added to the Features nav.
- Accessibility tests (`PosteriorPlot`, `a11y-results` full-panel, `a11y-comparison-dashboard`) no longer time out: a flat recharts mock in `app/frontend/src/test/recharts-stub.tsx` removes 1000+ SVG nodes per chart from axe's scan, reducing full-panel axe duration from 15-30s to ~3s. The deleted visual `.recharts-area-area` assertion was preserved in a new `PosteriorPlot.integration.test.tsx` using a ResponsiveContainer-only clone-element mock so real recharts renders in jsdom.
- `ProjectRepository` now handles unix-absolute SQLite URLs (`sqlite:////home/user/db.sqlite3`) without doubling the leading slash, fixing `test_diagnostics_endpoint` path assertion on Linux CI.
- Postgres integration tests skip on Windows CI where Docker Linux containers are unavailable (`testcontainers-ryuk` 404 on container create).
- Hypothesis property tests uncovered and fixed degenerate-input guards in `calculations_service`: zero variance continuous, conversion in {0, 1}, `mde = 0`, ultra-strict alpha.

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
