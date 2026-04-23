# CX Task: Диагностировать и починить >30s axe() таймауты в a11y-*.test.tsx

## Goal
`npm --prefix app/frontend run test` падает на 4 тестах в 3 файлах с `Error: Test timed out in 30000ms`:
- `src/App.test.tsx:829` ("persists the selected theme..." — один из них)
- `src/components/PosteriorPlot.test.tsx:67` ("credibility interval heading")
- `src/test/a11y-comparison-dashboard.test.tsx:58`
- `src/test/a11y-results.test.tsx:74`

Предыдущая попытка починить (uncommitted worktree-drift на 2026-04-23, до-HEAD `f920ecdb`) применила два shortcut-паттерна:
1. Отключила `color-contrast` axe-rule во всех 4 a11y-файлах (`rules: { "color-contrast": { enabled: false } }`).
2. Бампнула per-test timeout'ы: 15000→25000 (PosteriorPlot), 15000→20000 (a11y-comparison).

Оба паттерна — **false completion**: a11y-coverage понижен, тесты всё равно падали по 30s на a11y-results и a11y-comparison (20000/по-умолчанию <30s).

Цель — починить **правильно**: разобраться, ПОЧЕМУ `axe()` на эти компоненты занимает >30s, устранить root cause, вернуть `color-contrast` rule, оставить реальные per-test timeout'ы в пределах 15-20s.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `f920ecdb` (после де/es translation + HF snapshot landed).
- **Runner.** vitest 3.x + happy-dom (см. `app/frontend/vite.config.ts`). axe-core версия — из `package.json`.
- **Почему важно.** Unit suite сейчас запускается красным локально (CI его не бьёт через scripts/verify_all.py, но любой `npm test` для dev красен). Это мешает использовать unit tests как dev-gate.
- **НЕ трогать** backend, CI workflow, smoke, e2e Playwright, snapshot_service tests, translation тесты.

## Hypotheses (проверить в указанном порядке, не угадывать)

### Hypothesis A — axe() rule set слишком большой для большого DOM
axe default запускает ~60 rules. Некоторые (`color-contrast`, `nested-interactive`, `aria-valid-attr-value`) делают O(n²) обход. Если `ResultsPanel` / `ComparisonDashboard` рендерят 100+ элементов, каждый rule бегает секунды.

**Проверить:** в одном из failing тестов временно:
```js
const results = await axe(view.container, {
  rules: Object.fromEntries(
    ['color-contrast','nested-interactive','aria-valid-attr-value','aria-required-children','aria-required-parent']
      .map(r => [r, { enabled: false }])
  )
});
```
Если тест начинает проходить за <5s — нашли виновника (будут данные, кого именно отключать).

### Hypothesis B — axe() ждёт ResizeObserver / IntersectionObserver / chart render
Tests стабают `ResizeObserver`/`fetch` в `beforeEach`. Если компонент внутри делает animation frame / setTimeout / async chart paint, `axe()` ждёт их. Возможно, happy-dom не триггерит resolved promises без явного `await flushEffects()` N раз.

**Проверить:** добавить 3-й / 4-й `await flushEffects()` перед `axe()`; логнуть `performance.now()` до и после `axe()`; если разница >>1s — значит axe сам медленный, не ожидание.

### Hypothesis C — Recharts / D3 mount bottleneck
`PosteriorPlot`, `PowerCurveSection` внутри ResultsPanel, `ComparisonDashboard` — все используют recharts / svg. Рендер большой SVG с axis labels + gridlines заставляет axe-core обходить сотни нод.

**Проверить:** рендерить компонент с стаб-реализацией chart (`vi.mock('recharts', ...)` → возврат пустого div). Если тест зелёный — значит рендер charts и есть корень, и либо мокать их в a11y тестах, либо ограничивать axe-обход через `include: ['[data-testid=accessible-region]']` (scope axe только на ключевые areas).

## Deliverables

