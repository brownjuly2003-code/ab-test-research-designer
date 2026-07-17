---
title: "Release Notes v1.2.0"
editUrl: "https://github.com/brownjuly2003-code/ab-test-research-designer/edit/main/docs/RELEASE_NOTES_v1.2.0.md"
---

# Release Notes v1.2.0

## Executive Summary

v1.2.0 is a hardening and correctness release driven by two internal security/quality audits (2026-07-11 and 2026-07-16). The public demo now runs with the production security posture (`AB_ENV=demo`: webhook SSRF guard and HTTPS-only webhook targets stay active), webhook delivery moved to a durable outbox that survives restarts, and the supply chain is locked end to end: hash-locked Python dependencies, SHA-pinned GitHub Actions, CodeQL analysis, and repository-level Dependabot alerts, secret scanning and push protection.

Statistical correctness also improved: continuous post-test analysis now uses Welch Student-t for both the p-value and the confidence interval (previously a normal approximation), with a stdlib `t_cdf`/`t_ppf` implementation cross-checked against scipy, and `power_achieved` is computed instead of hardcoded to zero.

The release is additive for API consumers: no migrations are required (the schema updates to v15 automatically), and every existing API, export, and storage path keeps working unchanged. The entire dependency tree was refreshed to current versions, including TypeScript 7, vite 8 and pydantic 2.13.

## Capability Matrix

| Feature | Status | Notes |
| --- | --- | --- |
| Demo security posture (`AB_ENV=demo`) | GA | SSRF guard + HTTPS-only webhook targets active on the public Space |
| Durable webhook outbox | GA | Delivery rows committed with their audit event; leased background worker; retries survive restarts |
| Welch Student-t continuous analysis | GA | p-value + CI from `t_cdf`/`t_ppf`; 24 unit cases vs scipy (≤1e-7 / ≤1e-4) |
| Heavy-compute rate-limit bucket | GA | `AB_HEAVY_RATE_LIMIT_*` (default 30/60s) for `projects/compare` + `simulate/bandit` |
| Hash-locked dependencies | GA | uv-compiled universal locks; Docker installs with `--require-hashes` |
| CodeQL + SHA-pinned actions | GA | python + javascript-typescript, PRs / main / weekly |
| Metric capability registry | GA | Single source of truth for planning families and post-hoc analyzers |
| Retention windows + admin purge | GA | Opt-in `AB_RETENTION_*_DAYS`; `POST /api/v1/admin/retention/purge` (dry-run aware) |
| FR / ZH / AR locales with RTL | GA | 7-language switcher; Arabic flips `document.documentElement.dir` |
| Comparison dashboard, webhooks, property tests | GA | Inherited from v1.1.0 |

## Known Limitations

- Single-instance topology: rate limits and counters are in-process (`single_instance` reported on diagnostics); multi-replica deployments need external limits.
- Slack bot/user tokens are stored plaintext in SQLite/Postgres under the local-first threat model (documented in `docs/RUNBOOK.md` with hosted-setup guidance).
- Webhook SSRF guard resolves targets at delivery time; DNS-rebinding between check and connect remains a residual risk (accepted for the demo threat model).
- Docker bases stay on Python 3.13-slim / Node 22-alpine (3.14 / 26 deferred deliberately pending a runtime decision).

## Upgrade Path

1. Pull the `v1.2.0` image or source tree; no migrations required (SQLite/Postgres schema upgrades to v15 automatically on start).
2. If you deploy your own public instance, set `AB_ENV=demo` (or `production`) — `local` keeps the localhost webhook carve-out for development.
3. Optional new knobs: `AB_HEAVY_RATE_LIMIT_REQUESTS` / `AB_HEAVY_RATE_LIMIT_WINDOW_SECONDS`, `AB_RETENTION_*_DAYS`.
4. Backend dependency changes for contributors: direct deps live in `app/backend/requirements*.in`; locks are compiled with `uv pip compile --universal --generate-hashes` (see CONTRIBUTING.md). Do not edit `requirements*.txt` by hand.

## Verification Commands

- `python scripts/verify_all.py` (or `cmd /c scripts\verify_all.cmd`) — backend pytest, frontend vitest, contracts, locale parity, builds, smoke
- `python scripts/generate_frontend_api_types.py --check` — generated API contract in sync (pydantic 2.13 unified schema names)
- `pip-audit -r app/backend/requirements.txt` / `-r app/backend/requirements-dev.txt` — no known CVEs at release time
- `curl https://liovina-ab-test-research-designer.hf.space/health` — expect `"version":"1.2.0"` and `"environment":"demo"`
