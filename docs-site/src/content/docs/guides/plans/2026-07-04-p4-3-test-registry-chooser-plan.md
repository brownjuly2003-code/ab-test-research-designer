---
title: "P4.3 — Registry-рефактор выбора теста + мини-чузер «какой тест выбрать»"
---

# P4.3 — Registry-рефактор выбора теста + мини-чузер «какой тест выбрать»

Audit refs: `audit_fable_02_07_2026.md` §5.5 (ternary-лестницы), §6.2 п.7 (guided-выбор теста).
Tracker: `audit_plan_02_07_26.md` задача 4.3 (O48 medium).

## Проблема

1. **§5.5.** `ObservedResultsSection.tsx` держал три параллельные вложенные ternary-лестницы
   (`effectiveMetricType`, `supportedTypes` + `nextTest`, `stateMetricType`), плюс лестницы в
   `ObservedResultsView.tsx` (кнопки тоггла, hint, выбор формы). Каждая росла на ступень с каждым
   новым анализатором — при 9 анализаторах код становился нечитаемым, добавление теста требовало
   правок в 5+ местах.
2. **§6.2 п.7.** Тоггл выбора теста — плоские кнопки без подсказки «какой тест когда». При 7
   continuous-опциях нужен guided-выбор.

## Решение

### Registry (единый источник правды) — `observedResultsShared.ts`

- `BASE_DEFAULT_TESTS: Record<base, {metricType, labelKey, hintKey}>` — дефолтный («parametric»)
  тест на каждый базовый план (binary → z-test, continuous → t-test, ratio → continuous-approx).
- `ALTERNATIVE_TESTS: {test, metricType, availableFor, labelKey, hintKey}[]` — все альтернативы в
  порядке отображения; `availableFor` = какие базовые планы показывают опцию (count — все три).
- `FORM_BY_METRIC_TYPE: Record<metricType, formKind>` — какую форму читает анализатор.
- Хелперы, из которых выведены ВСЕ прежние лестницы:
  `observedTestButtons` (кнопки тоггла), `resolveEffectiveMetricType` (toggle→анализатор, с
  guard-fallback на дефолт если альтернатива не для этого базового плана — воспроизводит старую
  логику), `supportedObservedMetricTypes`, `restoreObservedTest` (обратный маппинг persisted→toggle),
  `observedTestHintKey`, `observedFormKind`.
- **Добавление анализатора = одна строка в `ALTERNATIVE_TESTS`** (+ label/hint i18n, + строка в
  `FORM_BY_METRIC_TYPE` если новая форма). Проверено round-trip-тестом.

Поведение сохранено 1:1 (юнит-тесты сверяют `supportedObservedMetricTypes`/`resolveEffectiveMetricType`
с прежними хардкод-наборами; hint-маппинг воспроизводит прежний «parametric показывает hint
альтернативы»).

### Мини-чузер — `internal/TestChooser.tsx` + pure-логика в shared

- `observedChooserQuestions(base)` — вопросы под базовый план (continuous: 3 — goal/distribution/focus;
  binary: 1 — small-sample; ratio: нет чузера, только 2 опции с разными данными).
- `recommendObservedTest(base, answers)` — чистая функция, null пока не отвечены все вопросы;
  continuous-приоритет: equivalence-goal → TOST; tail/percentile → quantile; skew/outliers → trimmed_t;
  small/non-normal → Mann–Whitney; иначе → t-test. binary: small → Fisher, иначе → z-test.
- Компонент: свёрнутая по умолчанию панель «Какой тест выбрать?», радио-вопросы, callout с
  рекомендацией (тем же лейблом, что кнопка тоггла) + «Использовать этот тест» → `onSelectTest`.
- **Lazy-loaded** (`lazy()`+`Suspense`) — держит `index.js` < 500 kB (499.63; TestChooser = 2.03 kB чанк).

## i18n

`results.observedResults.chooser.*` (toggle/description/incomplete/recommendation/apply + questions×4
+ rationale×7) во все 7 локалей — реальный перевод, не defaultValue (аддитивно, 7×47 строк,
mojibake-гейт чист).

## Verify

- tsc 0 · **полный vitest 62 файла / 384** (+30: observedResultsShared +27 registry/recommend,
  ObservedResultsSection +3 чузер) · vite build **index 499.63 kB < 500** · locale content 14 clean.
- Verify из трекера: «добавление нового анализатора = 1 строка в registry» — покрыто round-trip-тестом
  (`resolve → restore` для каждой кнопки каждого базового плана) и сверкой supported-наборов; vitest зелёный.
- Backend/схема НЕ трогались → contract `--check` без диффа, verify-postgres не релевантен.
