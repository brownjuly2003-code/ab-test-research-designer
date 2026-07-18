# v1.3.0 — Python 3.14 / Node 26 Toolchain, Safer Admin Defaults, Coverage Gate

## Demo Links

- Hosted demo: https://liovina-ab-test-research-designer.hf.space
- Docker image: `ghcr.io/brownjuly2003-code/ab-test-research-designer:v1.3.0`
- Docs: https://brownjuly2003-code.github.io/ab-test-research-designer/

## Executive Summary

v1.3.0 moves the runtime to Python 3.14 and the frontend build to Node 26 across Docker images and CI, makes the admin retention purge dry-run by default, and adds a frontend coverage gate plus three new Playwright e2e scenarios. CodeQL findings are triaged to zero open alerts and `main`/`v*` tags are protected against force-push and deletion.

Additive for API consumers apart from the retention-purge default; no migrations required.

## What's New

- **Python 3.14 / Node 26.** Docker runtime base `python:3.14-slim`, frontend build stage `node:26-alpine`, all CI jobs and the mypy target on 3.14. Local dev keeps 3.13/22 compatibility floors (ruff `target-version` py313). Closes the deferred Dependabot #89/#91.
- **Safer retention purge.** `POST /api/v1/admin/retention/purge` now defaults to `dry_run=true`; deletion requires an explicit `dry_run=false` — a destructive admin operation no longer deletes on a bare POST.
- **Frontend coverage gate.** Dedicated `frontend-coverage` CI job (vitest v8 coverage) with floors at lines/statements 75, functions 78, branches 67 — kept out of the verify path so the fast suite stays fast.
- **Three new e2e scenarios.** Locale switching incl. Arabic RTL with persistence across reload, workspace export→import roundtrip, and webhook manager create/delete against a second admin-token-enabled backend.
- **Configurable OpenAI model.** `AB_OPENAI_MODEL` on the caller-keyed adapter; default updated from the retired `gpt-4o-mini` to `gpt-5.6-luna`.
- **Cleaner main history.** CI badge payloads moved to a single-commit orphan branch `generated/badges`; README shields read from it, so bot commits no longer touch `main`.
- **Security triage.** CodeQL open alerts down to 0: markdown `tableEscape` sanitization fixed, sessionStorage session-token decision recorded in SECURITY.md, test-intentional DSN logging dismissed as test-only. Rulesets now block force-push/deletion on `main` and `v*` tags.

## Verification

- Full `verify_all` pipeline green including e2e; frontend coverage job green on its floors.
- First multi-arch image build on the 3.14/26 bases published and Trivy-scanned via `docker-publish`.
- `pip-audit` clean on both dependency locks at release time.

See [docs/RELEASE_NOTES_v1.3.0.md](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/RELEASE_NOTES_v1.3.0.md) for the capability matrix, known limitations, and upgrade path.
