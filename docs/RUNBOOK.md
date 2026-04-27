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

Docker with Slack App credentials:

```bash
set AB_SLACK_CLIENT_ID=your-client-id
set AB_SLACK_CLIENT_SECRET=your-client-secret
set AB_SLACK_SIGNING_SECRET=your-signing-secret
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

## Postgres deployment

Use Postgres when the backend must support concurrent writers, multiple app instances, or database-native replication. Leave `AB_DATABASE_URL` empty to keep the default SQLite workflow.

Minimal env:

```bash
set AB_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/abtest
set AB_DB_POOL_SIZE=10
python -m uvicorn app.backend.app.main:app --host 127.0.0.1 --port 8008
```

Notes:

- schema bootstrapping is automatic on startup via idempotent `CREATE TABLE IF NOT EXISTS`
- SQLite-specific snapshot sync stays disabled on Postgres runtimes
- `AB_DB_POOL_SIZE` controls the psycopg connection pool; increase it for multi-worker deploys
- `AB_DB_PATH`, `AB_SQLITE_BUSY_TIMEOUT_MS`, `AB_SQLITE_JOURNAL_MODE`, and `AB_SQLITE_SYNCHRONOUS` still apply only to SQLite

Migration guide from SQLite:

```bash
sqlite3 D:\AB_TEST\app\backend\data\projects.sqlite3 .dump > workspace.sql
psql postgresql://postgres:postgres@localhost:5432/abtest -f workspace.sql
```

## Demo seeding on Hugging Face

When `AB_SEED_DEMO_ON_STARTUP=true`, the backend runs a one-time startup hook after SQLite initialization and seeds the workspace with three demo projects: checkout conversion, pricing sensitivity, and onboarding completion. Each seeded project gets a saved analysis snapshot, and the checkout project also gets a markdown export event so the hosted UI shows populated sidebar and history views on first load.

For Hugging Face Spaces Docker deployments, keep the image default as `AB_SEED_DEMO_ON_STARTUP=false` and set `AB_SEED_DEMO_ON_STARTUP=true` in the Space Settings UI. Hugging Face Spaces currently injects runtime variables from Settings, not README frontmatter.

Disable seeding by setting:

```bash
set AB_SEED_DEMO_ON_STARTUP=false
```

Re-seed by starting from a fresh SQLite file and restarting the container. On Hugging Face Spaces basic storage this already happens on cold restarts because `/app/data/projects.sqlite3` is ephemeral. On a persistent runtime, either delete the SQLite file before restart or delete the demo projects through `DELETE /api/v1/projects/{id}` with a write-capable token and restart the app.

Quick verification after deploy:

```bash
curl https://YOUR-SPACE.hf.space/api/v1/projects
curl https://YOUR-SPACE.hf.space/api/v1/projects/PROJECT_ID/history
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

## Multi-project comparison

Useful endpoints:

- `POST /api/v1/projects/compare`
- `POST /api/v1/export/comparison`
- legacy pairwise: `GET /api/v1/projects/compare?base_id=...&candidate_id=...` with `Deprecation: true`

Open a comparison dashboard for 3 saved projects:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/projects/compare \
  -H "Content-Type: application/json" \
  -d '{"project_ids":["PROJECT_ID_1","PROJECT_ID_2","PROJECT_ID_3"]}'
```

Export the same selection to Markdown:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/export/comparison \
  -H "Content-Type: application/json" \
  -d '{"project_ids":["PROJECT_ID_1","PROJECT_ID_2","PROJECT_ID_3"],"format":"markdown"}'
```

Export the same selection to PDF:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/export/comparison \
  -H "Content-Type: application/json" \
  -d '{"project_ids":["PROJECT_ID_1","PROJECT_ID_2","PROJECT_ID_3"],"format":"pdf"}'
```

Checks:

- `project_ids` must contain 2 to 5 unique saved projects
- every selected project must already have a saved analysis snapshot
- mixed `binary` and `continuous` selections are allowed, but the dashboard marks direct effect comparison as not meaningful
- PDF export returns base64-encoded content in the JSON payload; decode client-side before saving to disk

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

## Webhook troubleshooting

Useful endpoints:

- `GET /api/v1/webhooks`
- `GET /api/v1/webhooks/{webhook_id}/deliveries?limit=50`
- `POST /api/v1/webhooks/{webhook_id}/test`

Common checks:

- confirm the subscription uses `https://...`; plain HTTP is rejected outside `AB_ENV=local` localhost targets
- verify the subscription is still `enabled`
- inspect the delivery history for `response_code`, `attempt_count`, and `error_message`
- if a delivery is stuck in `retrying`, wait for the next in-process backoff window before retrying manually
- generic consumers must verify `X-AB-Signature` with the stored shared secret; Slack subscriptions do not include that header
- repeated terminal failures move the delivery into the DB-backed dead-letter history with `status=failed`

Create a test subscription or re-run a probe:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/webhooks/WEBHOOK_ID/test \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

Inspect recent failed deliveries:

