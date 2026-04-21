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

Docker with API auth:

```bash
set AB_API_TOKEN=your-secret-token
docker compose up --build
```

Docker with split write/read tokens:

```bash
set AB_API_TOKEN=write-secret-token
set AB_READONLY_API_TOKEN=readonly-secret-token
docker compose up --build
```

Docker with signed workspace backups:

```bash
set AB_WORKSPACE_SIGNING_KEY=replace-with-a-long-random-secret
docker compose up --build
```

Security-hardening knobs:

```bash
set AB_RATE_LIMIT_ENABLED=true
set AB_RATE_LIMIT_REQUESTS=240
set AB_AUTH_FAILURE_LIMIT=20
set AB_MAX_REQUEST_BODY_BYTES=1048576
set AB_MAX_WORKSPACE_BODY_BYTES=8388608
docker compose up --build
```

## Quick checks

- health: `http://127.0.0.1:8008/health`
- readiness: `http://127.0.0.1:8008/readyz`
- diagnostics: `http://127.0.0.1:8008/api/v1/diagnostics`

If `AB_API_TOKEN` or `AB_READONLY_API_TOKEN` is enabled, send either:

- `Authorization: Bearer <token>`
- `X-API-Key: <token>`

Read-only tokens are valid only for `GET`, `HEAD`, and `OPTIONS`. Mutating routes still require the write token.
When the frontend is served, enter the token through the "API session token" field; it is stored only in the current browser session.
When throttling is enabled, bursty `/api/v1/*` traffic and repeated bad tokens return `429` with `Retry-After`.

## Full verification

Primary Windows entrypoint:

```bash
cmd /c scripts\verify_all.cmd
```

With secure Docker compose verification:

```bash
cmd /c scripts\verify_all.cmd --with-docker
```

Non-destructive Docker verification:

```bash
python scripts/verify_docker_compose.py --preserve
```

Or through the main verify wrapper:

```bash
cmd /c scripts\verify_all.cmd --with-docker-preserve
```

Focused checks:

```bash
python -m pytest app/backend/tests -q
npm --prefix app/frontend run test:unit
npm --prefix app/frontend run build
npm --prefix app/frontend run test:e2e
python scripts/run_local_smoke.py --skip-build
python scripts/benchmark_backend.py --payload binary --assert-ms 100
python scripts/verify_workspace_backup.py --fixture
```

Signed workspace backup check:

```bash
set AB_WORKSPACE_SIGNING_KEY=replace-with-a-long-random-secret
python scripts/verify_workspace_backup.py --fixture
```

`npm --prefix app/frontend run test:e2e` builds the frontend if needed and runs against a temporary backend-served build on a free local port.

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
- integrity counts and a SHA-256 checksum
- optional `signature_hmac_sha256` when `AB_WORKSPACE_SIGNING_KEY` is configured

Round-trip verification against a live DB file:

```bash
python scripts/verify_workspace_backup.py --db-path D:\AB_TEST\app\backend\data\projects.sqlite3
```

If the target runtime uses `AB_WORKSPACE_SIGNING_KEY`, rerun the same verification command with that env var set so signature verification is exercised, not only checksum validation.

## Saved-project recovery

Useful endpoints:

- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}/history`
- `GET /api/v1/projects/{project_id}/revisions`

Use revisions to restore an older payload into the wizard, then save to persist it as the latest version.

## Common failure modes

Readiness returns `503`:

- check SQLite path and write access
- check schema version and journal mode in `GET /readyz`
- if `AB_SERVE_FRONTEND_DIST=true`, ensure `app/frontend/dist/index.html` exists
- inspect `GET /api/v1/diagnostics` for frontend/LLM/storage details

Frontend loads but backend requests fail:

- confirm `VITE_API_BASE_URL`
- if write-token auth is enabled, confirm that the browser-session token is present and accepted by diagnostics
- if read-only auth is enabled, verify diagnostics/docs work while mutations still reject with `403`
- if requests start returning `429`, inspect `Retry-After` and tune `AB_RATE_LIMIT_*` or `AB_AUTH_FAILURE_*` for the target runtime
- verify CORS env values if frontend is on another origin
- use `request_id` and `X-Error-Code` from API failures to correlate UI errors with backend logs
- use diagnostics runtime counters and guard settings to confirm whether failures are isolated, rate-limited, or caused by request-size policy on the current process lifetime

Workspace import fails:

- validate JSON shape against `docs/API.md`
- if the payload is legitimately large, confirm `AB_MAX_WORKSPACE_BODY_BYTES` is high enough for the target runtime
- ensure referenced analysis runs and projects are consistent
- ensure the integrity checksum still matches and that the bundle was not edited after export
- if the runtime has `AB_WORKSPACE_SIGNING_KEY`, ensure the bundle still contains a valid `signature_hmac_sha256`

## Rotating API keys

Prerequisites:

- `AB_ADMIN_TOKEN` is configured on the backend runtime
- you can reach `GET /api/v1/keys` with `Authorization: Bearer <AB_ADMIN_TOKEN>`

Recommended rotation flow:

1. Create a replacement key with the same scope and any required per-key rate-limit override.
2. Update the external consumer to use the new plaintext key.
3. Verify traffic moved by checking `GET /api/v1/audit?key_id=<new-key-id>&action=api_key_used`.
4. Revoke the previous key with `POST /api/v1/keys/{key_id}/revoke`.
5. Delete the revoked key with `DELETE /api/v1/keys/{key_id}` once rollback is no longer needed.

Create:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/keys \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Partner write key","scope":"write"}'
```

Audit verification:

```bash
curl "http://127.0.0.1:8008/api/v1/audit?key_id=KEY_ID&action=api_key_used" \
  -H "Authorization: Bearer YOUR_WRITE_TOKEN"
```

Revoke:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/keys/KEY_ID/revoke \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

Delete:

```bash
curl -X DELETE http://127.0.0.1:8008/api/v1/keys/KEY_ID \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

Notes:

- the plaintext key is returned only once in the create response; do not log or persist it outside the intended secret store
- legacy `AB_API_TOKEN` and `AB_READONLY_API_TOKEN` continue to work during migration and can be retired separately from managed API keys

## Release hygiene

- regenerate API contracts: `python scripts/generate_frontend_api_types.py`
- regenerate API docs: `python scripts/generate_api_docs.py`
- run workspace roundtrip verification: `python scripts/verify_workspace_backup.py --fixture`
- run full verify pipeline
- refresh smoke screenshots if UI changed materially
