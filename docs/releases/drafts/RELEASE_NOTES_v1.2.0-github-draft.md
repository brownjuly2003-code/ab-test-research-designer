# v1.2.0 — Security Hardening, Welch t Correctness, Supply-Chain Locks

## Demo Links

- Hosted demo: https://liovina-ab-test-research-designer.hf.space
- Docker image: `ghcr.io/brownjuly2003-code/ab-test-research-designer:v1.2.0`
- Docs: https://brownjuly2003-code.github.io/ab-test-research-designer/

## Executive Summary

v1.2.0 is a hardening and correctness release driven by two internal audits. The public demo now runs with the production security posture, webhook delivery moved to a durable outbox, the statistical core fixes continuous post-test analysis to proper Welch Student-t, and the supply chain is locked end to end (hash-locked Python deps, SHA-pinned actions, CodeQL, Dependabot alerts + secret scanning + push protection).

Additive for API consumers: no migrations required; schema updates to v15 automatically.

## What's New

- **Demo security posture.** The public HF Space runs `AB_ENV=demo`: the webhook SSRF guard (private/loopback/link-local targets refused at delivery time) and the HTTPS-only webhook rule stay active on the public host.
- **Durable webhook outbox.** Delivery rows commit in the same transaction as their audit event and are claimed by a background worker under a database lease — retries survive restarts, replicas never race the same row. Diagnostics reports queue depth per status and queue-head age.
- **Welch Student-t continuous analysis.** `analyze_results` uses Student-t for both p-value and CI (was a normal approximation); stdlib `t_cdf`/`t_ppf` implementation, 24 unit cases against scipy (≤1e-7 / ≤1e-4); `power_achieved` computed instead of hardcoded 0.
- **Supply chain.** uv-compiled hash locks (`--require-hashes` in Docker), SHA-pinned GitHub Actions, CodeQL (python + js/ts), repository Dependabot alerts, secret scanning and push protection. Dependency debt cleared to zero: TypeScript 7, vite 8 + plugin-react 6 + vitest 4, Astro 7, mypy 2.3, pydantic 2.13 and the full minor/patch tail.
- **Heavy-compute rate-limit bucket.** `AB_HEAVY_RATE_LIMIT_*` (default 30 req / 60 s) for `projects/compare` and `simulate/bandit` on top of the global window.
- **Ops correctness fixes.** Cross-backend audit log on Postgres (`INSERT … RETURNING id`), rate-limiter per-bucket window pruning, workspace import `BEGIN IMMEDIATE` atomicity, snapshot-loop resilience, API-key audit writes off the auth hot path.
- **Locales.** French, Simplified Chinese and Arabic (with RTL layout) join EN/RU/DE/ES; locale leaf-key parity enforced in CI.
- **Performance.** Lazy-loaded locale JSONs and vendor chunk split: main JS bundle down 50% to 122 KB gzip.

## Verification

- Full `verify_all` pipeline green on ubuntu / windows / postgres CI lanes; 1700+ tests.
- Stat core cross-checked against scipy; property-based Hypothesis suite in the verify path.
- `pip-audit` clean on both dependency locks at release time.

See `docs/RELEASE_NOTES_v1.2.0.md` for the capability matrix, known limitations, and the upgrade path.
