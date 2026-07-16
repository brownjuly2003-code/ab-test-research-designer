---
title: AB Test Research Designer
emoji: 🧪
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8008
pinned: false
license: mit
editUrl: "https://github.com/brownjuly2003-code/ab-test-research-designer/edit/main/README.md"
---

<!-- docs-site:index:start -->
# AB Test Research Designer

[![Release](https://img.shields.io/github/v/release/brownjuly2003-code/ab-test-research-designer?include_prereleases&display_name=tag)](https://github.com/brownjuly2003-code/ab-test-research-designer/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-LTS-green.svg)](https://nodejs.org/)
[![Tests](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/badges/tests.json)](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/badges/coverage.json)](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/workflows/test.yml)
[![Lighthouse](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/badges/lighthouse.json)](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/workflows/test.yml)
[![Docs](https://img.shields.io/badge/docs-astro--starlight-blue)](https://brownjuly2003-code.github.io/ab-test-research-designer/)

Local-first experiment planning tool for A/B and multi-variant tests. Plan sample size and duration from the wizard, review deterministic statistical guidance (SRM, Bayesian, group-sequential, CUPED) plus design-time guardrail-metric recommendations, compare saved experiments side by side, and export decision-ready reports in seven languages (English, Russian, German, Spanish, French, Simplified Chinese, Arabic with RTL) — all against a local SQLite workspace with no cloud required.

Built with **FastAPI + React 19 + TypeScript + Vite + SQLite**, verified end-to-end via `scripts/verify_all.cmd --with-e2e` (350+ backend tests, 200+ frontend tests, Playwright E2E, Lighthouse CI, axe accessibility checks). Backend coverage gated at 89%+ in CI.

It combines:

- deterministic sample size and duration calculation
- heuristic warnings and feasibility checks
- deterministic experiment design output
- optional local LLM recommendations
- SQLite-backed project storage with history and export metadata
- lightweight runtime diagnostics plus request-id / process-time headers
- baseline security headers, API rate limiting, auth-failure throttling, and request-body size guards
- SQLite schema versioning plus configurable WAL/busy-timeout runtime settings
- optional API token protection for runtime and project APIs
- workspace backup and restore for saved projects plus history, integrity counts, checksums, and optional HMAC signatures
- preflight workspace validation before import, plus runtime SQLite write-probe diagnostics
<!-- docs-site:index:end -->

## Demo

**Live demo:** https://liovina-ab-test-research-designer.hf.space (hosted on Hugging Face Spaces, free CPU tier — first cold request may take a few seconds)

The hosted demo is seeded with four sample projects (checkout conversion, pricing sensitivity, onboarding completion, and feed ad click-through ratio), each with a completed analysis run and seeded live-experiment data (plus an export on the first one), so the sidebar and history views are populated on first load. For Hugging Face Spaces, set `AB_SEED_DEMO_ON_STARTUP=true` in Space Settings.

For persistent hosted state on Hugging Face Spaces, also set:

- `AB_HF_SNAPSHOT_REPO` to the private dataset repo id, for example `liovina/ab-test-designer-snapshots`
- `AB_HF_TOKEN` to a Hugging Face token with dataset write access, stored only as a Space Secret
- `AB_HF_SNAPSHOT_INTERVAL_SECONDS` to control periodic snapshot uploads; default is `900`, and `0` disables the background loop

With those variables configured, the backend restores the latest `projects.sqlite3` snapshot on startup, still runs the idempotent demo seed afterwards (so seeded live-experiment data survives a restore that predates it), uploads periodic dataset snapshots while the Space is running, and attempts one final push during shutdown.

[![GHCR](https://img.shields.io/github/v/tag/brownjuly2003-code/ab-test-research-designer?label=ghcr.io&logo=docker)](https://github.com/brownjuly2003-code/ab-test-research-designer/pkgs/container/ab-test-research-designer)

Deploy your own: see [docs/DEPLOY.md](/ab-test-research-designer/guides/deploy/). Release prep files: [fly.toml](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/fly.toml) and [docs/RELEASE_NOTES_v1.1.0.md](/ab-test-research-designer/guides/release_notes_v1-1-0/).

Sample import payload:

- [docs/demo/sample-project.json](/ab-test-research-designer/demo/sample-project.json)

Current workflow screenshots are generated by the smoke script into `docs/demo/`.
The smoke flow seeds saved demo projects, loads the onboarding example in the wizard,
runs analysis, captures comparison and webhook views, and exports a report:

![Wizard overview](/ab-test-research-designer/demo/wizard-overview.png)
![Review step](/ab-test-research-designer/demo/review-step.png)
![Results dashboard](/ab-test-research-designer/demo/results-dashboard.png)
![Multi-project comparison](/ab-test-research-designer/demo/comparison-dashboard.png)
![Webhook manager](/ab-test-research-designer/demo/webhook-manager.png)

The screenshots follow the real v1.1.0 path through the product: wizard overview, review step, and the post-analysis results dashboard.
They then switch to saved-project comparison to show the multi-project power-curve and forest-plot dashboard with seeded snapshots.
The final image shows the admin-side webhook manager with a seeded Slack-style subscription in the sidebar tools area. The Slack App flow adds OAuth installation and `/ab-test` commands alongside the older one-way webhook path.

<!-- docs-site:case-study:start -->
## Case study: Checkout redesign

Retailer testing two checkout variants against control to lift conversion from a 4.2% baseline.

**Setup** - 80k daily visitors, 50% share into test, 3 variants (34/33/33), alpha = 0.05, power = 0.80, two-sided, relative MDE = 10%.

**Sizing (from `POST /api/v1/calculate`).**

| Metric | Value |
| --- | --- |
| Per-variant sample | 45,429 users |
| Total sample | 136,287 users |
| Required duration | 4 days |
| Bonferroni adjustment | 2 treatment-vs-control comparisons, adjusted alpha 0.025 |

**Design guidance (from `POST /api/v1/design`).**
- Primary risk: More than two variants trigger a Bonferroni alpha correction. This is conservative and may overstate the required sample size.
- Key recommendation: Validate tracking and assignment before exposing live traffic.
- Guardrail to monitor: Payment error rate

**Interim check.**
An early snapshot came in after 1.2 test-days, 48,000 visitors, and 3,812 conversions (35.2% of the planned per-variant sample):
- P(variant A > control) = 93.4%
- P(variant B > control) = 99.8%
Variant A is still ambiguous; variant B is the only treatment with a decisive early signal.

**Decision.**
Stop spending exposure on variant A, keep variant B against control until the planned read is complete, and ship B only if payment error rate and refund value stay in range. The value here is that sizing, multivariant correction, design risks, and the Bayesian interim view all come from the same backend run.

Full inputs and outputs: [docs/case-studies/checkout-redesign.json](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/case-studies/checkout-redesign.json). Rerun with `python scripts/generate_case_study_numbers.py`.
<!-- docs-site:case-study:end -->

## Roadmap

Post-v1.1.0 Tier 2/3 roadmap items are all landed as of 2026-04-25.

**Landed:**
- **Portfolio polish.** HF Space startup seed, v1.1.0 screenshots, case-study section, GHCR Docker publish, dynamic shields.io badges.
- **Product quality.** Locale parity at 940 leaf keys across all shipped UI locales (en/ru/de/es/fr/zh/ar — including the Slack-App admin block), HF Dataset SQLite snapshot service, optional OpenAI/Anthropic adapter via browser-session token, Astro Starlight docs site at [brownjuly2003-code.github.io/ab-test-research-designer](https://brownjuly2003-code.github.io/ab-test-research-designer/), 10-template industry gallery.
- **Hardening.** Monte-Carlo distribution overlay with interactive probability slider, French / Simplified-Chinese / Arabic locales (+RTL for Arabic), extended Hypothesis property coverage (numerical stability + Bayesian edges + Monte-Carlo determinism), bundle optimization (main chunk 247 → 122 KB gzip via lazy-load locales + vendor chunks), optional Postgres backend via `AB_DATABASE_URL` with CI matrix coverage, Slack App integration with OAuth install + slash commands + interactive actions.

**Dropped as out-of-scope for a portfolio/demo:** manual NVDA / JAWS audit (automated axe a11y coverage sufficient here).

## Product shape

- Frontend: React 19 + TypeScript + Vite
- Backend: FastAPI + Pydantic
- Storage: SQLite
- Optional AI path: local orchestrator adapter with retry/backoff
- Verification: backend tests, frontend unit tests, typecheck, build, smoke, Playwright E2E
- CI: [.github/workflows/test.yml](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/.github/workflows/test.yml)
- Container image published to GHCR on each tag (`linux/amd64`, `linux/arm64`)
- canonical cross-platform verification entrypoint: [verify_all.py](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/scripts/verify_all.py) and [verify_all.cmd](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/scripts/verify_all.cmd)

## Main capabilities

- wizard-based experiment input with review step
- deterministic calculations for binary and continuous metrics
- twenty-two-analyzer post-hoc results engine spanning independent two-sample, paired within-subject, omnibus (>2 group), and survival (time-to-event) designs across binary, continuous, ratio, count, and categorical metrics (two-proportion z, Fisher's/Boschloo's/Barnard's exact, Welch's t, TOST equivalence, Mann–Whitney U, bootstrap/permutation, quantile treatment effect, Yuen–Welch trimmed t-test, ratio delta method, Poisson rate, chi-square r×c + Cramér's V, G-test, paired t, Wilcoxon signed-rank, McNemar, Welch's ANOVA, Kruskal–Wallis, log-rank, Fleming–Harrington weighted log-rank, Cox proportional hazards) — see [Statistical repertoire](#statistical-repertoire)
- live-experiment monitoring: SRM detection, sequential (O'Brien–Fleming) and always-valid boundaries, Bayesian P(B>A), multi-covariate CUPED, post-stratification, guardrail metrics with non-inferiority margins, holdout cumulative read, ratio delta-method, identity resolution, late/out-of-order event detection, and a bot/fraud filter
- Bonferroni-aware multivariant sizing notes
- warning engine for traffic, duration, seasonality, campaigns, and design quality
- deterministic report with design, metrics plan, risks, and recommendations
- optional AI advice kept separate from the hard-math output
- optional OpenAI and Anthropic adapters via browser-session token, without backend key persistence
- local project save, load, update, archive, restore, compare, history, and export flows
- saved-project revision history with payload restore into the wizard
- richer snapshot comparison with assumption/risk overlap and recommendation highlights
- full workspace export/import for project, analysis, export-history, and revision backup
- workspace import preflight validation with checksum/reference verification before writes begin
- browser draft restore/autosave plus JSON draft import/export
- workspace status board summarizing saved-project coverage, snapshot depth, exports, and current draft sync state
- read-only aware frontend mode that hides write actions for read-only sessions while keeping every stateless calculator available; `AB_PUBLIC_DEMO=true` turns this into an anonymous public-demo entry with a guest landing over the seeded demo projects

## Statistical repertoire

Post-hoc analysis (`POST /api/v1/results`, plus dedicated `/api/v1/results/ratio`, `/api/v1/results/categorical`, `/api/v1/results/paired`, `/api/v1/results/omnibus` and `/api/v1/results/survival` endpoints) covers twenty-two analyzers across independent two-sample, paired within-subject, omnibus (more-than-two-group), and survival (time-to-event) designs. Each request declares a `metric_type` (or a `test_type` on the dedicated endpoints); the backend validates the matching data shape and rejects mismatches.

| Analyzer | Binary | Continuous | Ratio | Count | Categorical | Survival | `metric_type` / endpoint | Notes |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | --- | --- |
| Two-proportion z-test | ✓ | | | | | | `binary` | Standard proportion significance test |
| Fisher's exact test | ✓ | | | | | | `fisher_exact` | Exact 2×2 test, no normal approximation; capped at 500k total observations |
| Boschloo's exact test | ✓ | | | | | | `boschloo_exact` | Unconditional exact 2×2 test, uniformly at least as powerful as Fisher's; capped at 200 total observations |
| Barnard's exact test | ✓ | | | | | | `barnard_exact` | Unconditional exact 2×2 test ordering tables by the pooled Wald z statistic; capped at 200 total observations |
| Welch's t-test | | ✓ | | | | | `continuous` | Unequal-variance two-sample mean comparison |
| TOST equivalence | | ✓ | | | | | `equivalence` | Two one-sided tests for "no meaningful difference" |
| Mann–Whitney U | | ✓ | | | | | `mann_whitney` | Distribution-free rank test; exact for ≤30 tie-free samples, asymptotic otherwise; reports Hodges–Lehmann shift and rank-biserial effect size |
| Bootstrap / permutation | | ✓ | | | | | `bootstrap` | Resampling test, no distributional assumption; exact enumeration for small samples, fixed-seed Monte Carlo otherwise |
| Quantile treatment effect | | ✓ | | | | | `quantile` | Permutation test on any quantile (default: median), not just the mean |
| Yuen–Welch trimmed t-test | | ✓ | | | | | `trimmed_t` | Robust mean comparison with tail trimming |
| Ratio delta method | | | ✓ | | | | `/results/ratio` | Raw per-user numerator/denominator pairs; reports the delta-method ratio difference with covariance-aware variance |
| Poisson rate | | | | ✓ | | | `count` | Event-rate comparison via a conditional binomial test; capped at 1M events |
| Chi-square r×c + Cramér's V | | | | | ✓ | | `/results/categorical` (`chi_square`) | Independence test across more than two arms/categories; includes a Cochran low-expected-count warning |
| G-test (likelihood-ratio) | | | | | ✓ | | `/results/categorical` (`g_test`) | Likelihood-ratio independence statistic on the same r×c table; shares the chi-square reference distribution and Cramér's V |
| Paired t-test | | ✓ | | | | | `/results/paired` (`paired_t`) | Paired (within-subject) mean comparison on per-pair differences; reports Cohen's dz |
| Wilcoxon signed-rank | | ✓ | | | | | `/results/paired` (`wilcoxon`) | Distribution-free paired test; Hodges–Lehmann pseudomedian and rank-biserial effect size |
| McNemar | ✓ | | | | | | `/results/paired` (`mcnemar`) | Paired binary test on discordant pairs; exact binomial or continuity-corrected chi-square |
| Welch's ANOVA | | ✓ | | | | | `/results/omnibus` (`welch_anova`) | Omnibus mean comparison across more than two groups, robust to unequal variances; reports η² |
| Kruskal–Wallis | | ✓ | | | | | `/results/omnibus` (`kruskal_wallis`) | Distribution-free omnibus across more than two groups; reports ε² |
| Log-rank test | | | | | | ✓ | `/results/survival` (`log_rank`) | k-sample time-to-event comparison (up to 10 arms) with per-arm Kaplan–Meier curves and Greenwood confidence bands |
| Fleming–Harrington weighted log-rank | | | | | | ✓ | `/results/survival` (`fleming_harrington`) | Weighted log-rank w(t) = S(t⁻)^ρ (1 − S(t⁻))^γ; the default (ρ=1, γ=0) emphasizes early differences |
| Cox proportional hazards | | | | | | ✓ | `/results/survival` (`cox`) | Two-arm treatment-effect hazard ratio with Wald confidence interval; HR < 1 means the treatment lowers the event hazard |

The paired and omnibus rows are within-subject and multi-group designs respectively (each with its own dedicated endpoint and `test_type`); the survival rows compare time-to-event data (a duration plus a censoring flag per subject) and return Kaplan–Meier curves alongside the test; the ratio row uses its own endpoint because the delta-method variance needs raw per-user numerator/denominator covariance rather than marginal summaries.

## Local setup

Prerequisites:

- Python 3.13 (the version CI tests and mypy targets)
- Node.js LTS
- Git

Environment template:

- start from [.env.example](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/.env.example)
- set `AB_API_TOKEN` if you want write-capable `/api/v1/*` routes protected
- optionally set `AB_READONLY_API_TOKEN` for read-only access: diagnostics, readiness, docs, `GET` project routes, and the stateless calculation endpoints
- optionally set `AB_PUBLIC_DEMO=true` to give anonymous visitors that same read-only scope (guest landing + calculators, no mutations) for a hosted demo
- optionally set `AB_WORKSPACE_SIGNING_KEY` to HMAC-sign exported workspace backups and require signed imports on that runtime
- optionally set `AB_HF_SNAPSHOT_REPO` and `AB_HF_TOKEN` to restore/persist the SQLite workspace through a private Hugging Face Dataset snapshot
- optionally set `AB_HF_SNAPSHOT_INTERVAL_SECONDS` to change the snapshot cadence; the default is `900`, and `0` disables the background snapshot task
- rate limiting and auth-failure throttling are enabled by default; tune `AB_RATE_LIMIT_*` and `AB_AUTH_FAILURE_*` for stricter or looser local behavior
- request body guards are enabled by default; tune `AB_MAX_REQUEST_BODY_BYTES` and `AB_MAX_WORKSPACE_BODY_BYTES` if you expect unusually large workspace bundles
- when the backend is protected, paste the token into the frontend "API session token" field; it stays only in the current browser session and is not baked into the build

### Backend

```bash
cd app/backend
python -m pip install -r requirements.txt       # runtime only
# for tests/lint/typecheck: python -m pip install -r requirements-dev.txt
cd ../..                                 # back to repo root
python -m uvicorn app.backend.app.main:app --host 127.0.0.1 --port 8008
```

Health:

```text
http://127.0.0.1:8008/health
```

Diagnostics:

```text
http://127.0.0.1:8008/api/v1/diagnostics
```

Readiness:

```text
http://127.0.0.1:8008/readyz
```

### Frontend

```bash
cd app/frontend
npm install
npm run dev
```

Vite default:

```text
http://127.0.0.1:5173
```

## Public API access

The runtime now supports two auth modes for external consumers:

- legacy shared tokens via `AB_API_TOKEN` and `AB_READONLY_API_TOKEN`
- managed database-backed API keys created with `AB_ADMIN_TOKEN`

FastAPI documentation pages stay public:

- Swagger UI: `http://127.0.0.1:8008/docs`
- Redoc: `http://127.0.0.1:8008/redoc`
- OpenAPI JSON: `http://127.0.0.1:8008/openapi.json`

Create a scoped key once `AB_ADMIN_TOKEN` is configured:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/keys \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Partner read key","scope":"read","rate_limit_requests":60,"rate_limit_window_seconds":60}'
```

Use the returned plaintext secret against protected routes:

```bash
curl http://127.0.0.1:8008/api/v1/projects \
  -H "X-API-Key: abk_your_plaintext_key"
```

Only the hash is stored in SQLite, and the plaintext key is shown once at creation time. Legacy shared tokens remain available for backward compatibility and should be documented to external consumers as legacy access.

Configure an outbound webhook for audit events:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/webhooks \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Slack alerts","target_url":"https://hooks.slack.com/services/XXX/YYY/ZZZ","secret":"rotate-me","format":"slack","event_filter":["api_key_created","api_key_revoked","analysis_run_created","workspace_imported","project.archive"],"scope":"global"}'
```

Fire a test delivery:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/webhooks/WEBHOOK_ID/test \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

Generic endpoints receive JSON plus `X-AB-Signature: sha256=...`; Slack subscriptions receive an incoming-webhook payload without signature validation.

For the two-way Slack App, create an app from `slack/app-manifest.yml`, set `AB_SLACK_CLIENT_ID`, `AB_SLACK_CLIENT_SECRET`, and `AB_SLACK_SIGNING_SECRET`, then open `/slack/install`. The app exposes `/ab-test projects`, `/ab-test status <project_id>`, and `/ab-test run <project_id>`.

## Languages

The UI ships with seven locales: **English** (default), **Russian**, **German**, **Spanish**, **French**, **Simplified Chinese**, and **Arabic**. Pick a language from the header switcher (the choice persists to `localStorage` under `ab-test:language`) or set `?lang=fr` on the URL to override auto-detection. Arabic also switches the document into `dir="rtl"` so the shell, panels, toasts, and warning callouts follow the reading direction automatically.

The backend honors the `Accept-Language` header on export endpoints and localizes the markdown/HTML report headers plus warning and risk strings. Regional tags fall back to their primary language: `fr-CA` -> `fr`, `de-AT` -> `de`, `es-MX` -> `es`, `zh-CN` / `zh-TW` -> `zh`, `ar-SA` / `ar-EG` -> `ar`, and unsupported locales fall back to `en`.

```bash
curl -X POST http://127.0.0.1:8008/api/v1/export/markdown \
  -H "Accept-Language: de" \
  -H "Content-Type: application/json" \
  -d @docs/demo/sample-report.json
```

Unsupported locales fall back to English. For instructions on adding another locale, see [docs/RUNBOOK.md#adding-a-new-locale](/ab-test-research-designer/guides/runbook/).

## Docker

Build and run the full stack through the backend-served frontend:

```bash
docker compose up --build
```

Secure local container mode:

```bash
set AB_API_TOKEN=your-secret-token
docker compose up --build
```

Dual-token container mode:

```bash
set AB_API_TOKEN=write-secret-token
set AB_READONLY_API_TOKEN=readonly-secret-token
docker compose up --build
```

Signed-backup container mode:

```bash
set AB_WORKSPACE_SIGNING_KEY=replace-with-a-long-random-secret
docker compose up --build
```

Secure Docker verification:

```bash
cmd /c scripts\verify_all.cmd --with-docker
```

Non-destructive Docker verification:

```bash
python scripts/verify_docker_compose.py --preserve
```

Image publish, registry tagging, rollback, and runtime verification details: [docs/DEPLOY.md](/ab-test-research-designer/guides/deploy/)

Then open:

```text
http://127.0.0.1:8008
```

## Verification

Full local pipeline:

```bash
cmd /c scripts\verify_all.cmd
```

Useful variants:

- `cmd /c scripts\verify_all.cmd --skip-smoke`
- `cmd /c scripts\verify_all.cmd --skip-build`
- `cmd /c scripts\verify_all.cmd --with-e2e`
- `cmd /c scripts\verify_all.cmd --with-e2e --with-lighthouse`
- `cmd /c scripts\verify_all.cmd --with-docker`
- `cmd /c scripts\verify_all.cmd --with-docker-preserve`

The verify pipeline exercises both checksum-only and signed workspace backup roundtrips.
It also covers rate limiting, auth-throttle, request-size enforcement, and workspace checksum/signature regressions through backend tests.

Workspace backup roundtrip drill:

```bash
python scripts/verify_workspace_backup.py --fixture
```

Signed workspace backup roundtrip drill:

```bash
set AB_WORKSPACE_SIGNING_KEY=replace-with-a-long-random-secret
python scripts/verify_workspace_backup.py --fixture
```

Backend calculation benchmark:

```bash
python scripts/benchmark_backend.py --payload binary --assert-ms 100
```

The backend pytest suite also includes an in-repo p95 latency guard for binary and continuous calculations.

Browser E2E:

```bash
cd app/frontend
npm run test:e2e
```

This command builds the frontend if needed and runs Playwright against a temporary backend-served build on a free local port.

## Lighthouse

Build the frontend, start the backend-served dist on port `4174`, and run Lighthouse CI:

```bash
npm --prefix app/frontend run build
python scripts/run_lighthouse_ci.py
```

To include Lighthouse in the full local verification flow:

```bash
cmd /c scripts\verify_all.cmd --with-e2e --with-lighthouse
```

Current Lighthouse thresholds stay strict for accessibility and advisory for other categories:

- performance `>= 0.85` (`warn`)
- accessibility `>= 0.90` (`error`)
- best-practices `>= 0.90` (`warn`)
- seo `>= 0.80` (`warn`)

## Documentation

Active docs:

1. [docs/HISTORY.md](/ab-test-research-designer/guides/history/)
2. [docs/ARCHITECTURE.md](/ab-test-research-designer/guides/architecture/)
3. [docs/API.md](/ab-test-research-designer/guides/api/)
4. [docs/RULES.md](/ab-test-research-designer/guides/rules/)
5. [docs/RUNBOOK.md](/ab-test-research-designer/guides/runbook/)
6. [docs/RELEASE_CHECKLIST.md](/ab-test-research-designer/guides/release_checklist/)
7. [CHANGELOG.md](/ab-test-research-designer/guides/changelog/)

## Notes

- frontend API contracts are generated from FastAPI OpenAPI into `app/frontend/src/lib/generated/api-contract.ts`
- TypeScript strict mode is enabled
- pytest cache artifacts are disabled via `pytest.ini`
- the smoke script updates `docs/demo/` screenshots from a real browser flow
- the smoke flow now verifies the sample import payload before refreshing screenshots
- the Playwright E2E command builds the frontend if needed, starts a temporary backend-served frontend on a free local port, and cleans it up through `scripts/run_frontend_e2e.py`
- LLM adapter timeout/retry behavior can be tuned through `.env.example`
- SQLite busy timeout, journal mode, synchronous mode, and backend log format are configurable through `.env.example`
- optional write-token auth is available through `AB_API_TOKEN`; the frontend can send it as a browser-session token without baking it into the build
- optional read-only auth is available through `AB_READONLY_API_TOKEN` for read-only runtime access (`GET/HEAD/OPTIONS` plus stateless calculation POSTs)
- API responses now include `X-Request-ID` and `X-Process-Time-Ms` headers for lightweight local observability
- responses now also include baseline security headers (`Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`)
- `/api/v1/*` requests now have configurable in-memory rate limiting plus a dedicated auth-failure throttle with `Retry-After` on `429`
- mutating API routes now enforce configurable request-body limits, with a larger dedicated ceiling for workspace import/validate flows
- error responses now also include `error_code`, `status_code`, `request_id`, and `X-Error-Code`
- `GET /readyz` gives a simple readiness view over storage, frontend-dist serving, and runtime config
- `GET /api/v1/diagnostics` now also exposes in-memory runtime counters plus the active guardrail configuration for security headers, rate limiting, auth throttling, and request-body limits
- workspace backup/import now works from the UI and through `GET /api/v1/workspace/export` plus `POST /api/v1/workspace/import`
- workspace backup bundles now include integrity counts and a SHA-256 checksum; when `AB_WORKSPACE_SIGNING_KEY` is configured they also carry an HMAC signature and imports require signature verification on that runtime
- saved projects now retain revision history and can restore older payload snapshots from the UI
