# Release v1.0.0 Report

## Git

### `git log --oneline -5`

```text
289154e4 release: v1.0.0 — CHANGELOG, version bump, release notes
9882d079 feat: expand axe a11y coverage and fix wizard/dialog/menu accessibility
7a156794 ci: wire lighthouse ci with backend-served frontend and real thresholds
0b63d4b9 feat: expand axe a11y coverage and fix wizard/dialog/menu accessibility
4b28afb5 docs: mark post-Phase-2 wave complete and index CX tasks
```

### `git tag -l -n5 v1.0.0`

```text
v1.0.0          Release 1.0.0 — BCG Phases 1..5 complete, a11y + lighthouse hardening
```

### History Notes

- Duplicate subject detected in the last 15 commits and intentionally left unrevised per task policy: `feat: expand axe a11y coverage and fix wizard/dialog/menu accessibility`
- `git cat-file -t v1.0.0` returned `tag`, so `v1.0.0` is annotated rather than lightweight

## Verify

- `scripts\verify_all.cmd --with-e2e`: exit code `0` on final release HEAD `289154e4`
  - backend tests: `165 passed`
  - backend benchmark: `mean_ms=0.009`, `p95_ms=0.011`, `max_ms=0.076`
- `scripts\verify_all.cmd --with-docker`: exit code `0`
  - log saved to `docs/plans/2026-04-22-v1-docker-verify.log`
- `python scripts/generate_api_docs.py --check`: exit code `0`
  - output: `D:\AB_TEST\docs\API.md is up to date`

## Versions After Bump

- `app/frontend/package.json`: `"version": "1.0.0"`
- `app/frontend/package-lock.json`: root package version updated to `"1.0.0"`
- `app/backend/app/config.py`: default `AB_APP_VERSION` updated to `"1.0.0"`
- `docs/API.md`: regenerated during the release flow and still passes `generate_api_docs.py --check`; the generated markdown does not currently embed a standalone semantic version line

## Deferred to v1.1

- Manual screen-reader audit coverage beyond automated axe checks
- Production HTTPS/TLS termination for Docker deployments
- Bundled or managed LLM orchestration; AI advice still depends on a separately running local orchestrator
