---
title: "AB_TEST — насколько покрыт репертуар статистических тестов (2026-06-29)"
---

# AB_TEST — насколько покрыт репертуар статистических тестов (2026-06-29)

> Ответ на вопрос Юли: «насколько покрыты все возможные варианты тестов?»
> Это инвентаризация ПО КОДУ (не по памяти): `app/backend/app/stats/*` + диспетчеры
> `services/results_service.py` (post-hoc) и `services/calculations_service.py` (планирование).
> Верифицировано на main `7db2fc9e`.

## 1. Что реально есть (по коду)

### Post-hoc анализ `/results` — диспетчер `analyze_results` (8 маршрутов)
| metric_type | Тест | Модуль | Эффект+CI |
|---|---|---|---|
| `binary` | Two-proportion z-тест | `binary.py` | abs. diff + Wald CI |
| `fisher_exact` | Fisher's exact 2×2 (точный условный, гипергеом.) | `fisher_exact.py` | odds ratio |
| `continuous` | **Welch** t-тест (неравные дисперсии, Welch df) | `continuous.py`/`student_t.py` | mean diff + t-CI |
| `mann_whitney` | Mann–Whitney U — **exact (N≤30, tie-free)** иначе asymptotic z | `mann_whitney.py` | rank-based |
| `bootstrap` | Permutation + percentile-bootstrap CI разницы средних | `bootstrap_permutation.py` | mean diff + Cohen's d |
| `quantile` | Quantile treatment effect (permutation по выбранному квантилю) | `quantile_te.py` | quantile diff |
| `count` | Poisson rate (two-sample, сведён к усл. биномиальному) | `poisson_rate.py` | rate ratio |
| `ratio`* | Delta-method для R=E[Y]/E[X] | `ratio.py` | ratio diff |

\* `ratio` доступен на live/MVP-пути (`live_stats_service`), не в основном `analyze_results`-диспетчере.

### Планирование/сайзинг — `calculations_service.calculate` (метрики: binary, continuous, ratio)
- `calculate_binary_sample_size`, `calculate_continuous_sample_size`, `calculate_detectable_mde_*`
- `bayesian_sample_size_binary/continuous` (precision-based)
- `sequential_sample_size_inflation` (поправка на последовательный дизайн)
- `estimate_experiment_duration_days`

### Семейства за рамками одного теста
- **Sequential / always-valid:** O'Brien–Fleming (`sequential.py`), mSPRT always-valid (`always_valid.py`)
- **Множественные сравнения:** Benjamini–Hochberg + Holm (`multiple_testing.py`)
- **Снижение дисперсии:** CUPED (multi-covariate, `cuped.py`), пост-стратификация (`stratification.py`)
- **Bayesian:** Monte-Carlo постериор + precision sizing (`bayesian.py`)
- **Диагностика:** SRM через chi² (`srm.py`), guardrail — направленная регрессия / односторонний non-inferiority margin (`guardrail.py`)

## 2. Универсум методов A/B-тестирования → покрытие

| Класс метрики / задача | Канонический тест | Статус |
|---|---|---|
| Доля/конверсия (2 группы) | z-тест двух долей | ✅ |
| Доля, малые выборки | Fisher's exact 2×2 | ✅ |
| Доля, точный безусловный | Barnard's exact | ⬜ ниша |
| Среднее непрерывной | Welch / Student t | ✅ (Welch) |
| Непрерывная, непараметрика | Mann–Whitney U (+exact) | ✅ |
| Непрерывная, без допущений | Bootstrap / permutation | ✅ |
| Хвосты/медиана распределения | Quantile treatment effect | ✅ |
| Робастная к выбросам | Trimmed-mean / Yuen | ⬜ ниша |
| Ratio-метрики (на пользователя) | Delta-method | ✅ (live-путь) |
| Счётчики/интенсивность | Poisson rate | ✅ |
| **Категориальная r×c (>2 исхода)** | **Chi² независимости + Cramér's V** | **❌ ГЭП** |
| **Эквивалентность/не-хуже** | **TOST (two one-sided)** | **❌ ГЭП** |
| Время до события | Log-rank / survival | ⬜ ниша для web-A/B |
| Кластерные данные | Cluster-robust / GEE | 🟡 частично (ratio delta) |
| **Последовательный дизайн** | OBF + always-valid mSPRT | ✅ |
| **Множественность** | BH + Holm | ✅ |
| **Снижение дисперсии** | CUPED + стратификация | ✅ |
| **Bayesian** | MC-постериор | ✅ |
| **SRM-диагностика** | chi² goodness-of-fit | ✅ |
| Sizing непараметрики/квантилей | ARE-инфляция t-сайзинга | 🟡 нет (только парам.) |

## 3. Честный вердикт

**Mainstream-репертуар A/B-тестирования покрыт на ~85–90%.** Закрыты все три массовых
типа метрик (доля / среднее / ratio / счётчик), параметрика и непараметрика, точные
малые выборки, последовательный дизайн, множественность, снижение дисперсии, Bayesian и
ключевая диагностика (SRM, guardrail). Это широкий, не учебный набор.

**Реальные (не нишевые) гэпы — ранжированы:**
1. **Эквивалентность/не-инфериорность (TOST)** — массово ожидаемое решение «доказать, что
   разницы НЕТ в пределах ±margin» (бэкенд-миграции, рефакторинг без регресса). Сейчас
   guardrail ловит односторонний вред, но симметричного теста эквивалентности нет.
   *Ложится в scalar effect+CI, переиспользует continuous-вход → дёшево и безопасно.*
2. **Chi² независимости r×c + Cramér's V** — единственная целая форма метрики (мультиномиальный
   исход, >2 категории), которую инструмент не считает. *Дорого: не-scalar ответ + новый UI
   с динамическими строками категорий (флаг в handoff).*
3. **Sizing для непараметрики/квантилей** — паритет планирования (ARE-инфляция t-сайзинга).
   Мелко, но без UI-дома (визард планирует только параметрику).

**Нишевые (низкий приоритет для web-A/B):** Barnard's exact, G-test, Yuen trimmed-mean,
log-rank/survival, явный cluster-robust.

## 4. Решение на эту сессию (/auto «продолжи»)

Беру **гэп #1 — TOST equivalence на continuous-пути**: highest-value, ложится в существующую
scalar-схему ResultsResponse, переиспользует `ObservedResultsContinuous` + поле `margin`,
повторяет проверенный паттерн тоггла (fisher/bootstrap/quantile) → Windows-verifiable, низкий
архитектурный риск, завершаемо+верифицируемо за сессию.

Гэп #2 (chi² r×c) оставлен как следующий крупный срез (новый UI + не-scalar ответ) — под
отдельную сессию, не бить в одном автономном проходе. Гэп #3 (непарам. sizing) — мелкий
follow-up после того как у непараметрики появится планировочный дом.
