# Production deployment (PostgreSQL-first)

This guide covers running the backend as a durable production service on PostgreSQL. For the
container build, registry, and hosted-demo mechanics (Docker / GHCR / Hugging Face / Fly), see
[`docs/DEPLOY.md`](DEPLOY.md) — those steps are not repeated here.

## Local / demo vs production

The default backend is SQLite, which is correct for local development and the hosted demo. It is
**not** durable for production: on the Hugging Face free tier (and any ephemeral container
filesystem) the SQLite file is wiped on every redeploy or restart. A real production deployment must
run on PostgreSQL so experiment data, exposures, and conversions survive restarts.

## Fail-fast contract

When `AB_ENV` declares a production environment (`production` or `prod`), the service **requires** a
PostgreSQL `AB_DATABASE_URL` and refuses to start otherwise:

- **Config validation** (`app/backend/app/config.py`): `AB_ENV=production` with a non-PostgreSQL
  `AB_DATABASE_URL` raises at `get_settings()` — the process never starts.
- **Startup storage probe** (`app/backend/app/main.py`): in production the app confirms the backend
  resolved to PostgreSQL and that a live write-probe succeeds before serving; a missing or unwritable
  database raises `RuntimeError` with the probe detail instead of silently degrading.

Local / demo behaviour is unchanged: with the default `AB_ENV=local`, SQLite stays valid.

## Environment matrix

| Variable | Production value | Notes |
| --- | --- | --- |
| `AB_ENV` | `production` | Enables the PostgreSQL fail-fast contract above. |
| `AB_DATABASE_URL` | `postgresql://USER:PASSWORD@HOST:5432/DBNAME` | `postgres://` is also accepted. Required in production. |
| `AB_DB_POOL_SIZE` | e.g. `10` | PostgreSQL connection-pool size; tune to expected concurrency. |
| `AB_HOST` / `AB_PORT` | `0.0.0.0` / `8008` | Bind address and port the container exposes. |
| `AB_API_TOKEN` | long random secret | Write-scoped token; without it, mutating endpoints are open. |
| `AB_READONLY_API_TOKEN` | long random secret | Optional read-only token for diagnostics. |
| `AB_ADMIN_TOKEN` | long random secret | Optional admin-only surfaces. |
| `AB_WORKSPACE_SIGNING_KEY` | long random secret (≥ 16 chars) | Signs workspace backups so they cannot be tampered with. |
| `AB_CORS_ORIGINS` | your frontend origin(s) | Comma-separated; defaults to localhost dev origins. |

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

The schema is created and migrated automatically on first startup (`schema_version` is tracked in the
database); no manual migration step is required. The same code path is exercised in CI by the
`verify-postgres` job on every pull request.

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
PostgreSQL write-probe passes. The probe checks the live schema version against the expected
`schema_version` and performs a real (rolled-back) write, so it catches an unreachable or
read-only database.

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
3. Auth secrets set (`AB_API_TOKEN`, optionally readonly/admin) and `AB_WORKSPACE_SIGNING_KEY`.
4. `AB_CORS_ORIGINS` restricted to your real frontend origin(s).
5. Deploy, then verify `GET /readyz` returns `200` / `ready` before routing traffic.
