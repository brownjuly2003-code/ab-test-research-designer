# F3b — Post-stratification — implementation plan

> Ось A / F3, часть 2 из 2 (F3a = multi-covariate CUPED — в PR #25, весь CI вкл. verify-postgres
> зелёный). План оси A: `2026-06-25-axis-a-statistical-depth-plan.md`. F1 (FDR) + F2 (ratio) в main.
> Эта ветка `feat/post-stratification` стоит ПОВЕРХ `feat/multi-covariate-cuped` (stacked), чтобы не
> конфликтовать по `schema_version` (F3a уже 9→10, F3b будет 10→11) и не блокироваться на merge F3a.

## Goal
Снизить дисперсию оценки эффекта на live-пути за счёт **post-stratification**: разбить выборку по
категориальной страте (платформа/страна/новизна и т.п.), оценить эффект **повзводно** и собрать
взвешенно по доле страты. Снижение дисперсии — когда страты объясняют вариацию исхода (between-strata
variation выносится из ошибки). Обратная совместимость: одна страта на всех → совпадает с unadjusted.

## Математика (досверено по источнику, НЕ из памяти — [[dont-claim-unverified]])
Источник: **Miratrix, Sekhon & Yu 2013, JRSS-B** «Adjusting treatment effect estimates by
post-stratification in randomized experiments»; Kohavi et al. *Trustworthy Online Controlled Experiments*.
Принцип (verbatim из реферата): «divide the sample into strata, compute the difference-in-means per
stratum, average the estimand on each stratum, weighting by the strata size».

Для пары control(c)/treatment(t), по стратам s:
- Per stratum эффект: `Δ_s = m_{t,s} − m_{c,s}` (continuous: средние; binary: доли).
- Per stratum дисперсия (unpooled, как существующие `_continuous_comparison`/`_binary_comparison`):
  `Var(Δ_s) = v_{c,s}/n_{c,s} + v_{t,s}/n_{t,s}`.
- Веса по наблюдаемой доле страты: `w_s = N_s / N`, `N_s = n_{c,s} + n_{t,s}`, `N = Σ_s N_s`.
- Post-stratified эффект: `Δ = Σ_s w_s · Δ_s`.
- **Conditional** (на наблюдаемых размерах страт) дисперсия: `Var(Δ) = Σ_s w_s² · Var(Δ_s)`.
- `z = Δ / sqrt(Var(Δ))`, two-sided p, CI = `Δ ± z_{α/2}·sqrt(Var(Δ))`.
- Снижение дисперсии: `var_reduction_pct = (1 − Var(Δ) / Var(Δ_pooled))·100`, где `Var(Δ_pooled)` —
  наивная дисперсия разности на всей выборке (без стратификации). Честно помечаем как conditional
  оценку (на observed strata sizes) — стандартная практика, не финитно-точная Neyman-форма.

## Design decisions (зафиксированы после чтения кода)
- **Stdlib**, без numpy (как все `stats/*.py`). Новый `stats/stratification.py`: чистые функции
  per-stratum combine + var_reduction. Переиспользует механику z/p/CI (`stats/binary`/`continuous`
  дают SE; здесь только взвешенная свёртка — НОВОЙ тест-статистики нет, уроки D-1/E5).
- **Ingestion (продуман ПЕРВЫМ, как требует handoff):** страта юзера известна на момент назначения
  (platform/country/...), но `exposures` её НЕ хранят и `attributes` в assign-пути отбрасываются.
  Решение зеркалит F3a: **новая таблица `user_strata`** (НЕ ALTER exposures — избегаем хрупкого
  SQLite rebuild), `(id, experiment_id, user_id, stratum, created_at)`, `UNIQUE(experiment_id, user_id)`
  first-write-wins (страта фиксируется при первом назначении, как exposure). CREATE IF NOT EXISTS в
  ОБОИХ `_init_db`. **schema_version 10→11.** PG-миграций в проекте нет (известное ограничение); SQLite
  `_migrate_db` ничего не бэкфиллит (старых страт нет — фича новая). Новый endpoint
  `POST /api/v1/experiments/{id}/strata`.
- **ОДНА категориальная страта на эксперимент** (значение per user). Multi-dimensional cross-product
  страт (platform×country) — **осознанный non-goal** (разреживает страты, как MVP targeting): клиент
  при желании сам кодирует составную страту в одну строку («ios|US»). MVP даёт честный, closed-form
  post-stratification и достаточен как дифференциатор.
- **«Покрытый» юзер = exposed (variation_index≥0) И имеет страту.** Holdout (−1) исключён. JOIN (не
  LEFT JOIN) на `user_strata` — юзеры без страты просто не входят в стратифицированную оценку (блок
  честно показывает covered_users_total vs exposed_users_total).
- **Минимальная страта:** страту считаем только если в ней есть ОБЕ руки с n≥2 (иначе Var(Δ_s)
  неопределена). Страты с пустой рукой пропускаются (документируем как dropped) — без тихого
  включения мусора. Если ни одной валидной страты → `unavailable`.
- **dual-SQL aggregates:** `get_stratified_aggregates` = калька `get_experiment_analysis_aggregates`
  + `JOIN user_strata` + `GROUP BY stratum, variation_index`. Portable (`?`→`%s`). Возврат: per
  (stratum, variation) `{exposed_users, converted_users, value_sum, value_sq_sum}` (тот же shape, что
  у основного ридера — переиспользуем `_arm_stat`/`_continuous_moments`).
