---
title: "План: расширения execution-MVP (после Phases A→D)"
---

# План: расширения execution-MVP (после Phases A→D)

**Дата:** 2026-06-14
**Запрос пользователя:** «доделать всё максимально» — снят гейт «только по явной просьбе» с будущих расширений, зафиксированных в `fable_handoff_features.md` после завершения Phase D.
**База:** main=`257b9b39` (execution-MVP A→D полностью влит).

## Рамка
Довести execution-слой до максимума ценности **без захода в осознанные не-цели §5.3** (identity resolution, bot-фильтрация, late/out-of-order события, columnar-warehouse streaming at scale, exactly-once на высоком throughput, streaming config refresh). Каждое расширение — отдельная ветка/PR, зелёный `verify_all.py --skip-smoke` + все CI (вкл. verify-postgres + ubuntu e2e), как в Phase A–D.

## Статус (2026-06-14)
**E1–E5 ВЛИТЫ в main — расширения завершены полностью.** Вместе с execution-MVP (Phases A→D)
это замыкает весь execution-слой; backlog исчерпан.
- ✅ **E1** — PR #11 merge `873f5723` (коммит `42fcc869`).
- ✅ **E2** — PR #12 merge `0fe053fe` (коммит `edbbdbf4`).
- ✅ **E3** — PR #13 merge `1431d2b0` (коммит `7398a970`).
- ✅ **E4** — PR #14 merge `6d230fda` (коммит `71343ffe`).
- ✅ **E5** — PR #16 merge `e44a3c9b` (коммиты `2057e986` + `83e16859`). Новая статистическая
  математика прошла §7-ревью (subagent `code-reviewer` вместо недоступного Codex): вердикт
  «математика корректна, блокеров нет». Все CI зелёные, включая verify-postgres.

## Очередь (по ценности/риску)

### ✅ E1 — Continuous Bayesian P(B>A) — LOW — PR #11 (ВЛИТА)
В `live_stats_service._continuous_comparison` сейчас `probability_treatment_beats_control=None` («binary-only»). Подключить существующий `monte_carlo_service._simulate_continuous_uplift_distribution` (Beta/Normal-draws, возвращает `probability_uplift_positive` = P(treatment>control)) по per-arm mean/std/n. Завершает симметрию live-stats. Тесты: continuous comparison теперь даёт prob∈[0,1]. Фронт: убрать «binary-only» note, показывать P(B>A) и для continuous.

### ✅ E2 — Sticky-bucket persistence — MEDIUM — PR #12 (ВЛИТА)
Exposures уже хранят первую вариацию per user (first-exposure-wins). `POST /experiments/{id}/assign`: если у user_id уже есть exposure — вернуть СОХРАНЁННУЮ вариацию (sticky), иначе bucketer. Защищает от смены вариации при изменении весов/coverage в работающем эксперименте. Новый repo-метод `get_user_exposure(experiment_id, user_id)`. Опциональный флаг ответа `sticky: bool`. Тесты: повторный assign после ingestion возвращает ту же вариацию даже при смене весов.

### ✅ E3 — Mutual-exclusion namespaces — MEDIUM — PR #13 (ВЛИТА)
Bucketer-инкремент (план Phase A упоминал): второй хэш на общем layer-seed + зарезервированный диапазон. `assign`: если `constraints.mutually_exclusive_experiments`/layer задан — сначала layer-хэш определяет, попадает ли юзер в «слот» этого эксперимента, иначе not-in-experiment. Чистая функция в `bucketer.py` (`assign_to_namespace`), тесты против равномерности и непересечения слотов.

### ✅ E4 — Targeting / attributes evaluation — MEDIUM-HIGH — PR #14 (ВЛИТА)
Phase B принимает `attributes`, но НЕ оценивает. Добавить targeting-правила в дизайн (минимум: список `{attribute, operator, value}` AND-условия) → eval в assignment: не прошёл таргетинг → not-in-experiment (variationId 0, inExperiment false). Schema-расширение (`setup.targeting_rules` опц.), `execution/targeting.py` (eval), тесты на in/out + GrowthBook-семантику. Держать простым (equals/in/gt/lt), без сложного rule-engine.

### ✅ E5 — CUPED на live-данных — HIGH (риск: новая математика) — PR #16 (ВЛИТА)
**Главный риск из плана — реализовано.** (1) ingestion pre-period covariate: таблица
`pre_period_values(experiment_id,user_id,value)` на обоих бэкендах (schema_version 8→9,
first-write-wins) + `POST /api/v1/experiments/{id}/pre-period`. (2) CUPED-adjusted estimator:
`repository.get_cuped_aggregates` отдаёт per-variation достаточные статистики
(`n,sum_x,sum_x2,sum_y,sum_y2,sum_xy`) по covered-subset; `live_stats_service._build_cuped_block`
считает pooled `θ = cov(X,Y)/var(X)`, adjusted mean=`Ȳ−θ(X̄−globalX̄)` и
adjusted var=`varY−2θ·cov+θ²·varX` в closed-form → существующий `analyze_results` (continuous,
новой тест-статистики не вводилось). Блок live-stats: `unavailable`→`available` когда есть
ковариата; `not_applicable` для binary. Property-тесты (θ=0 при константном ковариате →
совпадает с unadjusted, var_reduction=0; коррелированный → снижение дисперсии + эффект сохранён)
+ repo CTE/ingestion + PG round-trip + frontend-рендер. §7-ревью пройдено субагентом
`code-reviewer`: математика корректна. Кавеат «оценка по подвыборке с ковариатой» отражён в note.

## Не-цели (подтверждаем §5.3)
identity resolution · bot-фильтрация · late/out-of-order/timezone · streaming at scale · exactly-once high-throughput · streaming config refresh.

## Бюджет/последовательность
Серийно E1→E5, каждое самоценно и заканчивается зелёным CI. Frontend-only части — backend-сьют локально можно пропустить (CI покроет). При исходе бюджета — коммит сделанного + остаток остаётся в этом плане как backlog.
