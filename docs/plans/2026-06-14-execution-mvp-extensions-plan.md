# План: расширения execution-MVP (после Phases A→D)

**Дата:** 2026-06-14
**Запрос пользователя:** «доделать всё максимально» — снят гейт «только по явной просьбе» с будущих расширений, зафиксированных в `fable_handoff_features.md` после завершения Phase D.
**База:** main=`257b9b39` (execution-MVP A→D полностью влит).

## Рамка
Довести execution-слой до максимума ценности **без захода в осознанные не-цели §5.3** (identity resolution, bot-фильтрация, late/out-of-order события, columnar-warehouse streaming at scale, exactly-once на высоком throughput, streaming config refresh). Каждое расширение — отдельная ветка/PR, зелёный `verify_all.py --skip-smoke` + все CI (вкл. verify-postgres + ubuntu e2e), как в Phase A–D.

## Очередь (по ценности/риску)

### E1 — Continuous Bayesian P(B>A) — LOW — PR #11
В `live_stats_service._continuous_comparison` сейчас `probability_treatment_beats_control=None` («binary-only»). Подключить существующий `monte_carlo_service._simulate_continuous_uplift_distribution` (Beta/Normal-draws, возвращает `probability_uplift_positive` = P(treatment>control)) по per-arm mean/std/n. Завершает симметрию live-stats. Тесты: continuous comparison теперь даёт prob∈[0,1]. Фронт: убрать «binary-only» note, показывать P(B>A) и для continuous.

### E2 — Sticky-bucket persistence — MEDIUM — PR #12
Exposures уже хранят первую вариацию per user (first-exposure-wins). `POST /experiments/{id}/assign`: если у user_id уже есть exposure — вернуть СОХРАНЁННУЮ вариацию (sticky), иначе bucketer. Защищает от смены вариации при изменении весов/coverage в работающем эксперименте. Новый repo-метод `get_user_exposure(experiment_id, user_id)`. Опциональный флаг ответа `sticky: bool`. Тесты: повторный assign после ingestion возвращает ту же вариацию даже при смене весов.

### E3 — Mutual-exclusion namespaces — MEDIUM — PR #13
Bucketer-инкремент (план Phase A упоминал): второй хэш на общем layer-seed + зарезервированный диапазон. `assign`: если `constraints.mutually_exclusive_experiments`/layer задан — сначала layer-хэш определяет, попадает ли юзер в «слот» этого эксперимента, иначе not-in-experiment. Чистая функция в `bucketer.py` (`assign_to_namespace`), тесты против равномерности и непересечения слотов.

### E4 — Targeting / attributes evaluation — MEDIUM-HIGH — PR #14
Phase B принимает `attributes`, но НЕ оценивает. Добавить targeting-правила в дизайн (минимум: список `{attribute, operator, value}` AND-условия) → eval в assignment: не прошёл таргетинг → not-in-experiment (variationId 0, inExperiment false). Schema-расширение (`setup.targeting_rules` опц.), `execution/targeting.py` (eval), тесты на in/out + GrowthBook-семантику. Держать простым (equals/in/gt/lt), без сложного rule-engine.

### E5 — CUPED на live-данных — HIGH (риск: новая математика) — PR #15
**Главный риск из плана.** Нужен per-user pre-period covariate. (1) ingestion pre-period значений (новый эндпоинт/таблица `pre_period_values(experiment_id,user_id,value)`), (2) CUPED-adjusted estimator в анализе: `Y_adj = Y - θ(X - mean(X))`, `θ = cov(X,Y)/var(X)`; считать adjusted mean/var per arm → существующий `analyze_results` (continuous). Это НОВАЯ математика → перед мержем прогнать тесты на свойства (θ=0 при нулевой корреляции даёт исходный результат; снижение дисперсии при корреляции) + рассмотреть Codex second-opinion (§7). CUPED-блок live-stats: `unavailable`→`available` когда pre-period есть.

## Не-цели (подтверждаем §5.3)
identity resolution · bot-фильтрация · late/out-of-order/timezone · streaming at scale · exactly-once high-throughput · streaming config refresh.

## Бюджет/последовательность
Серийно E1→E5, каждое самоценно и заканчивается зелёным CI. Frontend-only части — backend-сьют локально можно пропустить (CI покроет). При исходе бюджета — коммит сделанного + остаток остаётся в этом плане как backlog.
