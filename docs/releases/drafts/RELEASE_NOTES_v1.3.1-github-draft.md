# v1.3.1 — Audit Closure, Local Runner, WCAG Hardening

## Links

- Full release notes: [docs/RELEASE_NOTES_v1.3.1.md](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/RELEASE_NOTES_v1.3.1.md)
- GitHub Release: https://github.com/brownjuly2003-code/ab-test-research-designer/releases/tag/v1.3.1
- Release commit: `bb314ae15c86eaf2ade77d3a111a66030b77573e`
- Docker image: `ghcr.io/brownjuly2003-code/ab-test-research-designer:v1.3.1` (also `1.3.1`, `latest`, `sha-bb314ae`)
  - digest: `sha256:1d02d8a09f790815127ef5c43792f3a3a809a0f872e6fa9434ed6ea957e8baac`
- Docs: https://brownjuly2003-code.github.io/ab-test-research-designer/

## Executive Summary

**v1.3.1** is the current published release: a backward-compatible patch with audit core F-01…F-10 closed, no-Docker single-port local runner, compute/Slack/API-key hardening, `practical_v1` decision policy, analytical population + PG precision fixes, HF publication path retired, and landing WCAG AA / mobile topbar quality gates.

## What's New

- **Audit core closed.** Population contract (incl. CUPED/ratio), PostgreSQL typing and float64 conversions, Slack body/rate caps, cost-aware compute admission, API key `read`/`write` only + admin token for operator routes, `practical_v1` ship policy, deterministic SQLite connection close.
- **Local-first runner.** `scripts/run_local.py` serves the product on one port without Docker/Compose; seed with `--seed-demo`.
- **GitHub-only path.** HF deploy/maintenance workflows removed from the active tree; HF is not a demo or acceptance target.
- **Frontend quality.** API client domain split, locale parity + ESLint baseline, EmptyState semantic region, accent/muted contrast, mobile topbar wrap, axe WCAG AA gate in e2e smoke.
- **Scientific oracle.** Optional SciPy stack + 97 checks as a CI job/artifact; production deps unchanged.

## Verified local start

```bash
python scripts/run_local.py --bootstrap   # first run only
python scripts/run_local.py
# optional: python scripts/run_local.py --seed-demo
# open http://127.0.0.1:8008
```

## Publication status

Published as tag **`v1.3.1`** on commit `bb314ae15c86eaf2ade77d3a111a66030b77573e`.

| Workflow | Run | Result |
|---|---|---|
| Tests | [30534255932](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30534255932) | success on release SHA |
| CodeQL | [30534256094](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30534256094) | success |
| Pages / docs | [30534256023](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30534256023) | success |
| GHCR publish | [30534834319](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30534834319) | success (build, critical-vuln scan, multi-arch) |

GHCR: `ghcr.io/brownjuly2003-code/ab-test-research-designer` tags `v1.3.1`, `1.3.1`, `latest`, `sha-bb314ae` → digest `sha256:1d02d8a09f790815127ef5c43792f3a3a809a0f872e6fa9434ed6ea957e8baac`.

See [docs/RELEASE_NOTES_v1.3.1.md](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/RELEASE_NOTES_v1.3.1.md) for the capability matrix, known limitations, and upgrade path.
