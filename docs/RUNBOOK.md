# Runbook

## Local startup

Backend:

```bash
python -m pip install -r app/backend/requirements.txt
python -m uvicorn app.backend.app.main:app --host 127.0.0.1 --port 8008
```

Frontend dev:

```bash
cd app/frontend
npm install
npm run dev
```

Docker:

```bash
docker compose up --build
```

## Quick checks

- health: `http://127.0.0.1:8008/health`
- readiness: `http://127.0.0.1:8008/readyz`
- diagnostics: `http://127.0.0.1:8008/api/v1/diagnostics`

## Full verification

Primary Windows entrypoint:

```bash
cmd /c scripts\verify_all.cmd
```

Focused checks:

```bash
python -m pytest app/backend/tests -q
npm --prefix app/frontend run test:unit
npm --prefix app/frontend run build
npm --prefix app/frontend run test:e2e
python scripts/run_local_smoke.py --skip-build
python scripts/benchmark_backend.py --payload binary --assert-ms 100
```

## Workspace backup and restore

Export the full local workspace:

```bash
curl http://127.0.0.1:8008/api/v1/workspace/export > workspace-backup.json
```

Import a backup:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/workspace/import ^
  -H "Content-Type: application/json" ^
  -d @workspace-backup.json
```

The backup contains:

- saved projects
- analysis run history
- export events
- saved project revisions

## Saved-project recovery

Useful endpoints:

- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}/history`
- `GET /api/v1/projects/{project_id}/revisions`

Use revisions to restore an older payload into the wizard, then save to persist it as the latest version.

## Common failure modes

Readiness returns `503`:

- check SQLite path and write access
- if `AB_SERVE_FRONTEND_DIST=true`, ensure `app/frontend/dist/index.html` exists
- inspect `GET /api/v1/diagnostics` for frontend/LLM/storage details

Frontend loads but backend requests fail:

- confirm `VITE_API_BASE_URL`
- verify CORS env values if frontend is on another origin

Workspace import fails:

- validate JSON shape against `docs/API.md`
- ensure referenced analysis runs and projects are consistent

## Release hygiene

- regenerate API contracts: `python scripts/generate_frontend_api_types.py`
- regenerate API docs: `python scripts/generate_api_docs.py`
- run full verify pipeline
- refresh smoke screenshots if UI changed materially
