# Release Notes v1.3.1

## Executive Summary

v1.3.1 is a backward-compatible patch that closes the mandatory audit core (F-01…F-10) and hardens quality on the GitHub-only / local-first publication path. It ships cost-aware compute admission, Slack ingress caps, API-key scope tightening, the `practical_v1` decision policy, a unified analytical population contract (including CUPED/ratio), PostgreSQL typing and float64 precision fixes, a no-Docker single-port local runner, frontend structure/i18n/a11y gates, and a scientific oracle CI job. Hugging Face is retired as a publication and demo target; operator acceptance is GitHub (source, Actions, Pages, Releases, GHCR) plus the supported local runtime.

UI quality follows the same patch: mobile topbar wrap so controls no longer overflow, landing semantic regions and accent/muted contrast for WCAG AA, and an e2e smoke axe gate on the landing surface. No migrations are required for API consumers beyond the already-shipped schema upgrades that apply automatically on start.

## Capability Matrix

| Feature | Status | Notes |
| --- | --- | --- |
| Audit core F-01…F-10 closure | GA | Population contract, PG typing, Slack body/rate caps, compute admission, practical_v1 policy, API key scopes, deterministic SQLite close, docs/ops hardening |
| No-Docker single-port local runner | GA | `scripts/run_local.py` bootstrap + serve on one port; README + unit coverage |
| GitHub-only publication path | GA | HF deploy/maintenance workflows removed from the active tree; legacy snapshot code unsupported and outside closure |
| Scientific oracle CI gate | GA | Optional SciPy/statsmodels/lifelines env; 97 differential/metamorphic checks; CI artifact upload |
| Frontend API client split + locale parity | GA | Domain modules under `lib/api/`; ×7 locale parity + static `t()` gate in verify/CI |
| Landing WCAG AA / mobile topbar | GA | Semantic EmptyState region, accent token split, muted contrast; topbar flex-wrap; axe gate in e2e smoke |
| Python 3.14 / Node 26 toolchain | GA | Inherited from v1.3.0 |
| Welch t, durable webhooks, retention dry-run | GA | Inherited from v1.2.0 / v1.3.0 |

## Known Limitations

- Single-instance topology: rate limits and counters are in-process (`single_instance` reported on diagnostics); multi-replica deployments need external limits.
- Slack bot/user tokens are stored plaintext in SQLite/Postgres under the local-first threat model (documented in `docs/RUNBOOK.md` with hosted-setup guidance).
- Webhook SSRF guard resolves targets at delivery time; DNS-rebinding between check and connect remains a residual risk (accepted for the demo threat model).
- The operator session token lives in `sessionStorage` by design (tab-scoped, CSP-mitigated); see SECURITY.md threat model notes.
- Hugging Face is not a publication, acceptance, or demo target. Optional in-repo snapshot code is historical only.

## Upgrade Path

1. Pull the `v1.3.1` image or source tree when the tag/image is published; no hand migrations required (schema upgrades apply on start).
2. Prefer the no-Docker local path for demos: `python scripts/run_local.py --bootstrap` once, then `python scripts/run_local.py` (optional `--seed-demo`) → `http://127.0.0.1:8008`.
3. Operator surfaces (`/api/v1/keys`, `/api/v1/webhooks`) require static `AB_ADMIN_TOKEN`; issued API keys are only `read`/`write` (legacy `admin` scopes normalize to `write`).
4. Automation that hits heavy `/api/v1/results*` or bandit simulation may receive `429 compute_capacity_exceeded` with `Retry-After` under load — treat as capacity, not a client bug.
5. Decision readout `ship` now requires statistical win **and** CI lower bound ≥ design MWE (`practical_v1`); trivial-but-significant effects become `no_ship` / `keep_running`.
6. Do not point deploy or verification at Hugging Face Spaces; use GitHub Releases/GHCR and the local runner.

## Verification Commands

- `python scripts/verify_all.py` (or `cmd /c scripts\verify_all.cmd`) — backend pytest, frontend vitest, contracts, locale parity, builds, bundle budget, smoke
- `python scripts/run_local_smoke.py --skip-build` — canonical UI smoke + `docs/demo/*.png` refresh (after a current frontend production build)
- `python scripts/generate_frontend_api_types.py --check` — generated API contract in sync
- `pip-audit -r app/backend/requirements.txt` / `-r app/backend/requirements-dev.txt` — no known CVEs at release time
- Local health after seed: open `http://127.0.0.1:8008/health` and expect `"version":"1.3.1"`

Publication evidence (tag, GitHub Release, green Actions on the release SHA, GHCR `v1.3.1` image) is recorded separately when those external steps complete — this document does not claim they are already done.
