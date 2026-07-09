---
title: "F3a — Multi-covariate CUPED (CUPAC-lite) — implementation plan"
---

# F3a — Multi-covariate CUPED (CUPAC-lite) — implementation plan

> Ось A / F3, часть 1 из 2 (F3b = post-stratification — отдельный PR, требует нового ingestion
> атрибутов, т.к. `exposures` их не хранят). План оси A: `2026-06-25-axis-a-statistical-depth-plan.md`.
> F1 (FDR) + F2 (ratio) уже в main. Это естественное продолжение E5 (single-covariate CUPED).

## Goal
Расширить live-CUPED с одного пред-периодного ковариата до **нескольких** (k≤5): θ — вектор из
нормальных уравнений `Σxx·θ = Σxy`, `Y_adj = Y − θᵀ(X − X̄)`. Снижение дисперсии = R² регрессии Y на X.
Обратная совместимость: один ковариат даёт идентичный E5 результат.

## Design decisions (зафиксированы после чтения кода)
- **Линал в stdlib**, без numpy. `stats/cuped.py` (новый) несёт устойчивый солвер малой симметричной
  системы (Гаусс с partial pivoting) + closed-form adjusted moments. Причина: все `stats/*.py` —
  stdlib-only; numpy в проекте лишь транзитивный (через matplotlib), не объявлен в requirements →
  опираться на него для математики хрупко, и он потянул бы `types-numpy` в mypy --strict.
- **БД: новая таблица `pre_period_covariates`** (паттерн E5 — CREATE IF NOT EXISTS в обоих бэкендах),
  НЕ ALTER старой `pre_period_values` (избегаем хрупкого SQLite table-rebuild для смены UNIQUE).
  `UNIQUE(experiment_id, user_id, covariate_name)`, first-write-wins. **schema_version 9→10.**
  Миграция данных (SQLite `_migrate_db`): идемпотентный `INSERT INTO pre_period_covariates SELECT …,
  '__default__', … FROM pre_period_values ON CONFLICT DO NOTHING`. Старая таблица остаётся (источник
  миграции; для свежих БД пуста и не используется). PG: свежие контейнеры получают новый DDL из
  `_init_db` (PG-миграций в проекте нет — известное ограничение, как и везде).
- **covariate_names выводятся из ingested данных** (`DISTINCT covariate_name`, sorted) — не требуют
  менять дизайн-схему метрик. k=0 → `unavailable`; единственный `__default__` → ведёт себя как E5.
- **«Покрытый» юзер = имеет ПОЛНЫЙ вектор** (все k ковариат) — `HAVING COUNT(DISTINCT covariate_name)=k`
  среди exposed (variation_index≥0); holdout исключён. Зеркалит E5 (juзер без X исключается).
- **dual-SQL aggregates**: SQL делает тяжёлый rollup в long/pair-формате (масштаб), Python собирает
  маленькую k×k матрицу. Portable (self-join + group by, `?`→`%s`). Возврат: per variation
  `{n, sum_y, sum_y2, sum_x[k], sum_xx[k][k] (включая диагональ), sum_xy[k]}`.
- **Контракт**: `LiveCupedBlock.theta` (float|None) СОХРАНЯЕТСЯ (k=1 → значение; k>1 → null) +
  новый `covariates: list[{name, theta}]` + `num_covariates`. var_reduction_pct остаётся (общий R²).

## Tasks
- [ ] 1. `stats/cuped.py` (новый, stdlib): `solve_symmetric(matrix, vector)` (Гаусс+pivot) +
      `cuped_theta(sigma_xx, sigma_xy)` + `adjusted_moment(...)` closed-form + `variance_reduction`.
      → Verify: `python -m pytest test_cuped_math.py` (см. task 8) зелёный.
- [ ] 2. БД: новая таблица `pre_period_covariates` в обоих `_init_db` (SQLite + PG); bump
      `schema_version` 9→10; SQLite `_migrate_db` копирует legacy `pre_period_values`→`__default__`.
      → Verify: свежая SQLite БД имеет таблицу (PRAGMA); diagnostics schema_version==10.
