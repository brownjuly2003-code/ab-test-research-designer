# CX Task: Postgres backend option (parallel to SQLite)

## Goal
Добавить опциональный Postgres backend для production deployments где нужен concurrent access / multi-instance / replication. SQLite остаётся default'ом для solo / HF demo / тестов. Controlled через env var `AB_DATABASE_URL` — если `postgresql://...` → Postgres path, иначе (default, `sqlite:///...`) → SQLite.

## Context
- **Repo.** `D:\AB_TEST\`, `main`, HEAD `906ec9ce` (или новее).
- **Current storage.** `app/backend/app/db/` или `app/backend/app/repository.py` (точно найти через `grep -rn "sqlite" app/backend/app/`). SQLite backend через `sqlite3` standard lib или SQLAlchemy.
- **HF snapshot service** (`app/backend/app/services/snapshot_service.py`, `3255df3c`) — SQLite-specific (pickle / file copy). Для Postgres — skip snapshot (Postgres сам replicated/backed up через HF infra, а demo Space не нуждается в Postgres).
- **Tests.** `app/backend/tests/` — сейчас все на SQLite. Добавить parametrize на Postgres через testcontainers.

## Deliverables

1. **Abstraction layer.**
   - Проверить есть ли repository abstraction. Если нет — ввести `DatabaseBackend` Protocol с методами `get_project`, `list_projects`, `save_project`, `get_latest_analysis_run`, `save_analysis_run`, `delete_project`, `list_api_keys`, etc.
   - Два implementation: `SQLiteBackend` (текущий код переупакованный) и `PostgresBackend` (новый).
   - Factory: `def create_backend(database_url: str) -> DatabaseBackend` — возвращает правильный тип по URL scheme.

2. **Postgres implementation.**
   - Use `psycopg[binary]>=3.2` (или SQLAlchemy Core — быстрее если SQLite уже через SQLAlchemy).
   - Schema miтрации — если SQLite без миграций (raw DDL на startup), Postgres — через `alembic` ИЛИ идемпотентный `CREATE TABLE IF NOT EXISTS` runtime.
   - Primary keys: сохранить same UUID strategy что и SQLite для data portability.
   - JSON столбцы: `jsonb` на Postgres где SQLite использует TEXT.
   - Connection pooling: `psycopg_pool` или SQLAlchemy pool, size=10 default, env override `AB_DB_POOL_SIZE`.

3. **Dependency pinning.**
   - Add `psycopg[binary]==3.2.5` к `app/backend/requirements.txt`.
   - Если uses SQLAlchemy — `sqlalchemy[asyncio]==X.Y` аlready в deps, иначе pin новую.
   - Postgres версия target: **16+** (для modern jsonb perf + timestamp).

4. **Tests.**
   - `app/backend/tests/conftest.py` — parametrize fixture `repository` на `sqlite` и `postgres` (через testcontainers-python).
   - `testcontainers==4.5.0` (или latest) в dev requirements.
   - Skip Postgres param на local dev если Docker недоступен (`pytest.skip("Docker unavailable")`) — но CI ubuntu уже имеет Docker.
   - Все existing 275 тестов должны pass'ить под обоими backend'ами.
   - Новые `test_postgres_backend.py`: UUID uniqueness, concurrent writes (2+ workers не конфликтуют), jsonb query performance (select projects with specific metric_type — <50ms на 10k rows).

5. **Docs.**
   - `docs/RUNBOOK.md#postgres-deployment` — connection string format, schema bootstrapping, connection pool tuning.
   - `docs-site/features/database.md` — кратко какой backend когда.
   - `.env.example` — add `AB_DATABASE_URL` с коммент про SQLite default.

6. **CI.**
   - Добавить optional `verify (ubuntu-latest, postgres)` matrix job — prodиspinning Postgres container через `services:` блок GitHub Actions, setting `AB_DATABASE_URL=postgres://postgres:postgres@postgres:5432/abtest`. Prefix tests запускает оба backend'а.
   - Existing job остаётся default (SQLite path).

7. **Backward compat.**
   - `.env` без `AB_DATABASE_URL` → SQLite путь (no user action needed).
   - Existing SQLite databases не трогаем. Migration guide в RUNBOOK (SQLite → Postgres dump via `sqlite3 .dump` + `psql`).
   - HF Space НЕ migrating на Postgres (остаётся SQLite + snapshot service).

8. **Коммит (возможно 2-3):**
   - `refactor(db): extract DatabaseBackend protocol and SQLiteBackend class` (prep)
   - `feat(db): postgres backend option via AB_DATABASE_URL` (main)
   - `ci: run backend tests on postgres matrix job` (CI change)
   - Либо single bundle commit если atomic.

9. **Report `docs/plans/2026-04-23-postgres-backend-report.md`:**
   - Deltas in test count (should stay 275+).
   - Benchmarks: p95 latency на SQLite vs Postgres для common queries.
   - CI runtime impact (extra matrix job).

## Acceptance
- `python -m pytest -p no:schemathesis app/backend/tests/ -v` → зелёный на SQLite (default).
- `AB_DATABASE_URL=postgresql://... python -m pytest ...` → зелёный на Postgres (локально через docker run).
- CI `Tests` зелёный на обоих matrix jobs.
- `scripts\verify_all.cmd --with-e2e` = 0 на default SQLite.
- Benchmarks: Postgres performance не хуже SQLite для single-user case (не обязано быть лучше, но не >2x медленнее).
- Без env var — никакой регрессии для existing users.

## Notes
- **НЕ** requirement'ить Postgres для dev / HF / demo — просто option.
- **НЕ** rewrite existing backend: extract interface, потом add new impl — refactor-first.
- **Transaction boundaries.** SQLite и Postgres имеют разные default isolation levels. Эксплицитно set'ить на SERIALIZABLE где критично (analysis_run snapshots), READ COMMITTED по default (проекты).
- **Migration alembic vs raw DDL.** Если сейчас raw DDL — keep consistency, не вводить alembic только для Postgres. `CREATE TABLE IF NOT EXISTS` работает на обоих.
- **Connection lifecycle.** Не создавать connection per request — pooling mandatory для Postgres. SQLite file-level OK.
- **jsonb vs TEXT.** При чтении данных в Python — `json.loads(row["data"])` для SQLite, psycopg уже парсит jsonb как dict. Унифицировать в backend layer.

## Out of scope
- MySQL / MariaDB backend (отдельно если понадобится).
- Multi-tenant sharding.
- Replication / read-replicas setup.
- Data migration tooling (помимо docs recommendation).
- ORM model classes (если сейчас data classes / dicts — сохранить, не вводить ORM на этом этапе).