- **Контракт:** новый `LiveStratifiedBlock` + поле `stratified` на live-stats ответе (рядом с `cuped`,
  не вместо). Binary И continuous (в отличие от CUPED — только continuous). `MAX_STRATA` в constants.

## Tasks
- [ ] 1. `stats/stratification.py` (stdlib): `post_stratified_effect(strata)` → Δ, var, z, p, ci +
      `variance_reduction(...)`. Валидация (непустые страты, n≥2 в обеих руках). k=1 страта == unadjusted.
      → Verify: `pytest test_stratification.py` (task 8).
- [ ] 2. БД: таблица `user_strata` в обоих `_init_db` (SQLite+PG) + индекс; bump `schema_version`
      10→11. → Verify: свежая SQLite БД имеет таблицу (PRAGMA); diagnostics schema_version==11.
- [ ] 3. `repository.record_strata` (INSERT ON CONFLICT DO NOTHING, first-write-wins) +
      `get_stratified_aggregates(experiment_id, metric_name)` (dual-SQL group-by stratum×variation).
      → Verify: round-trip тест SQLite (task 8).
- [ ] 4. Схемы: `StratumEvent{user_id, stratum}` + `StratumIngestRequest{strata[]}`;
      `LiveStratifiedBlock` + `LiveStratifiedStratum` + `LiveStratifiedComparison`; поле `stratified` на
      live-stats ответе. Endpoint `POST .../strata` в `routes/execution.py`. Регенерить контракт
      (`generate_frontend_api_types.py` + `generate_api_docs.py`). → Verify: `--check` up-to-date.
- [ ] 5. `live_stats_service._build_stratified_block`: per-stratum binary/continuous моменты → per-arm
      Δ_s/Var_s → weighted combine через `stats/stratification.py`; FWER `adjusted_alpha`; wire в
      `build_live_stats` + `_compute_live_stats` (читать `get_stratified_aggregates`). → Verify: live-тесты.
- [ ] 6. Frontend `LiveStatsSection.tsx`: блок post-stratification (список страт n_s/Δ_s + общий Δ, CI,
      var_reduction). → Verify: tsc + vitest LiveStatsSection.
- [ ] 7. i18n×7: `results.liveStats.stratified*` во все локали (Edit, не Python; `{{n}}` не `{{count}}`;
      «post-stratification» как термин не переводим, поясняем). → Verify: `check_locale_content.py` + паритет.
- [ ] 8. Тесты: `test_stratification.py` (1 страта==unadjusted; коррелирующая страта→reduction>0;
      страта без сигнала→≈unadjusted; weighted vs ручной расчёт; краевые: пустая рука/одна страта) +
      `test_execution_live_stats` (live happy binary+continuous / insufficient / dropped-stratum) +
      `test_postgres_backend` (+strata round-trip → verify-postgres) + vitest. → Verify: серийный гейт.

## Done When (Phase: Verification — LAST) — ✅ ВЫПОЛНЕНО 2026-06-26
- [x] Серийный гейт зелёный (Windows): mypy `--strict` (65 файлов) · tsc · vitest LiveStatsSection
      (9 passed, +1) · `vite build` (485.54 kB < 500) · `check_locale_content.py` (14 чисты) ·
      contract `--check` (TS + API.md up to date) · **весь backend 640 passed / 12 skip**
      (12 skip = PG round-trip, вкл. новый strata-тест — на Win нет Docker).
- [x] Обратная совместимость: одна страта на всех даёт тот же Δ, что unadjusted (effect == 2.0 ==
      `comparisons[0].analysis.observed_effect`, variance_reduction == 0.0).
- [x] Контракт/локали/mypy чисты; план помечен done; handoff + память обновлены.

> **dual-SQL (Postgres) НЕ проверен локально** (нет Docker на Windows): `test_postgres_backend_
> stratified_aggregates_round_trip` среди 12 skip. Валидация — CI `verify-postgres` при push +
> (рекомендация Юли) прогон на `deproject-mac`. push/PR/merge — по слову Юли (эта сессия: «продолжи
> работу» → локальный коммит на ветке `feat/post-stratification`, stacked поверх F3a PR #25).

> **dual-SQL (Postgres) НЕ проверить на Windows** ([[no-docker-on-windows]]) — PG round-trip среди skip.
> Валидация — CI `verify-postgres` при push + (рекомендация Юли) прогон на `deproject-mac`.
> push/PR/merge — по слову Юли (эта сессия: «продолжи работу», НЕ «реши сам» → локальный коммит).

## Risks / гочи
- Conditional vs Neyman-точная дисперсия post-stratification: берём conditional (на observed strata
  sizes) — стандартна и закрытая; документируем честно, не обещаем finite-sample оптимальность.
- Страты с одной рукой / n<2 → Var(Δ_s) неопределена: пропускать (dropped), не падать; если все
  невалидны → `unavailable`. Тест обязателен.
- var_reduction может быть ОТРИЦАТЕЛЬНЫМ при плохих/мелких стратах (Miratrix: «can increase variance if
  the number of strata is large and strata poorly chosen») — показывать честно (не клампить в 0).
- Контракт: `stratified` — НОВОЕ поле рядом с `cuped`; не ломать существующее.
- schema_version 10→11 бампать в реальном пути + api diagnostics-тесте, НЕ в мок-делегации PG-теста.
- push/PR/merge/deploy — НЕ /auto: по слову Юли.
