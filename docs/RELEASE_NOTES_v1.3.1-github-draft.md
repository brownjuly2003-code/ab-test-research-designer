# v1.3.1 — Audit Closure, Local Runner, WCAG Hardening

## Links

- Full release notes: [docs/RELEASE_NOTES_v1.3.1.md](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/RELEASE_NOTES_v1.3.1.md)
- Docker image (after publish): `ghcr.io/brownjuly2003-code/ab-test-research-designer:v1.3.1`
- Docs: https://brownjuly2003-code.github.io/ab-test-research-designer/

## Executive Summary

v1.3.1 is a backward-compatible patch release: audit core F-01…F-10 closed, no-Docker single-port local runner, compute/Slack/API-key hardening, `practical_v1` decision policy, analytical population + PG precision fixes, HF publication path retired, and landing WCAG AA / mobile topbar quality gates. Latest published tag before this cut remains `v1.3.0` until this release is tagged and published.

## What's New

- **Audit core closed.** Population contract (incl. CUPED/ratio), PostgreSQL typing and float64 conversions, Slack body/rate caps, cost-aware compute admission, API key `read`/`write` only + admin token for operator routes, `practical_v1` ship policy, deterministic SQLite connection close.
- **Local-first runner.** `scripts/run_local.py` serves the product on one port without Docker/Compose; seed with `--seed-demo`.
- **GitHub-only path.** HF deploy/maintenance workflows removed from the active tree; HF is not a demo or acceptance target.
- **Frontend quality.** API client domain split, locale parity + ESLint baseline, EmptyState semantic region, accent/muted contrast, mobile topbar wrap, axe WCAG AA gate in e2e smoke.
- **Scientific oracle.** Optional SciPy stack + 97 checks as a CI job/artifact; production deps unchanged.

## Verified local start

```bash
python scripts/run_local.py --bootstrap   # first run only
python scripts/run_local.py --seed-demo
# open http://127.0.0.1:8008
```

## Status (pre-publication)

Source is prepared for **v1.3.1**. Tag, GitHub Release, green Actions on the release SHA, and GHCR image publish are **not claimed done** in this draft — complete those steps after fresh local verification.

See [docs/RELEASE_NOTES_v1.3.1.md](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/RELEASE_NOTES_v1.3.1.md) for the capability matrix, known limitations, and upgrade path.
