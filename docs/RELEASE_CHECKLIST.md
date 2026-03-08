# Release Checklist

## Before tagging

- confirm working tree is clean
- review `.env.example` and any new runtime settings
- regenerate OpenAPI-derived artifacts:
  - `python scripts/generate_frontend_api_types.py`
  - `python scripts/generate_api_docs.py`

## Verification

- run `cmd /c scripts\verify_all.cmd`
- ensure backend benchmark passes:
  - `python scripts/benchmark_backend.py --payload binary --assert-ms 100`
- ensure workspace backup roundtrip passes:
  - `python scripts/verify_workspace_backup.py --fixture`
- if Docker-related code changed, run:
  - `docker compose build`
  - `docker compose up -d`
  - `curl http://127.0.0.1:8008/readyz`

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
