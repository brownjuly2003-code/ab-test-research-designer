# Release Checklist

## Before tagging

- confirm working tree is clean
- review `.env.example` and any new runtime settings
- confirm whether `AB_API_TOKEN` should be enabled for the target deployment
- confirm whether `AB_READONLY_API_TOKEN` should be enabled for diagnostics/read-only access
- regenerate OpenAPI-derived artifacts:
  - `python scripts/generate_frontend_api_types.py`
  - `python scripts/generate_api_docs.py`

## Verification

- run `cmd /c scripts\verify_all.cmd`
- or run `python scripts/verify_all.py` on platforms where the batch wrapper is not the preferred entrypoint
- run `cmd /c scripts\verify_all.cmd --with-docker` when deployment packaging or auth/runtime config changed
- ensure backend benchmark passes:
  - `python scripts/benchmark_backend.py --payload binary --assert-ms 100`
- ensure workspace backup roundtrip passes:
  - `python scripts/verify_workspace_backup.py --fixture`
- if Docker-related code changed, run:
  - `docker compose build`
  - `docker compose up -d`
  - `curl http://127.0.0.1:8008/readyz`
  - if auth is enabled, verify read-only token gets `200` on `GET /api/v1/diagnostics` and `403` on `POST /api/v1/calculate`

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
- update `progress.md` only for meaningful milestone-level changes
