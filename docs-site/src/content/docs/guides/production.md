---
title: "Production deployment (PostgreSQL-first)"
---

# Production deployment (PostgreSQL-first)

This guide covers running the backend as a durable production service on PostgreSQL. For the
container build, registry, and hosted-demo mechanics (Docker / GHCR / Hugging Face / Fly), see
[`docs/DEPLOY.md`](/ab-test-research-designer/guides/deploy/) — those steps are not repeated here.

## Local / demo vs production

The default backend is SQLite, which is correct for local development and the hosted demo. It is
**not** durable for production: on the Hugging Face free tier (and any ephemeral container
filesystem) the SQLite file is wiped on every redeploy or restart. A real production deployment must
run on PostgreSQL so experiment data, exposures, and conversions survive restarts.

## Fail-fast contract

When `AB_ENV` declares a production environment (`production` or `prod`), the service **requires** a
PostgreSQL `AB_DATABASE_URL` *and* auth material that can gate writes. It refuses to start otherwise:

- **Config validation** (`app/backend/app/config.py`): `AB_ENV=production` with a non-PostgreSQL
  `AB_DATABASE_URL` raises at `get_settings()` — the process never starts. The same validation raises
  the shared-token minimum length from 8 to **24 characters** in production (`AB_API_TOKEN`,
  `AB_READONLY_API_TOKEN`, `AB_ADMIN_TOKEN`).
- **Startup storage probe** (`app/backend/app/main.py`): in production the app confirms the backend
  resolved to PostgreSQL and that a live write-probe succeeds before serving; a missing or unwritable
  database raises `RuntimeError` with the probe detail instead of silently degrading.
- **Startup auth gate** (`app/backend/app/main.py`): in production the app refuses to serve with no
  auth material, because every mutating endpoint would then accept anonymous callers.

Local / demo behaviour is unchanged: with the default `AB_ENV=local`, SQLite stays valid and the
8-character token minimum applies.

### Valid production auth bootstraps

Any **one** of these satisfies the startup auth gate — each ends with anonymous writes rejected:

| Bootstrap | What it gives you |
| --- | --- |
| `AB_API_TOKEN` | The write-scoped shared token. Simplest single-secret deployment. |
| `AB_ADMIN_TOKEN` | No write scope of its own, but it issues the first write-scoped API key through `POST /api/v1/keys`. Until that key exists, mutating endpoints answer `401` — they are closed, not open. |
| An active **write**-scoped API key already in the database | The steady state after the admin token has been retired. |

A read-only token (`AB_READONLY_API_TOKEN`) or `AB_PUBLIC_DEMO` **alone** does not satisfy the gate.
Nothing would be open, but nothing could be written either — that is a broken production config, not a
secure one, so it fails fast rather than serving a read-only service you did not ask for.

### Escape hatch: `AB_ALLOW_INSECURE_PRODUCTION`

`AB_ALLOW_INSECURE_PRODUCTION=true` (default `false`) starts production **without** auth material. Every
mutating endpoint is then open to anonymous callers, and the app logs a `WARNING`
(`event=insecure_production`) on every boot. It exists for throwaway internal instances that are
unreachable from any network you do not control. Do not set it on a reachable deployment.

```
WARNING app.backend.app.main: INSECURE PRODUCTION: no auth material is configured, so every mutating
endpoint is open to anonymous callers. AB_ALLOW_INSECURE_PRODUCTION=true suppressed the startup check
that would normally refuse to boot.
```

## Environment matrix

| Variable | Production value | Notes |
| --- | --- | --- |
| `AB_ENV` | `production` | Enables the PostgreSQL fail-fast contract above. |
| `AB_DATABASE_URL` | `postgresql://USER:PASSWORD@HOST:5432/DBNAME` | `postgres://` is also accepted. Required in production. |
| `AB_DB_POOL_SIZE` | e.g. `10` | PostgreSQL connection-pool size; tune to expected concurrency. |
| `AB_HOST` / `AB_PORT` | `0.0.0.0` / `8008` | Bind address and port the container exposes. |
| `AB_API_TOKEN` | long random secret (≥ 24 chars in production) | Write-scoped token. Required unless you bootstrap through `AB_ADMIN_TOKEN` or an existing write API key — see the auth gate above. |
| `AB_READONLY_API_TOKEN` | long random secret (≥ 24 chars in production) | Optional read-only token for diagnostics. Does not satisfy the auth gate on its own. |
| `AB_ADMIN_TOKEN` | long random secret (≥ 24 chars in production) | Admin-only surfaces (`/api/v1/keys`, `/api/v1/webhooks`); issues the first write-scoped API key. Satisfies the auth gate. |
| `AB_ALLOW_INSECURE_PRODUCTION` | `false` | Escape hatch. `true` starts production with no auth material — mutating endpoints open to anyone — and logs a `WARNING` every boot. |
| `AB_WORKSPACE_SIGNING_KEY` | long random secret (≥ 16 chars) | Signs workspace backups so they cannot be tampered with. |
| `AB_CORS_ORIGINS` | your frontend origin(s) | Comma-separated; defaults to localhost dev origins. |
| `AB_MISTRAL_API_KEY` | Mistral API key | Optional **free fallback** for AI advice/hypotheses: when the default local orchestrator is unavailable (e.g. the hosted demo has none), requests fall back to Mistral so suggestions still work without a paid provider. Unset → no fallback (advice degrades gracefully to an empty, `available: false` result). |
| `AB_MISTRAL_MODEL` | `mistral-small-latest` | Model used for the Mistral fallback. |

