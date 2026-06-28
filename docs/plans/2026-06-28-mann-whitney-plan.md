# AB_TEST — Mann–Whitney U (Wilcoxon rank-sum): non-parametric two-sample analyzer

> **Зачем.** Запрос Юли 2026-06-28: «насколько широко покрыты A/B-тесты? Тест Манна-Уитни есть?».
> Аудит: **нет** — весь continuous-путь параметрический (z/Student-t по среднему + CUPED), непараметрики
> нет нигде (grep по `app/`, аудитам, планам, handoff — пусто). Это главный gap по широте: продуктовые
> continuous-метрики (revenue, time-on-site, AOV) сильно скошены с тяжёлыми хвостами, где t/z по среднему
> чувствителен к выбросам. Mann–Whitney проверяет сдвиг распределения / стохастическое доминирование,
> устойчив к выбросам, не требует нормальности. Юля выбрала «2-3» → этот срез (полный) + затем F3.

## Ключевое design-решение
Mann–Whitney **ранговый** → нужны **сырые значения по юнитам**, а не сводка (mean/std/n). Текущий
`ObservedResultsContinuous` несёт только сводку → требуется **новый input-режим raw samples** на post-hoc
пути `/api/v1/results` (диспетчер `results_service.analyze_results` по `metric_type`). Эндпоинт НЕ новый —
переиспользуем `/results` + `ResultsResponse` (U→test_statistic, p, Hodges–Lehmann shift→effect+CI,
rank-biserial/CLES→effect_size). Это автономно: без dual-SQL, без миграций БД, тестируется на Windows.

## Математика (досверить ПРИ реализации, не из памяти — [[dont-claim-unverified]])
Источник: Mann & Whitney 1947; Hollander, Wolfe & Chicken *Nonparametric Statistical Methods*;
Hodges & Lehmann 1963 (оценка сдвига). Объединённое ранжирование с midrank на ties.
- `U₁ = R₁ − n₁(n₁+1)/2`, `U₂ = n₁n₂ − U₁` (R₁ — сумма рангов control).
- `μ_U = n₁n₂/2`; tie-corrected `σ²_U = (n₁n₂/12)·[(N+1) − Σ(tⱼ³−tⱼ)/(N(N−1))]`, N=n₁+n₂.
- `z = (U_t − μ_U ∓ 0.5)/σ_U` (continuity correction), two-sided `p = 2(1−Φ(|z|))`.
- CLES `= U_t/(n₁n₂)` = P(treatment>control) (ties=0.5); rank-biserial `r = 2·CLES − 1 ∈ [−1,1]`.
- Hodges–Lehmann shift = median по всем парным `(t_j − c_i)`; rank-based CI по нормальной аппроксимации
  (индексы `K = round(μ_U − z_{α/2}·σ_U)`, границы — порядковые статистики парных разностей).
  **Cap** на n₁·n₂ (напр. 4·10⁶) — иначе память; сверх cap честный fallback (медианный сдвиг) + дисклеймер.
- Малые выборки: нормальная аппроксимация (как scipy `method='asymptotic'`); exact-распределение — future,
  пометить дисклеймером (как делает проект для других approximate-режимов).

## Tasks (PR A — Mann–Whitney, ветка `feat/mann-whitney`)
- [ ] `stats/mann_whitney.py` (stdlib): чистые функции U/z/p/CLES/rank-biserial/HL+CI, `None` на вырожденных
      (n<2 в руке, нулевая дисперсия рангов). → Verify: `python -c` smoke на каноническом примере.
- [ ] `tests/test_mann_whitney.py`: канон (U,z,p руками), ties-поправка, property (U₁+U₂=n₁n₂, симметрия,
      сдвиг-инвариантность, монотонность по сдвигу, идентичные→p≈1, CLES∈[0,1], r=2·CLES−1), HL восстанавливает
      сдвиг, **Monte-Carlo**: под H₀ type-I ≈ α, под сдвигом мощность растёт. → Verify: `pytest -q test_mann_whitney`.
