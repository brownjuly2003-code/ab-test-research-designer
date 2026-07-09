---
title: "План: Phase C — event ingestion + dedup (execution-MVP)"
---

# План: Phase C — event ingestion + dedup (execution-MVP)

**Дата:** 2026-06-13
**Источник:** `docs/plans/2026-06-12-execution-layer-plan.md` §"Phase C". Главный риск — exposure-dedup (источник ложного SRM).
**Рамка:** backend-only срез (живой дашборд/SRM-читы = Phase D). Без i18n/frontend.

## Архитектурный контекст (разведано)
- `repository.py` — dual-backend: `PostgresBackend(SQLiteBackend)` наследует data-методы; SQL пишется один раз с `?`-плейсхолдерами, `_translate_sql` конвертирует `?`→`%s` для Postgres.
- Таблицы создаются в `SQLiteBackend._init_db` (через `_create_*_tables`-хелперы) И отдельно в `PostgresBackend._init_db` (с PG-типами).
- `INSERT ... ON CONFLICT(...) DO NOTHING` поддержан обоими (SQLite ≥3.24, Postgres) — dedup-примитив.
- `cursor.rowcount` == 1 (вставлено) / 0 (конфликт) на обоих → признак recorded.
- CI-лейн `verify-postgres` гоняет весь suite против Postgres (локально на Windows нельзя — нет Docker; PG-путь валидируется ТОЛЬКО в CI → SQL писать аккуратно).
- id = `str(uuid.uuid4())`, ts = `datetime.now(timezone.utc).isoformat()`.

## Таблицы (оба бэкенда, FK→projects ON DELETE CASCADE)
**`exposures`** — `id PK`, `experiment_id`, `user_id`, `variation_index INT`, `created_at`,
`UNIQUE(experiment_id, user_id)` → first-exposure-wins. Индекс `(experiment_id, variation_index)`.
**`conversions`** — `id PK`, `experiment_id`, `user_id`, `metric`, `value REAL DEFAULT 1`,
`idempotency_key` (nullable), `created_at`, `UNIQUE(experiment_id, idempotency_key)` → dedup при наличии ключа
(NULL'ы различны в UNIQUE на обоих бэкендах → без ключа дублей не давим). Индекс `(experiment_id, metric)`.

schema_version 7→8 (документирование; `CREATE TABLE IF NOT EXISTS` идемпотентен для существующих БД).

## Repository-методы (в `SQLiteBackend`, Postgres наследует)
- `record_exposures(experiment_id, items: [{user_id, variation_index}]) -> {received, recorded, deduplicated}` —
  цикл `INSERT ... ON CONFLICT(experiment_id,user_id) DO NOTHING` в одной транзакции; recorded += rowcount==1.
- `record_conversions(experiment_id, items: [{user_id, metric, value?, idempotency_key?}]) -> {received, recorded, deduplicated}` —
  цикл `INSERT ... ON CONFLICT(experiment_id,idempotency_key) DO NOTHING`.
- `get_ingestion_summary(experiment_id) -> {exposures_total, exposure_counts:[{variation_index,count}], conversions_total, conversion_counts:[{metric,count,value_sum}]}` —
  GROUP BY; основа для Phase D SRM/stats.
- Все три проверяют существование проекта (404 через ApiError, как `_ensure_project_active`-паттерн, но без archived-блока — экспозиции можно лить и в архивный? нет: лить только в активный → переиспользовать `_ensure_project_active`).

## Schemas (`schemas/api.py`)
`ExposureEvent`, `ExposureIngestRequest{exposures: list, max N}`, `ConversionEvent`, `ConversionIngestRequest`,
`IngestResultResponse{received, recorded, deduplicated}`, `IngestionSummaryResponse{...}`. `extra="forbid"`.

## Routes (`routes/execution.py`, новый; wired в main.py)
- `POST /api/v1/experiments/{experiment_id}/exposures` (require_write_auth) → IngestResultResponse.
- `POST /api/v1/experiments/{experiment_id}/conversions` (require_write_auth) → IngestResultResponse.
- `GET  /api/v1/experiments/{experiment_id}/ingestion` (require_auth) → IngestionSummaryResponse.
- 404 на неизвестный/архивный experiment_id.

## Тесты
- `tests/test_execution_ingestion_repository.py` — record/dedup/idempotency/summary напрямую через `ProjectRepository` (SQLite локально, Postgres в CI).
- route-тесты в `test_api_routes.py` — happy-path + dedup-через-API + 404 + summary.

## Контракт/доки
Регенерировать `api-contract.ts` + `docs/API.md` (как в Phase B).

## Гейт
`verify_all.py --skip-smoke` зелёный (читать ВЫВОД, не exit-код) + CI verify-postgres + ubuntu e2e → PR → merge.

## Явные НЕ-цели (в Phase C)
identity resolution, late/out-of-order, timezone-нормализация, bot-фильтрация, exactly-once на высоком throughput,
живой SRM/sequential/Bayesian (это Phase D), frontend.
