# Phase 2 gap report

Дата: 2026-04-21
Статус: пройдено без код-фиксов

## Источники constraints

- `docs/plans/codex-tasks/phase-2-1-data-visualization.md`
- `docs/plans/codex-tasks/phase-2-2-visual-polish.md`
- `docs/plans/2026-04-21-phase-2-bundle-baseline.txt`

## Проверки

### 1. Reduced motion

Статус: пройдено

- В `app/frontend/src/styles/utilities.css` есть глобальный блок `@media (prefers-reduced-motion: reduce)`.
- Внутри блока отключаются и `transition`, и `animation` для `*`, `*::before`, `*::after`, что соответствует constraint из Phase 2.2.
- `utilities.css` подключён глобально через `app/frontend/src/main.tsx`, поэтому правило применяется ко всему приложению.

Правка: не требуется.

### 2. Accessibility checks

Статус: пройдено

- `app/frontend/src/components/Skeleton.tsx` рендерит `aria-hidden="true"`.
- `app/frontend/src/components/ProjectListSkeleton.tsx` и `app/frontend/src/components/ResultsSkeleton.tsx` также помечены `aria-hidden="true"` на корневом контейнере.
- Theme toggle в `app/frontend/src/App.tsx` использует `role="group"` с `aria-label="Theme preference"`, а каждая кнопка имеет собственный `aria-label` и `aria-pressed`.
- `app/frontend/src/components/ChartErrorBoundary.tsx` в fallback рендерит только текстовый контент (`div`, `strong`, `pre`) без tabbable-элементов; по коду это не должно ломать tab-order.

Правка: не требуется.

Примечание: последний пункт подтверждён code audit, без отдельной browser-проверки tab navigation.

### 3. Bundle budget и lazy-loading

Статус: пройдено

- По свежему `npm run build` из `docs/plans/2026-04-21-phase-2-bundle-baseline.txt` основной JS chunk: `dist/assets/index-BpUhWkqB.js` = `114.80 kB gzip`, что ниже лимита `< 130 kB`.
- Chart chunk вынесен отдельно: `dist/assets/PowerCurveChart-HBJ2y2s-.js` = `107.09 kB gzip`.
- В `app/frontend/src/components/results/PowerCurveSection.tsx` график грузится через `lazy(() => import("../PowerCurveChart"))`.
- В `app/frontend/src/components/ResultsPanel.tsx` секция с power curve появляется только когда есть `displayedAnalysis?.report` и анализ не находится в состоянии `isAnalyzing`, то есть chunk не нужен в initial render без results.
- В `app/frontend/src/components/PowerCurveChart.tsx` используются именованные импорты из `recharts`, а не namespace/default import всей библиотеки.
- В `app/frontend/src/components/SensitivityTable.tsx` используется обычная HTML-таблица, без canvas, что соответствует constraint из Phase 2.1.

Правка: не требуется.

## Итог

- Обязательные constraints по reduced-motion, a11y и bundle/lazy-loading в текущем working tree соблюдены.
- Точечные код-фиксы по пункту `B` не понадобились.
- Для следующего шага можно опираться на этот report как на подтверждение Phase 2 visual gate.
