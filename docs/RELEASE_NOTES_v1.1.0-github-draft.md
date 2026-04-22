# v1.1.0 — A/B Test Research Designer

## Demo Links

- Hosted demo: https://liovina-ab-test-research-designer.hf.space
- Docker image: *(not published; build locally with `docker compose up --build`)*

## Executive Summary

v1.1.0 extends the v1.0.0 baseline with three parallel post-release initiatives and broader locale coverage. Teams can now compare 2-5 saved experiments side by side, forward audit events to Slack or generic HTTP endpoints, and read the product and its deterministic reports in four languages. The statistical surface also gains a property-based test layer that enforces monotonicity, round-trip, and symmetry invariants across the shipped calculators.

The release is additive: no migrations are required, and every existing API, export, and storage path keeps working unchanged.

## What's New

- **Multi-project comparison dashboard.** `POST /api/v1/projects/compare` returns a side-by-side dashboard for 2-5 saved experiments, with power-curve overlays, a sensitivity grid, forest-plot observed effects, and shared/unique insight panels. Markdown and PDF exports go through `POST /api/v1/export/comparison`. Lazy-loaded React chunk keeps the main bundle unaffected.
- **Outbound webhooks.** New `routes/webhooks.py` + `services/webhook_service.py` surface admin-guarded CRUD at `/api/v1/webhooks`, with per-subscription event filters, retry tracking, and an HMAC `X-AB-Signature` header for generic JSON consumers. Slack incoming-webhook format ships out of the box.
- **Property-based statistical tests.** 37 Hypothesis invariants across binary, continuous, SRM, group-sequential, and Bayesian calculators, added to the verify pipeline.
- **German and Spanish locales.** Backend export and report strings, warning catalog, and schema errors translate via `Accept-Language`. Header switcher now ships EN / RU / DE / ES buttons with `document.documentElement.lang` synchronization.

## Capability Matrix

| Feature | Status | Notes |
| --- | --- | --- |
| Multi-project comparison dashboard | GA | 2-5 projects, Markdown and PDF export, p95 compare under 200 ms on five-project fixture |
| Outbound webhook subscriptions | GA | Slack and generic JSON, admin-guarded, HMAC-signed for generic consumers |
| Hypothesis-based property tests | GA | Runs inside `scripts\verify_all.cmd` |
| German and Spanish locales | GA (backend) / Partial (frontend) | Frontend deep strings fall back to English |
| Experiment design wizard and deterministic sample-size planning | GA | Inherited from v1.0.0 |
| SRM, Bayesian, sequential, CUPED, guardrails | GA | Inherited from v1.0.0 |
| Saved projects, revisions, filters, templates, audit log | GA | Inherited from v1.0.0 |
| Report export: HTML, Markdown, PDF, CSV, XLSX | GA | Now also covers multi-project comparison |
| Accessibility and Lighthouse quality gates | GA | Expanded axe coverage for comparison dashboard, webhook manager, and locale switches |
| AI advice via the local orchestrator adapter | Beta | Unchanged from v1.0.0 |
| Docker packaging for local deployment | Beta | Unchanged from v1.0.0 |

## Known Limitations

- Frontend `de` / `es` translations cover only top-level app chrome; deeper product strings fall back to English via `react-i18next` `fallbackLng`.
- Webhook secrets are stored in plaintext in SQLite; encrypt-at-rest is an additive follow-up.
- Webhook delivery has no per-event ordering guarantees across subscriptions and no deduplication.
- Manual screen-reader (NVDA, JAWS) regression passes are still deferred; automated axe coverage is the enforced gate.
- Fly.io demo hosting remains a single-machine SQLite deployment; horizontal scaling needs Postgres or LiteFS.

## Upgrade Path

No migration required. Optional configuration:

- set `AB_ADMIN_TOKEN` to authorize webhook CRUD and test-delivery endpoints
- send `Accept-Language: de` / `es` / `de-AT` / `es-MX` on `/api/v1/export/markdown` and `/api/v1/export/html` for localized headers

## Verification Steps For Publishing

1. Hosted demo on Hugging Face Spaces verified: `/health` returns `200` with `"version": "1.1.0"`.
2. Re-run `scripts\verify_all.cmd --with-e2e` locally before re-tagging.
3. Attach the assets listed below.

## Verification Commands

```powershell
python scripts/generate_api_docs.py --check
python scripts/generate_frontend_api_types.py --check
scripts\verify_all.cmd --with-e2e
scripts\verify_all.cmd --with-docker
```

## Assets To Attach

- `ab-test-research-designer_1.1.0.tar.gz` (repo HEAD tarball plus `fly.toml`)
- `docs/RELEASE_NOTES_v1.1.0.md`
- `docs/DEPLOY.md`

# How to publish

```bash
gh release create v1.1.0 --draft --notes-file docs/RELEASE_NOTES_v1.1.0-github-draft.md
```
