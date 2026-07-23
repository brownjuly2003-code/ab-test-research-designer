# Release Checklist

## Before tagging

- confirm working tree is clean
- review `.env.example` and any new runtime settings
- confirm whether `AB_API_TOKEN` should be enabled for the target deployment
- confirm whether `AB_READONLY_API_TOKEN` should be enabled for diagnostics/read-only access
- confirm whether `AB_WORKSPACE_SIGNING_KEY` should be enabled for signed workspace backup/import flows
- confirm target values for `AB_RATE_LIMIT_*`, `AB_AUTH_FAILURE_*`, `AB_MAX_REQUEST_BODY_BYTES`, `AB_MAX_WORKSPACE_BODY_BYTES`, `AB_MAX_SLACK_BODY_BYTES` / `AB_SLACK_RATE_LIMIT_*` / `AB_SLACK_INVALID_SIGNATURE_*`, and `AB_COMPUTE_*` admission knobs
- regenerate OpenAPI-derived artifacts:
  - `python scripts/generate_frontend_api_types.py`
  - `python scripts/generate_api_docs.py`

## Verification

- run `cmd /c scripts\verify_all.cmd`
- or run `python scripts/verify_all.py` on platforms where the batch wrapper is not the preferred entrypoint
- run `cd app/frontend && npm.cmd run test:unit`; this suite includes `src/test/a11y-*.test.tsx` as the frontend accessibility gate
- confirm the a11y gate still targets WCAG 2.1 AA with `0 critical / 0 serious` axe violations across wizard, results, sidebar, and modal states
- run `cmd /c scripts\verify_all.cmd --with-docker` when deployment packaging or auth/runtime config changed
- ensure backend benchmark passes:
  - `python scripts/benchmark_backend.py --payload binary --assert-ms 100`
- ensure workspace backup roundtrip passes:
  - `python scripts/verify_workspace_backup.py --fixture`
  - if signed workspace imports are enabled, rerun with `AB_WORKSPACE_SIGNING_KEY` set
- if Docker-related code changed, run:
  - `docker compose build`
  - `docker compose up -d`
  - `curl http://127.0.0.1:8008/readyz`
  - if auth is enabled, verify read-only token gets `200` on `GET /api/v1/diagnostics`, `200` on stateless `POST /api/v1/calculate`, and `403` on a mutating route such as `POST /api/v1/templates`
  - verify burst requests to `/api/v1/diagnostics` return `429` only after the configured threshold, with `Retry-After`
  - use `python scripts/verify_docker_compose.py --preserve` when you need the same verification without automatic `down -v`

## External acceptance gates

Use this block when a local acceptance pass is already green and the remaining evidence depends on CI, Docker, or external services.

- before push or PR:
  - confirm the tracked tree is clean apart from intended checklist/release files
  - run `git diff --check`
  - do not include root `audit_*.md`, `_*.md`, `.claude/`, `.cx_polls/`, local DB files, caches, or other internal notes in a public deploy payload
- on GitHub Actions after push/PR, require these jobs to pass before treating the branch as externally accepted:
  - `Tests / verify (ubuntu-latest)`
  - `Tests / verify (windows-latest)`
  - `Tests / locale-content`
  - `Tests / repo-hygiene`
  - `Tests / dependency-audit`
  - `Tests / statistical-oracle`
  - `Tests / verify-postgres`
  - `Tests / docker`
  - `Tests / lighthouse`
  - `Tests / frontend-coverage`
  - `CodeQL / analyze (python)`
  - `CodeQL / analyze (javascript-typescript)`
- after CodeQL completes, confirm the repository has no new open alerts for Python or TypeScript. Known accepted alerts must stay documented in `SECURITY.md` or a release note.
- if Docker is unavailable on the local workstation, treat the CI `verify-postgres` and `docker` jobs as the required Linux/Docker evidence. On a Docker-capable Mac/Linux host, the equivalent local commands are:
  - `python -m pytest -p no:schemathesis app/backend/tests/test_postgres_backend.py -q` with `AB_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/abtest`
  - `python scripts/verify_docker_compose.py`
- container publishing is a release gate, not a PR gate. For a release tag or manual publish, require `.github/workflows/docker-publish.yml` to finish after the local single-arch build, Trivy critical-vulnerability scan, and multi-arch GHCR push.
- Hugging Face deploys are manual/tag-driven only. Before dispatching `.github/workflows/deploy-hf.yml`, confirm `HF_TOKEN` is present as a repository secret, `AB_API_TOKEN` is intentionally configured or intentionally absent, and `/health` reports the expected version/build after the Space rebuild.
- destructive HF snapshot drills must use a disposable dataset or Space repository and a write-scoped token created for that drill. Do not run corrupt-latest or rollback tests against the production demo snapshot repository.

## UI evidence

- rerun `python scripts/run_local_smoke.py --skip-build` when the workflow or layout changed
- confirm `docs/demo/` screenshots match current UI

## Storage safety

- export a workspace backup before risky storage changes
- verify workspace import on a fresh SQLite file if repository migrations changed
- check that analysis history, export history, and project revisions survive round-trip import/export

## Docs

- update `README.md` when setup, verification, or endpoints change
- append a short note to `CHANGELOG.md`
- use `CHANGELOG.md` for meaningful milestone-level changes; keep `archive/2026-04-23-bcg-planning-docs/progress.md` as historical reference only