### Шаг 1: Диагностика (обязательно, отдельный коммит, может быть revertable)
Выбрать ОДИН failing тест (рекомендую `a11y-results.test.tsx:74` — самый чёткий слом). Добавить telemetry:
```ts
const t0 = performance.now();
const results = await axe(view.container);
console.log(`[axe-timing] ${view.container.children.length} root kids, ${view.container.querySelectorAll('*').length} total descendants, axe took ${(performance.now()-t0).toFixed(0)}ms`);
```
Запустить `npm --prefix app/frontend run test -- src/test/a11y-results.test.tsx`. Скопировать лог в отчёт.

Если `axe took > 15000ms` → виновник медленные rule'ы или огромный DOM; идём в Hypothesis A / C.
Если `axe took < 5000ms`, но всё равно timeout → виновник не axe, а render / useEffect / fetch; идём в Hypothesis B.

### Шаг 2: Фикс по диагнозу

**Если Hypothesis A подтвердилась** → ограничить axe runOnly к actionable rules:
```ts
const results = await axe(view.container, {
  runOnly: {
    type: 'tag',
    values: ['wcag2a', 'wcag2aa']  // без experimental / best-practice
  }
});
```
Это идиоматичный способ ускорить axe без отключения конкретных rules. Если `wcag2aa` всё ещё слишком дорог — попробовать `wcag2a` только.

**Если Hypothesis B подтвердилась** → идентифицировать зависший promise (через `vi.runAllTimers()` после render или через `waitFor(() => screen.getByRole('...'))`). Починить per-test, не глобально.

**Если Hypothesis C подтвердилась** → добавить `vi.mock('recharts', ...)` в `beforeAll` конкретного файла, возвращать плоские div-ы вместо SVG. Альтернатива: сузить axe-скан через `include:`:
```ts
const results = await axe(view.container.querySelector('[role="region"]'));
```

### Шаг 3: Удалить телеметрию из Шага 1 (отдельный коммит)

### Шаг 4: Восстановить coverage
- Вернуть `color-contrast` в axe rules (если после фикса axe быстрый, эта rule больше не проблема).
- Вернуть реальные per-test timeout'ы: 15000ms должно хватать на любой a11y тест после фикса. Если какому-то тесту всё ещё нужно >15s — это сигнал неоптимального DOM, открыть issue, не ставить 30s.

### Шаг 5: Полный прогон
- `npm --prefix app/frontend run test` → exit 0, 3 прогона подряд.
- `npm --prefix app/frontend run test -- --reporter=verbose` — показать в отчёте топ-5 самых медленных тестов с их длительностью.
- `npx tsc --noEmit -p app/frontend/tsconfig.json` → 0 ошибок.

## Acceptance
- Все 4 failing теста зелёные.
- Никакой axe rule не отключён глобально через `color-contrast` exception — либо проблема сведена через `runOnly: wcag2a|wcag2aa`, либо зафикшена в компоненте.
- Максимальный per-test timeout в a11y-*.test.tsx и PosteriorPlot.test.tsx ≤ 20000ms (сейчас был 25000-30000). Если какой-то требует больше — TODO в тесте с объяснением.
- Unit suite стабильно зелёный: 3 подряд `npm run test` без flakies.
- Коммиты:
  - (опц.) `test(a11y): temporary axe timing telemetry to locate slow tests`
  - `fix(test): unstick a11y axe timeouts by scoping to WCAG AA rules` (или аналогично под найденный root cause)
  - `test(a11y): restore color-contrast axe coverage after perf fix`
  - (опц.) `test: remove axe timing telemetry after a11y perf fix`

## Notes
- **НЕ возвращать** shortcut'ы: `{rules: { "color-contrast": { enabled: false } }}` в axe-options без reason'а из диагностики — это false completion.
- **НЕ бампить** per-test timeout'ы до 30000 как workaround — если axe реально требует 30s на маленькой RTL-комненте, это индикатор бага в компоненте, не теста.
- В финальном отчёте (15-20 строк): какая гипотеза подтвердилась, axe-timing до / после (ms), список тестов с изменённой стратегией (runOnly vs scoped-container vs mocked-recharts), 3 подряд green run duration.
- Если 2 часа диагностики не дают ясного root cause — остановиться, вернуться с отчётом и данными, **не** shortcut'ить через disable.
