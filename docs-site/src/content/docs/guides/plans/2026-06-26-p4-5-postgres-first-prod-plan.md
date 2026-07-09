---
title: "P4.5 — Postgres-first production mode (Phase 4 · 2026-06-26)"
---

# P4.5 — Postgres-first production mode (Phase 4 · 2026-06-26)

Closes the gap that lets a `AB_ENV=production` deployment silently fall back to the
ephemeral SQLite default. SQLite is correct for local / demo (HF free tier wipes it on every
redeploy — see `docs/DEPLOY.md`), but a real production deployment must run on a durable
PostgreSQL backend. Unlike P4.1–P4.4 this is a **config + ops** slice: **no schema bump, no new
table, no API field, no i18n**.

## What is missing today
- `config.py` reads `AB_ENV` (default `local`) and `AB_DATABASE_URL` (default
  `sqlite:///…/projects.sqlite3`) but never couples them: `AB_ENV=production` with the SQLite
  default starts up silently on throwaway storage.
- Connection health at runtime already exists (`/readyz` runs a write-probe per backend, returns
  503 when degraded; `/api/v1/diagnostics` exposes `storage.write_probe_ok`). What is missing is a
  **fail-fast at startup** so a misconfigured production process never reaches the serving state.
- No operator guide for the PostgreSQL production path (env matrix, provisioning, retention, backup).

## Design
1. **Enforce PG in production (`config.py`).** Two derived properties on `Settings`:
   - `is_production` — `environment.strip().lower() in {"production", "prod"}` (consistent with the
     existing `environment == "local"` sentinel in `routes/webhooks.py`).
   - `uses_postgres` — `urlparse(database_url).scheme in {"postgres", "postgresql"}` (same predicate
     the `create_backend` factory uses).
   In `_validate_settings`: `is_production and not uses_postgres` → `ValueError` pointing at
   `docs/PRODUCTION.md`. Fail-fast: `get_settings()` raises, the process never starts.
2. **Verify the live PG path at startup (`main.py`).** `_verify_production_storage(repository)` runs
   only when `is_production`: confirms `backend_name == "postgres"` and that a real
   `get_diagnostics_summary()` write-probe succeeds, otherwise `RuntimeError` with the probe detail.
   This turns "config says PG" into "PG is actually reachable and writable" before serving — the
   plan's "health-проверка соединения" + "prod-конфиг стартует на PG".
3. **`docs/PRODUCTION.md`.** Operator guide: env matrix (`AB_ENV`, `AB_DATABASE_URL`,
   `AB_DB_POOL_SIZE`, auth/signing secrets), PostgreSQL provisioning, the fail-fast contract,
   health/readiness checks, retention & backup notes, links to `docs/DEPLOY.md` for the container /
   registry mechanics (not duplicated here).

## Scope / non-goals
- No change to the data model, statistics, decision path, or frontend.
- Local / demo behaviour is unchanged (default `AB_ENV=local` → SQLite stays valid).
- Connection-health endpoints (`/readyz`, `/api/v1/diagnostics`) already exist and are reused, not
  rebuilt.

## Steps
- [ ] `config.py`: `is_production` + `uses_postgres` properties; production-requires-PG check in
  `_validate_settings` (after the empty-URL check).
- [ ] `main.py`: `_verify_production_storage(repository)` + call it in `create_app` when production.
- [ ] `docs/PRODUCTION.md` (operator guide).
- [ ] Tests: `test_config.py` (+ production+sqlite → ValueError · production+postgres → ok ·
  `prod`/case-insensitive alias · local+sqlite → ok · `is_production` / `uses_postgres` properties);
  `test_main.py` for `_verify_production_storage` (postgres+probe-ok passes · probe-fail raises ·
  non-postgres backend raises) with duck-typed fakes (no live PG needed).

## Verify / gate
Serial Windows gate: ruff, mypy --strict, backend pytest (config + main suites green, no regressions),
contract `--check` (untouched — no schema change), locale (untouched). No `verify-postgres`-only
behaviour is added (no dual-SQL), but the existing CI matrix still runs on the PR. Then push → PR → CI
→ merge under the standing "реши сам" mandate; deploy gated on "задеплой".