- [ ] 3. `repository.record_pre_period_values`: писать в `pre_period_covariates` с `covariate_name`
      (default `__default__`); `get_cuped_aggregates` переписать на multi (DISTINCT covariate_name →
      dual-SQL rollup → per-variation матрицы). → Verify: round-trip тест SQLite (task 8).
- [ ] 4. Схемы: `PrePeriodEvent +covariate_name: str = "__default__"`; `LiveCupedBlock +covariates[]
      +num_covariates`, `theta` остаётся; новый `LiveCupedCovariate{name, theta}`. Регенерить контракт
      (`generate_frontend_api_types.py` + `generate_api_docs.py`). → Verify: `--check` up-to-date.
- [ ] 5. `live_stats_service._build_cuped_block`: multi-covariate через `stats/cuped.py` (центрирование,
      θ-вектор, adjusted moments per arm → существующий continuous t-test). k=1 ⇒ E5-идентично.
      Обновить `_NOTE_AVAILABLE`. → Verify: live-тесты (task 8).
- [ ] 6. Frontend `LiveStatsSection.tsx`: показать список ковариат с θ (когда k>1), сохранить single-вид.
      → Verify: tsc + vitest LiveStatsSection.
- [ ] 7. i18n×7: новые ключи (`results.liveStats.cupedCovariates*`) во все локали, паритет; CUPED не
      переводится, локализуются пояснения. → Verify: `check_locale_content.py` + key-паритет.
- [ ] 8. Тесты: `test_cuped_math.py` (k=1==E5 closed-form; θ-вектор vs ручное решение; 2 коррелир. →
      var_reduction>single; коллинеарность→graceful; солвер vs известная система) + расширить
      `test_execution_live_stats.py` (multi-cov live happy/insufficient/k=1-обратная-совместимость) +
      `test_postgres_backend.py` (+multi-cov round-trip → verify-postgres) + миграционный тест (legacy
      single → читается как `__default__`). → Verify: серийный гейт ниже.

## Done When (Phase: Verification — LAST) — ✅ ВЫПОЛНЕНО 2026-06-25
- [x] Серийный гейт зелёный (Windows, по одному): `python -m mypy` (--strict, 64 файла) · tsc ·
      `vitest run --no-file-parallelism` (261/1skip) · `vite build` (483.6kB<500) ·
      `check_locale_content.py` (14 чисты) · contract `--check` (TS+API.md) · **весь backend 611 passed/11 skip**.
- [x] Обратная совместимость: один ковариат (`__default__`) даёт тот же θ/variance_reduction, что E5
      (unit + live тесты: theta=8.5 / θ=-0.02 / reduction совпали).
- [x] Контракт/локали/mypy чисты; план помечен done; handoff + память обновлены.

> **dual-SQL (Postgres) НЕ проверен локально** (нет Docker на Windows): 11 PG round-trip тестов
> skip, среди них новый `test_postgres_backend_multi_cuped_aggregates_round_trip`. Валидация —
> CI `verify-postgres` + (рекомендация Юли) прогон на `deproject-mac`. push/PR/merge — по слову Юли.

## Risks / гочи
- **dual-SQL multi-cov нельзя проверить на Windows** (нет Docker/PG). Полагаюсь на CI `verify-postgres`;
  Mac-прогон (`deproject-mac`, конфиг как CI) — явный шаг для Юли перед/после merge. [[no-docker-on-windows]]
- Коллинеарные ковариаты → вырожденная Σxx: солвер должен честно вернуть «не решается» → fallback на
  unadjusted (θ=0), не падать. Тест на коллинеарность обязателен.
- Контракт: НЕ ломать `theta` (фронт/доки на него опираются) — оставить, добавлять рядом.
- Миграция данных идемпотентна (ON CONFLICT) — повторный старт не дублирует.
- push/PR/merge/deploy — НЕ /auto: по слову Юли (в этой сессии «реши сам» не звучало).
