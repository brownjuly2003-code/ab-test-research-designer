# CX Task: Verify & ship Plan A fix для a11y axe() timeouts (patches уже в worktree)

## Goal
Патчи Plan A (flat recharts mock + ResizeObserver stub + удалённые per-test timeout-bump'ы) **уже применены в рабочей копии** `D:\AB_TEST\`. Закоммичено только предыдущее (HEAD `07ae9b29`). Нужно: (1) прогнать frontend suite и подтвердить зелёный, (2) закоммитить патчи одним логичным коммитом, (3) пушнуть и убедиться, что CI зелёный. Это finisher-таск по spec'у `docs/plans/codex-tasks/2026-04-23-cx-a11y-test-perf.md` — root cause (гипотеза C по Opus: recharts SVG × wcag2aa rules = O(rules × nodes)) уже диагностирован, фикс применён.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD на момент выдачи таска — `07ae9b29`. Worktree НЕ чистый — содержит uncommitted изменения, описанные ниже. **Не запускать `git checkout --` на эти файлы.**

- **Root cause.** Opus (extended thinking max) подтвердил гипотезу C из `2026-04-23-cx-a11y-test-perf.md` для 3 тестов из 4: `PosteriorPlot.test.tsx`, `a11y-results.test.tsx`, `a11y-comparison-dashboard.test.tsx`. В каждом — recharts SVG с 200+ datapoints + ComposedChart/LineChart разворачиваются в >1000 нод, и axe-core wcag2aa обходит каждую для каждого rule → 15-30s честного compute. Для `App.test.tsx:814` root cause — гипотеза B (отсутствующий ResizeObserver stub в jsdom 28 + недостаточно `flushEffects()`).

- **Стратегия фикса.**
  1. **Flat recharts mock** (`app/frontend/src/test/recharts-stub.tsx`) — все экспорты recharts возвращают примитивные `<div>` / `null`. Используется через `vi.mock("recharts", () => import("../test/recharts-stub"))` (vitest hoist'ит, поэтому допустимо ставить до import блока).
  2. **Локализация флат-мока** в 3 тест-файлах с axe: PosteriorPlot test 1, a11y-results, a11y-comparison-dashboard. Все `timeout` параметры (15000, 25000) удалены — default vitest `testTimeout` 5000ms должен хватать с запасом.
  3. **PosteriorPlot test 2** ("renders a shaded credibility interval overlay") в `PosteriorPlot.test.tsx` проверяет `.recharts-area-area` — real recharts CSS class. Flat mock его ломает. Test перенесён в новый файл `app/frontend/src/components/PosteriorPlot.integration.test.tsx` (без mock'а, сохраняет coverage). В original остался `it.skip` с TODO-комментарием.
  4. **App.test.tsx:561 beforeEach** — добавлен `ResizeObserver` stub (был стаб только для `URL`). В тесте "has no critical accessibility violations on initial render" (строка ~814) добавлен второй `await flushEffects()` перед `axe()` чтобы Zustand bootstrap + i18n init + draftStore hydration успевали.

- **Изменённые файлы (worktree state):**
  - НОВЫЕ: `app/frontend/src/test/recharts-stub.tsx`, `app/frontend/src/components/PosteriorPlot.integration.test.tsx`
  - MODIFIED: `app/frontend/src/components/PosteriorPlot.test.tsx`, `app/frontend/src/test/a11y-results.test.tsx`, `app/frontend/src/test/a11y-comparison-dashboard.test.tsx`, `app/frontend/src/App.test.tsx`

- **Инвариант.** `color-contrast` rule НЕ отключён ни в одном файле. Все axe() вызовы работают с default rule-set (либо уже существующим `runOnly` для App.test.tsx).

- **НЕ трогать** backend, smoke, CI workflow, i18n JSON, snapshot_service, mkdocs-site. Всё остальное в docs/ тоже не трогать.

## Deliverables

1. **Sanity check worktree state:**
   ```bash
   git status --short
   ```
   Ожидание: 6 файлов в списке (2 untracked `??`, 4 modified `M`). Пути перечислены выше. Если список не совпадает — **остановиться** и вернуть отчёт, **не** пытаться "подчистить".

2. **Прогнать затронутые тесты таргетированно (быстрая обратная связь):**
   ```bash
   npm --prefix app/frontend run test -- --run \
     src/App.test.tsx \
     src/components/PosteriorPlot.test.tsx \
     src/components/PosteriorPlot.integration.test.tsx \
     src/test/a11y-results.test.tsx \
     src/test/a11y-comparison-dashboard.test.tsx \
     src/test/a11y-sidebar.test.tsx
   ```
   `a11y-sidebar.test.tsx` включён как drift canary — он не трогался в Plan A, должен остаться зелёным (если падает — значит что-то всё-таки изменилось).
   
   Ожидание: все файлы passing, длительность каждого axe-теста — меньше 5000ms (теперь без per-test timeout override'ов).

3. **Прогнать полный suite, 1 раз:**
   ```bash
   npm --prefix app/frontend run test -- --run
   ```
   Если хоть один тест упал — пойти в отчёт, **не** коммитить.

4. **Прогнать typecheck:**
   ```bash
   npx tsc --noEmit -p app/frontend/tsconfig.json
   ```
   Exit 0.

5. **Коммит** одним атомарным коммитом, через **explicit pathspec** (а не `git add -A`, т. к. в worktree могут быть сторонние side-effect изменения — см. memory про multi-agent workspace):
   ```bash
   git add \
     app/frontend/src/test/recharts-stub.tsx \
     app/frontend/src/components/PosteriorPlot.integration.test.tsx \
     app/frontend/src/components/PosteriorPlot.test.tsx \
     app/frontend/src/test/a11y-results.test.tsx \
     app/frontend/src/test/a11y-comparison-dashboard.test.tsx \
     app/frontend/src/App.test.tsx
   ```
   
   Сообщение:
   ```
   fix(test): unstick a11y axe timeouts via flat recharts mock
   
   Root cause: axe-core wcag2aa rules obey O(rules × nodes), and the
   recharts SVG tree in ResultsPanel / ComparisonDashboard / PosteriorPlot
   expands to 1000+ nodes per chart. Full-panel axe scans honestly took
   15-30s per test. App.test.tsx had a separate issue: no ResizeObserver
   stub in beforeEach on jsdom 28.
   
   Plan A per Opus extended-thinking diagnosis:
   - new app/frontend/src/test/recharts-stub.tsx — flat mock exporting
     plain <div>/null for every recharts symbol the codebase uses.
   - PosteriorPlot.test.tsx, a11y-results.test.tsx, a11y-comparison-
     dashboard.test.tsx import that stub via vi.mock; per-test timeout
     bumps (15000, 25000) removed; default 5000ms suffices.
   - PosteriorPlot.test.tsx test 2 asserts .recharts-area-area (real
     recharts markup). Moved to new PosteriorPlot.integration.test.tsx
     without the mock; original site now has it.skip with a TODO.
   - App.test.tsx beforeEach stubs ResizeObserver; the a11y test gains
     a second flushEffects() to settle zustand/i18n/draftStore init.
   
   color-contrast and all other wcag2aa rules preserved; no runOnly
   scoping added. A11y coverage unchanged in semantic intent, only the
   SVG-internal markup that was never the subject of those tests is
   removed from axe's scan.
   
   Closes the frontend suite red status noted in the 2026-04-23-cx-
   a11y-test-perf.md spec.
   ```
   
   После коммита — `git log --oneline -3` в отчёт.

6. **Push:**
   ```bash
   git push origin main
   ```

7. **Отметить статус CI** через `gh run list --branch main --limit 1` и убедиться что Tests workflow запустился. Дождаться заверешения (Tests обычно 3-5 мин). Если упал — вытащить relevant лог и приложить к отчёту. Если зелёный — `gh run view <id> --json conclusion,jobs` и приложить к отчёту.

## Acceptance
- `npm --prefix app/frontend run test -- --run` exit 0, **3 подряд** (flaky check). Каждый axe-тест завершается под 5000ms.
- `npx tsc --noEmit -p app/frontend/tsconfig.json` exit 0.
- `git log --oneline -3` показывает новый коммит поверх `07ae9b29`.
- CI run на `main` после push: все jobs зелёные (verify ubuntu + windows, docker, lighthouse, update-metrics-badges, Deploy docs если триггернётся).
- В worktree после push могут остаться несвязанные с Plan A изменения (демо-PNG regen от smoke, i18n side-effects) — их **не трогать**, не коммитить, не реверчить.
- Один коммит, не squashed из нескольких.

## Notes
- **Про multi-agent workspace.** В параллельной сессии может быть открыт smoke / verify / npm process — не убивать чужие процессы; если какой-то из path'ей (напр. `docs/demo/*.png`) меняется в ходе запуска тестов, это не моё. Работаем только с 6 файлами из п. 1.
- **Про hoisting vi.mock.** В модифицированных тест-файлах строка `vi.mock("recharts", () => import("./recharts-stub"))` стоит **до** `import { ... } from "vitest"`. Это корректно — vitest автоматически хостит `vi.mock()` вызовы на top файла перед любыми static import'ами. Не перемещать; если typecheck падает на "vi is undefined" — это ложная тревога от IDE, vitest-transform переписывает.
- **Если тесты всё равно падают** (особенно `a11y-results.test.tsx` на 5000ms default) — fallback из Opus'а Plan B: `view.container.cloneNode(true)` + удалить `svg, .recharts-wrapper` перед axe-scan. Не применять без обсуждения — вернуться с `axe-timing` measurements (перформанс.now вокруг axe()) и отчётом.
- **Отчёт** (15-20 строк): duration каждого из 4 ранее failing тестов (в ms), total suite duration до и после (ожидаю -40s минимум), commit hash, CI run id и conclusion, любые side-effect modifications, которые не трогал.
