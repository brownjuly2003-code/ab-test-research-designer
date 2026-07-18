---
title: "Release Notes v1.3.0"
editUrl: "https://github.com/brownjuly2003-code/ab-test-research-designer/edit/main/docs/RELEASE_NOTES_v1.3.0.md"
---

# Release Notes v1.3.0

## Executive Summary

v1.3.0 is a toolchain and operational-safety release. The runtime moves to Python 3.14 and the frontend build to Node 26 across Docker images and every CI lane, closing the deferred Dependabot base-image updates. The one behavioral API change is a safety default: the admin retention purge now runs as a dry run unless deletion is requested explicitly.

Quality gates grew on two fronts: frontend unit-test coverage is now enforced as a dedicated CI job with per-metric floors, and the Playwright e2e layer gains three scenarios beyond the smoke flow (locale switching including Arabic RTL persistence, workspace export→import roundtrip, webhook manager CRUD). Repository operations were tidied up as well — CI badge payloads moved off `main` onto a single-commit orphan branch, CodeQL findings were triaged to zero open alerts, and `main` plus `v*` tags are protected against force-push and deletion.

The release is additive for API consumers apart from the retention-purge default: no migrations are required and every existing API, export, and storage path keeps working unchanged.

## Capability Matrix

| Feature | Status | Notes |
| --- | --- | --- |
| Python 3.14 / Node 26 toolchain | GA | Docker bases `python:3.14-slim` + `node:26-alpine`; CI and mypy target 3.14; 3.13/22 stay supported as local-dev floors |
| Retention purge dry-run default | GA | `POST /api/v1/admin/retention/purge` defaults to `dry_run=true`; deletion needs explicit `dry_run=false` |
| Frontend coverage gate | GA | Dedicated `frontend-coverage` CI job; floors: lines/statements 75, functions 78, branches 67 |
| Extended e2e suite | GA | Locale switching incl. RTL persistence, workspace export→import roundtrip, webhook manager CRUD against an admin-token backend |
| Configurable OpenAI model | GA | `AB_OPENAI_MODEL` (default `gpt-5.6-luna`, replacing the retired `gpt-4o-mini`) |
| Badge payloads off `main` | GA | `update-metrics-badges` force-pushes orphan branch `generated/badges`; README shields read from it |
| CodeQL triage + repo protection | GA | 0 open alerts (1 fixed, 2 dismissed with rationale in SECURITY.md); rulesets block force-push/deletion on `main` and `v*` |
| Welch t, durable webhooks, demo posture | GA | Inherited from v1.2.0 |

## Known Limitations

- Single-instance topology: rate limits and counters are in-process (`single_instance` reported on diagnostics); multi-replica deployments need external limits.
- Slack bot/user tokens are stored plaintext in SQLite/Postgres under the local-first threat model (documented in `docs/RUNBOOK.md` with hosted-setup guidance).
- Webhook SSRF guard resolves targets at delivery time; DNS-rebinding between check and connect remains a residual risk (accepted for the demo threat model).
- The operator session token lives in `sessionStorage` by design (tab-scoped, CSP-mitigated); see SECURITY.md threat model notes.

## Upgrade Path

1. Pull the `v1.3.0` image or source tree; no migrations required.
2. **Behavioral change:** automation calling `POST /api/v1/admin/retention/purge` must now pass `dry_run=false` to actually delete; without it the endpoint reports what would be purged and removes nothing.
3. Optional new knob: `AB_OPENAI_MODEL` for the caller-keyed OpenAI adapter.
4. `.env.example` no longer pins `AB_APP_VERSION`; the release version is baked into `config.py` and the variable is only an override.
5. Local dev floors stay at Python 3.13 / Node 22; CI and Docker run 3.14 / 26.

## Verification Commands

- `python scripts/verify_all.py` (or `cmd /c scripts\verify_all.cmd`) — backend pytest, frontend vitest, contracts, locale parity, builds, bundle budget, smoke
- `python scripts/generate_frontend_api_types.py --check` — generated API contract in sync
- `pip-audit -r app/backend/requirements.txt` / `-r app/backend/requirements-dev.txt` — no known CVEs at release time
- `curl https://liovina-ab-test-research-designer.hf.space/health` — expect `"version":"1.3.0"` and `"environment":"demo"`
