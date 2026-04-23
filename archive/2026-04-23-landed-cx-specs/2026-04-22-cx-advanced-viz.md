# CX Task: Advanced visualizations — Bayesian posterior plot + Sequential boundary chart

## Goal
Добавить в `D:\AB_TEST\` две визуализации для уже landed stat-методов: Bayesian posterior distribution plot и Sequential O'Brien-Fleming boundary chart. Обе — Recharts, lazy-loaded, в соответствующих Results-секциях.

## Context
- Репо: `D:\AB_TEST\`, `main`, HEAD после v1.0.0. Не ветка, не push.
- Backend уже реализует обе статистики:
  - Bayesian: `app/backend/app/stats/bayesian.py`, вызывается при `analysis_mode=bayesian` и возвращает поля в `CalculationResponse` — `bayesian_sample_size_per_variant`, `bayesian_credibility`, `bayesian_note` (см. `schemas/api.py`).
  - Sequential: `app/backend/app/stats/sequential.py`, поля `sequential_boundaries` (список dict-ов с per-look границами), `sequential_inflation_factor`, `sequential_adjusted_sample_size`.
- Frontend сейчас показывает эти данные только текстом в соответствующих секциях:
  - `app/frontend/src/components/results/SequentialDesignSection.tsx` — рендерит таблицу `sequential_boundaries`.
  - `PosteriorPlot.tsx` / `SequentialBoundaryChart.tsx` — **не существуют**.
- Recharts@^3.8.1 уже в deps, `PowerCurveChart.tsx` — референс паттерна (lazy-loaded, ResponsiveContainer, a11y-friendly).
- Bundle budget: main JS gzip < 130 KB; новые чарты должны быть lazy (`React.lazy` + `Suspense` с Skeleton fallback), не бандлиться в main.

## Deliverables
1. **`app/frontend/src/components/PosteriorPlot.tsx`:**
   - Props:
     ```ts
     interface PosteriorPlotProps {
       posteriorMean: number;
       posteriorStd: number;
       credibilityInterval: { lower: number; upper: number; level: number };
       priorMean?: number;
       priorStd?: number;
       metricType: "binary" | "continuous";
     }
     ```
   - Отображает posterior density (нормальная аппроксимация для начала) как область под кривой. Prior — пунктирная линия если передан. Credibility interval — shaded area между `lower` и `upper`.
   - Recharts `AreaChart` или `ComposedChart`. Дискретизация 200 точек для smooth curve.
   - Tooltip: `x=0.045` → `P(θ ≤ 0.045 | data) = 0.23`.
   - `role="img"` + `aria-label="Bayesian posterior distribution with {level}% credibility interval from {lower} to {upper}"`.
   - Высота 260px, responsive width.

2. **`app/frontend/src/components/SequentialBoundaryChart.tsx`:**
   - Props:
     ```ts
     interface SequentialBoundaryChartProps {
       boundaries: Array<{
         look: number;
         alpha_spent: number;
         upper_boundary_z: number;
         lower_boundary_z: number;
         sample_size_cumulative: number;
       }>;
       currentLook?: number;
     }
     ```
   - X axis: `look` (1..n), Y axis: z-statistic.
   - Две линии: upper boundary (red, solid), lower boundary (red, solid), symmetric around 0.
   - Horizontal reference lines `y=1.96` / `y=-1.96` (nominal critical value, dashed gray).
   - Если `currentLook` задан — vertical dashed line на текущем look.
   - A11y: `role="img"` + `aria-label="O'Brien-Fleming sequential boundaries across {n} looks"`.
   - Высота 240px.

3. **Wiring в Results sections:**
   - `SequentialDesignSection.tsx`: lazy-import `SequentialBoundaryChart` через `React.lazy`, оборачивать в `<Suspense fallback={<Skeleton height="240px" />}>`. Показывать только если `boundaries?.length > 0`.
   - Новый `app/frontend/src/components/results/BayesianSection.tsx` (или расширить существующую секцию если уже есть — проверить `ls app/frontend/src/components/results/`). Содержит текущий текстовый бейз + `<PosteriorPlot>` lazy-loaded. Показывать только если `analysis_mode === "bayesian"`.
   - Добавить BayesianSection в `ResultsPanel.tsx` между SequentialDesignSection и ObservedResultsSection (или по логическому месту, см. текущую структуру).

4. **Тесты:**
   - `app/frontend/src/components/PosteriorPlot.test.tsx`:
     - render + a11y-check (no axe violations)
     - credibility interval shading визуально присутствует
     - mock props, проверить нет runtime warnings
   - `app/frontend/src/components/SequentialBoundaryChart.test.tsx`:
     - render с 4 looks, проверить корректное кол-во данных
     - `currentLook=2` рендерит reference line
     - a11y-check
   - Интеграция в `App.test.tsx` или отдельный `a11y-bayesian-sequential.test.tsx` (follow pattern из существующих `a11y-*.test.tsx`):
     - Запустить анализ в bayesian mode с моком API → BayesianSection рендерится с PosteriorPlot.
     - Sequential mode с 4 looks → SequentialBoundaryChart рендерится.
   - Обновить snapshot `__snapshots__/WizardPanel.test.tsx.snap` если изменился (через `npm.cmd run test:unit -- -u`).

5. **Bundle-check:**
   - `npm run build` → main JS gzip остаётся < 130 KB.
   - Новые chunks: `PosteriorPlot-*.js` и `SequentialBoundaryChart-*.js` в отдельных файлах.

6. **Один коммит:**
   ```
   feat: bayesian posterior plot and sequential boundary chart
   ```

7. **Отчёт `docs/plans/2026-04-22-advanced-viz-report.md`:**
   - Bundle sizes (main + new chunks, gzip).
   - Number of new tests added.
   - Скриншоты обоих чартов (если e2e делает — ссылка на artefact); иначе — короткое ASCII-описание.

## Acceptance
- `scripts\verify_all.cmd --with-e2e` = exit 0.
- `npm run build` main JS gzip < 130 KB, `PosteriorPlot*.js` и `SequentialBoundaryChart*.js` присутствуют как отдельные chunks.
- Lighthouse a11y ≥ 0.9 (новые чарты не должны уронить скор).
- `npm.cmd run test:unit` — +6–10 новых тестов (2 unit + 2 a11y + ≥ 2 интеграция).
- Commit subject уникальный, `Co-Authored-By: Codex <noreply@anthropic.com>`.
- Этот CX-файл стадж в тот же коммит.
- `git status --short` = пусто.

## How
1. Baseline: `git status --short` = пусто, `scripts\verify_all.cmd` = 0.
2. Прочитать текущий `SequentialDesignSection.tsx` — понять источник данных. Прочитать `CalculationResponse` в `schemas/api.py` — подтвердить структуру полей.
3. Прочитать `PowerCurveChart.tsx` как референс паттерна (lazy + Recharts + a11y).
4. Написать `PosteriorPlot.tsx` + тест. Density вычисление — через normal PDF `(1/sqrt(2πσ²)) * exp(-(x-μ)²/(2σ²))` на 200 точках в `[μ-4σ, μ+4σ]`.
5. Написать `SequentialBoundaryChart.tsx` + тест.
6. Wiring в `SequentialDesignSection` и новый/расширенный `BayesianSection`.
7. Mount в `ResultsPanel.tsx`.
8. Bundle-check: `npm run build` посмотреть output.
9. Regen api-contract не нужен (backend не менялся) — просто проверить `generate_frontend_api_types.py --check` = 0.
10. Commit + verify + report.

## Notes
- **CX-файл hygiene:** staging этот файл.
- **Commit subject hygiene:** проверка на дубль.
- **НЕ** переделывать backend — данные уже есть в response.
- **НЕ** использовать Canvas / WebGL — Recharts достаточно.
- **НЕ** добавлять новые deps (`d3`, `chart.js` и пр.) — Recharts уже есть.
- **НЕ** lazy-loadить основной `ResultsPanel` — только новые чарты.
- Если PosteriorPlot с prior выглядит загромождённым — сделать prior опциональным флагом в UI (`showPrior` state, default off), либо просто рендерить если `priorMean/priorStd` заданы (задача это допускает).
- **Normal approximation** для posterior — ок для MVP. Если юзер попросит честный бета/гамма — отдельный таск.
- **Sequential boundaries** — использовать точные z-значения из backend; если их нет, backend нужно расширить — зафиксировать в отчёте и не пытаться угадать.
- Backend `test_performance` может флапнуть — перезапустить один раз.
- **НЕ** пушить на remote.

## Out of scope
- Интерактивное изменение prior в UI
- Exact beta/gamma posterior calculations (только normal approx)
- Download-chart-as-PNG (уже есть ChartExport — переиспользовать если тривиально)
- Monte Carlo simulation визуализация
- Comparison plots (два эксперимента side-by-side)