The SQLite-specific knobs (`AB_SQLITE_*`) are ignored on the PostgreSQL backend.

## Provision PostgreSQL

Create a dedicated database and user, then point `AB_DATABASE_URL` at it:

```sql
CREATE USER abtest WITH PASSWORD 'replace-with-a-strong-secret';
CREATE DATABASE abtest OWNER abtest;
```

```bash
export AB_ENV=production
export AB_DATABASE_URL="postgresql://abtest:replace-with-a-strong-secret@db-host:5432/abtest"
export AB_DB_POOL_SIZE=10
```

### Schema and migrations

On startup the app creates any missing objects and then applies every migration the database has
not seen yet, under a PostgreSQL advisory lock (so two replicas booting at once serialise instead
of racing the same `ALTER`). The version that was actually applied is recorded in the
`schema_migrations` table — it is read back, not assumed, which is what lets `/readyz` tell a
current database apart from one that is behind (`503`, `pending migration`).

Migrations are defined in `app/backend/app/repository/_migrations.py`. Each is idempotent, so a
restart never re-applies one, and a fresh install and a legacy upgrade converge on the same schema.
CI runs both paths: `verify-postgres` provisions a fresh database, and the upgrade drill in
`test_postgres_backend.py` rewinds a real database to its pre-`occurred_at` shape, seeds rows,
reopens it with the current build, and asserts the rows survived.

**Back up before upgrading.** Migrations run automatically at startup, so the deploy *is* the
migration. Rolling back the image does not roll back an applied `ALTER`:

```bash
pg_dump "$AB_DATABASE_URL" > backup-$(date +%F).sql   # before the deploy
psql "$AB_DATABASE_URL" < backup-2026-07-12.sql       # to roll back, restore it
```

## Health and readiness

| Endpoint | Purpose | Healthy response |
| --- | --- | --- |
| `GET /health` | Liveness | `200`, `{"status":"ok", ... "environment":"production"}` |
| `GET /readyz` | Readiness (per-backend write-probe) | `200`, `{"status":"ready"}`, all checks `ok` (`503` / `degraded` otherwise) |
| `GET /api/v1/diagnostics` | Storage / auth / runtime detail | `200`, `storage.write_probe_ok=true` |

```bash
curl https://<host>/health
curl https://<host>/readyz
```

Use `/readyz` as the container/orchestrator readiness probe so traffic is only routed once the
PostgreSQL checks pass. It compares the schema version recorded in the database against the version
this build requires (`503` while a migration is pending) and performs a real (rolled-back) write, so
it catches a database that is unreachable, read-only, or behind the code.

## Ingestion: batch semantics, idempotency, limits

Exposure and conversion events are ingested in batches (`POST /api/v1/experiments/{id}/exposures`
and `.../conversions`). Each request returns an accounting object:

```json
{ "received": 10000, "recorded": 10000, "deduplicated": 0 }
```

`received == recorded + deduplicated` always holds.

- **At-least-once safe.** Production ingestion is at-least-once: clients retry on timeout and queues
  redeliver. Replaying an identical batch is safe — it records nothing (`recorded == 0`) and never
  inflates stored totals. This is verified at scale (10k-event replay) in
  `app/backend/tests/test_ingestion_load.py`.
- **Exposures: first-exposure-wins** per `(experiment, user)`. A user's first-seen variation is
  sticky; a duplicate or later exposure is dropped, so a redelivery cannot inflate an arm and
  manufacture a false SRM.
- **Conversions: idempotency keys.** Supply an `idempotency_key` so retries with the same key are
  deduplicated per experiment. Events sent without a key are always recorded (use a key whenever the
  producer may retry).
- **Batch size limit.** `AB_MAX_REQUEST_BODY_BYTES` (default 1 MiB) bounds a single request body, so
  very large backfills must be chunked into multiple batches. Each batch is one transaction
  (all-or-nothing per request); throughput scales with the PostgreSQL backend and connection pool
  (`AB_DB_POOL_SIZE`).

## Retention and backup

- **Backups.** Use managed PostgreSQL automated backups, or schedule `pg_dump`:

  ```bash
  pg_dump "$AB_DATABASE_URL" --format=custom --file "abtest-$(date +%F).dump"
  ```

  Restore with `pg_restore --clean --dbname "$AB_DATABASE_URL" abtest-YYYY-MM-DD.dump`.
- **Retention.** Exposures and conversions accumulate per experiment. There is no automatic purge;
  archive or delete experiments you no longer analyse, and size storage for your event volume (see
  P4.6 for ingestion throughput / capacity notes).
- **Workspace exports.** `AB_WORKSPACE_SIGNING_KEY` lets you export and re-import a signed workspace
  snapshot as a portable, integrity-checked backup of the project/experiment definitions (not the
  raw event stream — that lives in PostgreSQL).

## Pre-flight checklist

1. PostgreSQL provisioned, reachable from the app host, credentials in a secret store.
2. `AB_ENV=production` and a `postgresql://` `AB_DATABASE_URL` set.
3. Auth material set — `AB_API_TOKEN`, or `AB_ADMIN_TOKEN`, or an existing write-scoped API key
   (≥ 24 chars for shared tokens; the app refuses to start without one of the three). Plus
   `AB_WORKSPACE_SIGNING_KEY`, and optionally `AB_READONLY_API_TOKEN`.
4. `AB_CORS_ORIGINS` restricted to your real frontend origin(s).
5. Deploy, then verify `GET /readyz` returns `200` / `ready` before routing traffic.
