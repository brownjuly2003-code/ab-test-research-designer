---
title: "План: Phase D — live-stats (execution-слой, финальная фаза)"
---

# План: Phase D — live-stats (execution-слой, финальная фаза)

**Дата:** 2026-06-14
**Источник:** `docs/plans/2026-06-12-execution-layer-plan.md` §"Phase D" + `fable_handoff_features.md`.
**Предыдущее:** Phase A/B/C влиты (main=`12f96ee5`). Phase C дал ingestion (exposures/conversions) + dedup + `get_ingestion_summary`. Phase D — последняя.

## Рамка

Замкнуть цикл plan→run→**analyze**: над dedup-агрегатами Phase C считать live-статистику теми же существующими функциями (новой математики нет) + дашборд «running experiment». Local-first, MVP-дисклеймер сохраняется.

Делю на 2 PR (как Phase C был backend-only):
- **PR #9 (Phase D-1, backend)** — live-stats endpoint. ЭТА СЕССИЯ.
- **PR #10 (Phase D-2, frontend)** — «running experiment» дашборд. Следующая сессия.

## Переиспользуемые функции (НЕ пишем новую математику)

| Кит | Функция | Файл |
|-----|---------|------|
| SRM-guardrail | `chi_square_srm(observed_counts, expected_fractions)` | `stats/srm.py` |
| Frequentist | `analyze_results(ResultsRequest)` → `_analyze_binary`/`_analyze_continuous` | `services/results_service.py` |
| Bayesian P(B>A) | `simulate_uplift_distribution(...)` → `probability_uplift_positive` | `services/monte_carlo_service.py` |
| Sequential | `obrien_fleming_boundaries(n_looks, alpha)` + planned N из `calculate_experiment_metrics` | `stats/sequential.py`, `services/calculations_service.py` |

## Данные

`exposures(experiment_id,user_id,variation_index)` (one per user, dedup) + `conversions(experiment_id,user_id,metric,value,idempotency_key)` (multi per user).

**Новый repo-метод** `get_experiment_analysis_aggregates(experiment_id, metric_name) -> dict | None`:
один CTE-JOIN (per-user rollup → per-variation), портируемый SQLite+PG:
```
WITH user_values AS (
  SELECT e.variation_index AS variation_index, e.user_id AS user_id,
         COALESCE(SUM(c.value), 0) AS user_value,
         MAX(CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END) AS converted
  FROM exposures e
  LEFT JOIN conversions c
    ON c.experiment_id = e.experiment_id AND c.user_id = e.user_id AND c.metric = ?
  WHERE e.experiment_id = ? AND e.variation_index >= 0
  GROUP BY e.variation_index, e.user_id
)
SELECT variation_index, COUNT(*) AS exposed_users, SUM(converted) AS converted_users,
       SUM(user_value) AS value_sum, SUM(user_value * user_value) AS value_sq_sum
FROM user_values GROUP BY variation_index ORDER BY variation_index
```
- binary: `converted_users` (distinct users с ≥1 событием), `exposed_users`.
- continuous: `mean = value_sum/exposed_users` (non-converters=0), `var = (value_sq_sum - n*mean²)/(n-1)`, `n = exposed_users`.
- holdout (variation_index = -1) ИСКЛЮЧАЕТСЯ из анализа (`>= 0`).

## Сервис `services/live_stats_service.py`

`build_live_stats(experiment_id, project_payload, aggregates) -> dict`:
1. **design** из payload: `metrics.{metric_type, primary_metric_name, baseline_value, alpha}`, `setup.traffic_split`→expected_fractions (нормализация), `constraints.n_looks`.
2. **srm**: `chi_square_srm([exposed по варианту], expected_fractions)`; нужно ≥2 арма с total>0 иначе `status="insufficient_data"`.
3. **comparisons** (control=variation 0 vs каждый treatment t≥1):
   - binary → `ObservedResultsBinary` → `analyze_results` (freq) + `simulate_uplift_distribution` → `probability_treatment_beats_control`.
   - continuous → `ObservedResultsContinuous` → `analyze_results`.
   - арм с <2 exposed или degenerate → `status="insufficient_data"`.
4. **sequential**: n_looks>1 → `calculate_experiment_metrics` (planned per-variant N + boundaries), info_fraction = total_exposed/(planned·k), z*(f)=z_final/√f, crossed = |z|>z*(f). n_looks==1 → `status="fixed_horizon"`.
5. **cuped**: `status="unavailable"` (нет pre-period covariate-ingestion в MVP — честно, как в плане).

## Endpoint

`GET /api/v1/experiments/{experiment_id}/live-stats` (read auth) в `routes/execution.py`. 404 unknown. Достаёт `get_project` + `get_experiment_analysis_aggregates`, зовёт сервис, валидирует в `LiveStatsResponse`.

## Схемы (`schemas/api.py`)

`LiveStatsResponse`: experiment_id, metric_type, primary_metric_name, exposures_total, conversions_total, disclaimer, `srm: LiveSrmBlock`, `comparisons: list[LiveComparison]`, `sequential: LiveSequentialBlock`, `cuped: LiveCupedBlock`. Вложенные блоки со `status`-полями.

## Тесты

- repo: CTE-агрегаты (dedup-join, holdout исключён, value rollup, missing exp→None).
- service: SRM детект/чисто, freq significance, bayesian∈[0,1], sequential crossed, insufficient_data-гарды, cuped unavailable.
- route: 200 happy, 404 unknown, read-auth.
- регенерация контракта + `docs/API.md`.

## Гейт

`python scripts/verify_all.py --skip-smoke` зелёный → commit → push → PR → ubuntu e2e → merge (admin). dual-backend: PG проверится в `verify-postgres` CI (Docker на Win нет).

## НЕ в scope D-1
Frontend (D-2), continuous Bayesian (freq continuous есть; Bayesian — только binary в MVP), CUPED-вычисление, targeting, >control-vs-treatment попарных (контрол vs каждый — есть; all-pairs — нет).
