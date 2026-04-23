# Prompt для Opus (effort max) — a11y axe() >30s timeouts

Запрос: скопировать всё ниже линии в claude.ai с моделью Opus 4.x + extended thinking (budget max). Ожидаемый результат — root cause identification + 1-2 конкретные minimal-footprint strategies с estimated ROI. Самому ничего не менять в моём репо; только анализ.

---

# Диагностика: 4 vitest теста упираются в 30000ms timeout при вызове `axe()` в a11y-suite

## Репозиторий

Публичный GitHub: https://github.com/brownjuly2003-code/ab-test-research-designer
HEAD на момент прогона: `f4178dd3`
Главный файл плана (мой текущий spec на фикс): https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/plans/codex-tasks/2026-04-23-cx-a11y-test-perf.md

Стек:
- Backend: FastAPI 0.128 + Python 3.13 + SQLite
- Frontend: React 19 + TypeScript + vitest 3.x + @testing-library/react + happy-dom + jest-axe (axe-core wrapper) + recharts
- Репо: 1 main branch, CI green через `scripts/verify_all.py` (который не запускает полный `npm run test` — поэтому unit suite красный локально не ломает pipeline).

## Проблема

При прогоне `npm --prefix app/frontend run test` падают 4 теста с ошибкой `Error: Test timed out in 30000ms`. Остальные ~208 тестов зелёные. Global `testTimeout` в vitest config — 30000ms.

Все 4 теста делают одно и то же по форме:
1. Рендерят React компонент через `@testing-library/react` с harness.
2. `await flushEffects()` 1-2 раза.
3. `const results = await axe(view.container)` — это **зависает** >30s.
4. `expect(results).toHaveNoViolations()`.
5. `view.unmount()` в `finally`.

### Failing tests (с path:line)

| Test file | Line | Компонент под axe() |
|---|---|---|
| `app/frontend/src/App.test.tsx` | ~829 | `<App />` full mount (включает Wizard, Results, Sidebar) |
| `app/frontend/src/components/PosteriorPlot.test.tsx` | ~67 | `<PosteriorPlot />` (recharts SVG с credibility interval) |
| `app/frontend/src/test/a11y-comparison-dashboard.test.tsx` | ~58 | `<ComparisonDashboardHarness />` (recharts forest/power plots + 3 seeded projects) |
| `app/frontend/src/test/a11y-results.test.tsx` | ~74 | `<ResultsPanel />` (recharts PosteriorPlot + PowerCurve + sensitivity tables) |

GitHub URLs для контента:
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/src/App.test.tsx
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/src/components/PosteriorPlot.test.tsx
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/src/test/a11y-comparison-dashboard.test.tsx
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/src/test/a11y-results.test.tsx

Компоненты под тестом:
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/src/components/ResultsPanel.tsx
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/src/components/PosteriorPlot.tsx
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/src/components/ComparisonDashboard.tsx

Конфиг vitest и setup:
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/vite.config.ts
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/src/test/setup.ts
- https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/app/frontend/package.json

## Что я уже попробовал (и откатила как false completion)

Первая попытка шортcut'ом:

1. Отключить правило `color-contrast` в axe во всех 4 тестах:
   ```ts
   const axeOptions = { rules: { "color-contrast": { enabled: false } } };
   const results = await axe(view.container, axeOptions);
   ```
2. Поднять per-test timeout: 15000 → 25000 (PosteriorPlot), 15000 → 20000 (a11y-comparison).

**Результат:** `App.test.tsx` и `PosteriorPlot.test.tsx` иногда проходят; `a11y-results.test.tsx` и `a11y-comparison-dashboard.test.tsx` по-прежнему падают в `Test timed out in 30000ms`.

**Вывод:** disable + bump не фиксит root cause; это маскировка, которая ломается, как только компонент чуть-чуть вырастает. Всё откатила `git checkout --` до того, как попало в main.

## Гипотезы, которые у меня есть

Уже описаны в моём spec'е https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/plans/codex-tasks/2026-04-23-cx-a11y-test-perf.md — три варианта: (A) слишком большой axe rule-set на большой DOM, (B) зависший promise / useEffect / unmocked async, (C) recharts SVG обход через axe-core занимает O(rules × nodes) и это буквально >30s.

Есть инстинкт, что это **C** — ResultsPanel + ComparisonDashboard рендерят несколько recharts компонент одновременно, каждый — SVG с сотнями нод (grid lines, tick labels, datapoints), и axe-core честно бегает все wcag2aa rules по всем узлам. Но это спекуляция, не данные.

## Что я хочу от тебя (Opus, extended thinking)

1. **Root cause identification.** Какая из гипотез (A / B / C) или какая четвёртая наиболее вероятная причина >30s axe() на этих конкретных тестах? Обоснуй цепочкой рассуждений, привязанной к коду компонент (почитай через WebFetch ResultsPanel.tsx, ComparisonDashboard.tsx, PosteriorPlot.tsx).

2. **Minimal-footprint fix.** Опишу две вещи: (a) что поменять (точечно, без отключения rules и без bump timeout выше 15-20s); (b) какой тип компромисса я беру — performance cost vs coverage loss vs test reliability. Идеальный фикс сохраняет все axe rules (включая `color-contrast`) и работает за <10s per test.

3. **Fallback plan.** Если root cause оказывается неустранимым дешево (например, recharts SVG требует 20k+ обходов, и только mock его удаляет) — что ты выберешь: axe `runOnly: {type: 'tag', values: ['wcag2a']}` (сохраняет критичные rules, убирает experimental/best-practice), `vi.mock('recharts', ...)` в beforeAll конкретных файлов, или scoped-container `axe(view.container.querySelector('[role="region"]'))`? Или комбинацию?

4. **Что НЕ надо.** Не нужен overhaul архитектуры, не нужно сменить test runner, не нужно поднимать `testTimeout` глобально до 60s. Хочу точечный фикс, который попадает в спек `docs/plans/codex-tasks/2026-04-23-cx-a11y-test-perf.md`.

5. **Формат ответа.** Предпочту: (i) "наиболее вероятная причина: X, потому что [рассуждение], подтверждение через Y observation"; (ii) "конкретный патч" — в виде унифицированного diff hunks или `apply_patch` блока, максимум 30-50 строк изменений суммарно по файлам; (iii) 2-3 предложения про fallback и tradeoff.

Если решишь, что надо запустить сами тесты локально (через Agent / Bash в среде, где можно cloneить github) — можешь (я могу применить patch'и и дать тебе `axe-timing` числа). Но если прямой анализ достаточен для уверенного ответа — не гоняй circles, давай фикс.
