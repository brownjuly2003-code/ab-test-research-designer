# T6: ResultsPanel декомпозиция (1919 → 11 секций + <150 строк)

**Phase:** BCG Phase 1
**Depends on:** T5 (App.tsx на stores)
**Effort:** ~4h

## Context

`app/frontend/src/components/ResultsPanel.tsx` — 1919 строк. Содержит 11+ логических секций: sensitivity, power curve, SRM check, observed results, sequential design, warnings, experiment design, metrics plan, risks, AI advice, comparison.

Читать перед стартом:
- `app/frontend/src/components/ResultsPanel.tsx` — полный файл
- `src/components/ResultsPanel.test.tsx`
- `src/components/ResultsPanel.module.css`
- `archive/2026-04-23-bcg-planning-docs/BCG_plan.md` §1.3.1-1.3.12

## Goal

Разрезать `ResultsPanel.tsx` на 11 секций в `src/components/results/*.tsx`. Итоговый `ResultsPanel.tsx` — тонкий orchestrator < 150 строк, импортирует и рендерит секции через `<Accordion>`.

## Steps

### 1. Создать директорию

```
src/components/results/
  SensitivitySection.tsx          (~200 стр)
  PowerCurveSection.tsx           (~50 стр)
  SrmCheckSection.tsx             (~120 стр)
  ObservedResultsSection.tsx      (~250 стр)
  SequentialDesignSection.tsx     (~80 стр)
  WarningsSection.tsx             (~60 стр)
  ExperimentDesignSection.tsx     (~100 стр)
  MetricsPlanSection.tsx          (~80 стр)
  RisksSection.tsx                (~60 стр)
  AiAdviceSection.tsx             (~60 стр)
  ComparisonSection.tsx           (~80 стр)
```

Каждая секция:
- Читает данные из `useAnalysisStore()` напрямую (или принимает как prop, если это view-only секция)
- Имеет свой scoped CSS (через `*.module.css` если нужен)
- Экспортирует default функциональный компонент

### 2. Миграция по одной секции за раз

Рекомендуемый порядок (от простого к сложному):
1. WarningsSection (чистый view)
2. RisksSection
3. MetricsPlanSection
4. ExperimentDesignSection
5. AiAdviceSection
6. PowerCurveSection (lazy-loaded, уже есть Suspense)
7. SequentialDesignSection
8. ComparisonSection
9. SrmCheckSection (с локальным state формы)
10. SensitivitySection (с локальным state формы)
11. ObservedResultsSection (binary + continuous формы + ForestPlot)

Для каждой:
- Вырезать код из `ResultsPanel.tsx`
- Вставить в новый файл, исправить импорты
- Запустить `npx vitest run`, убедиться что тесты зелёные
- Commit

### 3. Новый `ResultsPanel.tsx`

После выноса всех 11 секций — переписать `ResultsPanel.tsx` как orchestrator:

```tsx
import { Accordion } from "./Accordion";
import SensitivitySection from "./results/SensitivitySection";
// ... остальные импорты

export function ResultsPanel() {
  const results = useAnalysisStore(s => s.results);
  if (!results) return <EmptyState ... />;

  return (
    <div className="results-panel">
      <Accordion items={[
        { id: "warnings", title: "...", content: <WarningsSection /> },
        // ...
      ]} />
    </div>
  );
}
```

Целевой размер: **< 150 строк**.

### 4. CSS

Глобальные классы из `ResultsPanel.module.css` — разделить по секциям. Общие (шрифты, цвета) — оставить в `module.css` или вынести в `tokens.css`.

### 5. Тесты

- `ResultsPanel.test.tsx` — упростить до smoke-теста orchestrator'а
- Создать `src/components/results/__tests__/*.test.tsx` для каждой секции (минимум render + типовые данные)

### 6. Verify

```bash
cd app/frontend
wc -l src/components/ResultsPanel.tsx  # < 150
wc -l src/components/results/*.tsx     # каждая в рамках ожидаемого
npx vitest run
npx tsc --noEmit
npm run build
```

Ручная проверка: открыть results view → все 11 секций рендерятся, accordion раскрывается, sensitivity/SRM/observed формы работают, charts (power curve, forest plot) рендерятся.

## Done When

- [ ] 11 секций в `src/components/results/`
- [ ] `ResultsPanel.tsx` < 150 строк
- [ ] Все тесты зелёные
- [ ] Полный results view работает в браузере без регрессий

## Constraints

- НЕ вводить progressive disclosure (это BCG §2.3, Phase 2)
- НЕ менять логику расчётов или API
- Не терять ни одной фичи — все 11 секций должны остаться видимыми и функциональными
- Каждая секция читает данные напрямую из `useAnalysisStore()` (избегать prop drilling)