```bash
curl "http://127.0.0.1:8008/api/v1/webhooks/WEBHOOK_ID/deliveries?limit=50&status=failed" \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

## Slack App deployment

Use `slack/app-manifest.yml` for Slack UI import or `slack manifest validate`. Replace `{DEPLOY_HOST}` with the HTTPS backend host before importing.

Required runtime secrets:

- `AB_SLACK_CLIENT_ID`
- `AB_SLACK_CLIENT_SECRET`
- `AB_SLACK_SIGNING_SECRET`

Useful endpoints:

- `GET /slack/install`
- `GET /slack/oauth/callback`
- `POST /slack/commands`
- `POST /slack/interactive`
- `POST /slack/events`
- `GET /api/v1/slack/status`

Smoke check:

```bash
curl http://127.0.0.1:8008/api/v1/slack/status
```

After installation, run `/ab-test projects` in Slack and verify the response lists saved projects. Slack requests are rejected when `X-Slack-Signature` is invalid or the timestamp is older than five minutes.

Rotate secrets from the Slack App configuration, update runtime secrets, restart the backend, delete the affected `slack_installations` row when replacing bot tokens, then reinstall through `/slack/install`.

### Slack OAuth tokens at rest

`slack_installations.bot_token` and `slack_installations.user_token` are stored **plaintext** in SQLite (or Postgres if `AB_DATABASE_URL` is set). The threat model is local-first single-user use, where access to the SQLite file already implies host compromise. Specifically:

- `data/projects.sqlite3` and any custom `AB_DB_PATH` should sit on a filesystem that only the application user can read.
- Hugging Face Spaces and similar hosted demos: do **not** install Slack in production-grade workspaces from the demo. Use a sandbox Slack workspace or skip the integration.
- For a self-hosted production deployment, restrict access to the database file at the filesystem layer (e.g. `chmod 600`, encrypted volume, AWS KMS-backed EFS), and rotate Slack tokens promptly if compromise is suspected.
- Token rotation: re-run `/slack/install` to overwrite the row; the previous token becomes inactive in Slack as well.

If you need encrypted-at-rest storage, the recommended path is to enable filesystem-level or volume-level encryption on the host rather than column-level encryption in the application — the latter requires its own KEK management and adds a recovery failure mode without changing the practical attacker model for a host with running write access.

## Adding a new locale

The project ships with seven locales: `en`, `ru`, `de`, `es`, `fr`, `zh`, `ar`. Adding a new one takes a matching pair of JSON files plus registration, switcher, and verification touches.

1. **Frontend translation** - copy `app/frontend/src/i18n/en.json` to `<code>.json` in the same directory and translate the strings. Current shipped locales (`de`, `es`, `fr`, `zh`, `ar`) all keep full leaf-key parity with `en`; do not ship a partial file unless review explicitly allows fallback coverage.
2. **Frontend registration** - add the new code to `app/frontend/src/i18n/index.ts`: import the JSON, add it to `resources`, extend `supportedLngs`, and keep the `fallbackLng` resolver returning `<primary> -> en` for regional tags.
3. **Language switcher** - extend `SUPPORTED_LANGUAGES` in `app/frontend/src/App.tsx` so the header switcher renders the new button. Add a label under `app.language.options.<code>` to every shipped locale file, not only the new one, because the switcher is visible in every active locale.
4. **RTL locales** - if the locale is right-to-left, update `App.tsx` so it sets `document.documentElement.dir = "rtl"` for that code and `"ltr"` otherwise. Audit `app/frontend/src/**/*.css` for logical properties (`inset-inline-*`, `padding-inline-*`, `margin-inline-*`, `border-inline-start-*`, `text-align: start/end`) before shipping.
5. **Backend translation** - copy `app/backend/app/i18n/en.json` to `app/backend/app/i18n/<code>.json`. Translate at least the `export.markdown`, `export.html`, `warnings`, and `report` subtrees, since those feed the `/api/v1/export/*` payloads and the deterministic report builder.
6. **Backend registration** - extend the `Language` literal and `SUPPORTED_LANGUAGES` tuple in `app/backend/app/i18n/__init__.py`. The `resolve_language` helper already accepts any supported primary tag, so regional variants like `fr-CA`, `zh-TW`, or `ar-SA` fall back automatically.
7. **Tests** - extend `app/frontend/src/i18n.test.tsx`, keep `app/frontend/src/test/a11y-locales.test.tsx` aligned with the current switcher shape, add `app/frontend/src/test/a11y-rtl.test.tsx` for RTL locales, and add backend export assertions to `app/backend/tests/test_export_api.py` covering the translated markdown header and primary-tag fallback.

Verification:

```bash
cmd /c scripts\verify_all.cmd --with-e2e
```

The backend bundle is small (one JSON per locale); the frontend bundle impact depends on whether locales are statically imported or lazy-loaded, so re-check the build output after adding a fully translated locale set.

## Release hygiene

- regenerate API contracts: `python scripts/generate_frontend_api_types.py`
- regenerate API docs: `python scripts/generate_api_docs.py`
- run workspace roundtrip verification: `python scripts/verify_workspace_backup.py --fixture`
- run full verify pipeline
- refresh smoke screenshots if UI changed materially

## Local cleanup

`python scripts/cleanup_test_artifacts.py` (use `--dry-run` first) removes
local pytest temp dirs, `.coverage`, the cxkm sandbox, and the mkdocs `site/`
build. Everything it touches is recreated on the next test/build run; no
tracked content is affected.

## Screenshots

Single source of truth is `docs/demo/`, populated by
`scripts/run_local_smoke.py`. The mkdocs site keeps its own copies in
`docs-site/assets/screenshots/` because mkdocs only serves files under
`docs_dir`. After regenerating screenshots, run
`python scripts/sync_doc_screenshots.py` to mirror them; CI does this
automatically before `mkdocs gh-deploy`. Files unique to docs-site
(currently `comparison-distribution-view.png`) are left untouched.
