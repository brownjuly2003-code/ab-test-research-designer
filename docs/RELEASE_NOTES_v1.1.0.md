# Release Notes v1.1.0

## Executive Summary

v1.1.0 extends the v1.0.0 baseline with three parallel post-release initiatives and broader locale coverage. Teams can now compare 2-5 saved experiments side by side, forward audit events to Slack or generic HTTP endpoints, and read the product and its deterministic reports in four languages. The statistical surface also gains a property-based test layer that enforces monotonicity, round-trip, and symmetry invariants across the shipped calculators.

The release is additive: no migrations are required, and every existing API, export, and storage path keeps working unchanged.

## Capability Matrix

| Feature | Status | Notes |
| --- | --- | --- |
| Multi-project comparison dashboard | GA | `POST /api/v1/projects/compare` for 2-5 saved projects; Markdown and PDF export via `POST /api/v1/export/comparison`; lazy-loaded React chunk with power curves, sensitivity grid, forest plots, and shared/unique insights |
| Outbound webhook subscriptions | GA | Slack incoming-webhook and generic JSON formats, admin-guarded CRUD, per-subscription event filters, retry with dead-letter history, HMAC `X-AB-Signature` for generic consumers |
| Hypothesis-based property tests | GA | 37 invariants across binary, continuous, SRM, group-sequential, and Bayesian sample-size paths; runs inside `scripts\verify_all.cmd` |
| German and Spanish locales | GA (backend) / Partial (frontend) | Backend report, warning, and export strings fully translated; frontend ships `app.*` chrome in `de`/`es` with automatic fallback to English for deep product strings via `react-i18next` `fallbackLng` |

## Known Limitations

- Frontend `de` and `es` translations cover the top-level app chrome and language switcher; deeper product strings (wizard copy, tooltips, results panels) continue to render in English until the remaining keys are translated.
- Webhook secrets are stored in plaintext in SQLite; encrypt-at-rest can be added later without a schema change.
- Webhook delivery uses a small in-process worker pool with no per-event ordering guarantees across subscriptions and no deduplication.
- Manual screen-reader (NVDA, JAWS) regression passes are still deferred; automated axe coverage remains the enforced gate.

## Upgrade Path

No migration required. Configuration additions are optional:

- set `AB_ADMIN_TOKEN` to authorize webhook CRUD and test-delivery endpoints
- send `Accept-Language: de` or `es` to `/api/v1/export/markdown` and `/api/v1/export/html` for localized headers; regional tags like `de-AT` and `es-MX` fall back to the primary language

## Verification Commands

```powershell
python scripts/generate_api_docs.py --check
python scripts/generate_frontend_api_types.py --check
scripts\verify_all.cmd --with-e2e
scripts\verify_all.cmd --with-docker
```