- [ ] Схема `schemas/api.py`: новый `ObservedResultsRanked(control_values,treatment_values,alpha)` (валидация
      finite, min_length=2, max_length cap); `ResultsRequest.metric_type`+`"mann_whitney"`, поле `ranked`,
      расширить `check_type`; `ResultsResponse` +опц. `effect_size`/`effect_size_label` (additive). → Verify: mypy.
- [ ] Сервис `results_service.py`: `_analyze_mann_whitney`, ветка в `analyze_results`; degenerate→reuse;
      interpretation через `translate("results.interpretation.mann_whitney", …)`. → Verify: pytest results_service.
- [ ] Контракт: `python scripts/generate_frontend_api_types.py` + `generate_api_docs.py`; `--check` зелёный.
- [ ] i18n backend ×7 (`app/backend/app/i18n/*.json`): `results.interpretation.mann_whitney` (+effect_size labels,
      +любые новые error-строки). Verdict-строки переиспользуются. Писать через Edit (не Python — mojibake).
- [ ] Frontend `ObservedResultsSection`: режим `mann_whitney` + два textarea raw values (парс по запятой/пробелу/
      переводу строки), вывод U/z/p/CLES/HL/CI. i18n frontend ×7 (`app/frontend/public/locales/*.json`).
- [ ] Frontend tests (vitest) на новый режим; `vitest run --no-file-parallelism`, `tsc`, `vite build`.
- [ ] **Serial gate (Windows, по очереди):** mypy `--strict` → pytest (затронутое) → contract `--check` →
      `check_locale_content.py` (mojibake) → tsc → vitest → vite build. Полный backend/full vitest — CI.

## Done When (PR A)
- [ ] Mann–Whitney доступен на `/results` (`metric_type:"mann_whitney"`, raw samples), корректные U/z/p/CLES/HL+CI.
- [ ] Property + Monte-Carlo (type-I≈α, мощность↑) зелёные; ties-поправка проверена; degenerate обработан.
- [ ] Контракт/локали(14)/mypy-strict/tsc/vitest/build в порядке; UI без emoji/stock-icon ([[no-emoji-no-stock-icons]]).
- [ ] Отдельный PR; push/PR/merge — по слову Юли (не /auto). Память + handoff обновлены.

## PR B (F3 multi-covariate CUPED + stratification) — УЖЕ ВЛИТО В MAIN (проверено 2026-06-28)
**Re-implement НЕ нужно.** План 2026-06-25 устарел: F3 доделан за прошедшие дни. Проверено по коду в HEAD:
- F3a multi-covariate CUPED: `stats/cuped.py` (нормальные уравнения Σ_xx·θ=Σ_xy через Gaussian elimination
  + partial pivoting, `adjusted_variance` полная квадратичная форма, k=1 → single-covariate). Dual-SQL таблица
  `pre_period_covariates` с миграцией из legacy `pre_period_values` в `repository._init_db` (оба backend).
  `live_stats_service._build_cuped_block` реально решает multi-X (`cuped.cuped_theta(sigma_xx, sigma_xy)`),
  отдаёт per-covariate θ + `num_covariates`. Frontend (LiveStatsSection/WizardDraftStep) есть.
- F3b post-stratification: `stats/stratification.py` + `_build_stratified_block` + frontend.
- Тесты: `test_cuped_math.py` + `test_stratification.py` — 29 passed.
Решение `cuped_theta` сделано на stdlib (Gaussian elimination), НЕ numpy — точнее плана (держит stats пакет
без зависимостей). Следующая ось/фича — на усмотрение Юли (Mann–Whitney sizing? exact small-sample p? quantile TE?).

## Риски / гочи
- Raw-sample вход новый — продумать парсинг чисел в UI (запятая-десятичная vs разделитель). Cap длины массива.
- HL CI на больших n: O(n₁n₂) память → cap + честный fallback, не молчать ([[no-silent-caps]]).
- Не вводить новую тест-статистику в СУЩЕСТВУЮЩИЕ пути — это НОВЫЙ путь (`mann_whitney`), не правка continuous (урок D-1/E5 соблюдён).
- Формулы (tie-correction, HL CI индексы) досверить с источником при реализации, не из памяти.
