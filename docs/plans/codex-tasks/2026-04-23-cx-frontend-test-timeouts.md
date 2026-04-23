# CX Task: Починить 3 timeout'а во frontend unit-тестах

## Goal
`npm --prefix app/frontend run test` падает красным из-за 3 tests, которые упираются в таймаут (не из-за содержательного expect failure). Остальные тесты и CI ubuntu-verify зелёные, так что баг не блокирующий — но подсветка "unit suite red" добавляет шум в каждом CX-таске и мешает использовать frontend-тесты как gate. Цель — разобраться с каждым таймаутом отдельно и сделать suite стабильно зелёным локально и в CI.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `1e8472b0` (после Tier 1 closure, все backend/verify/lighthouse зелёные).
- **Что падает** (Codex отчёт от 2026-04-23 при верификации data-testid контракта):
  - `app/frontend/src/App.test.tsx:814`
  - `app/frontend/src/components/PosteriorPlot.test.tsx:52`
  - `app/frontend/src/test/a11y-sidebar.test.tsx:168`
- **Важно.** Эти таймауты НЕ связаны с недавним data-testid рефакторингом. Один из тестов `a11y-sidebar.test.tsx` — compare controls с testid'ами — работает (`:272`, `"renders compare controls with stable test ids"`), это именно он запускался явно и был зелёным. Падают соседние тесты в тех же файлах.
- **Runner.** vitest 3.x + happy-dom (см. `app/frontend/vite.config.ts`), дефолтный `testTimeout` — 5000ms; возможно один из ранних CX-тасков этой сессии бампнул `testTimeout=30000` в worst-case режиме (`93a33a65 ci(frontend): force vitest testTimeout=30s`). Проверить текущий конфиг.
- **Не трогать** backend, e2e Playwright (`app/frontend/e2e/`), smoke скрипт, CI workflow.

## Deliverables

Для каждого из трёх тестов отдельный commit. Алгоритм per test:

1. **Воспроизвести локально в изоляции:**
   ```bash
   npm --prefix app/frontend run test -- src/App.test.tsx -t "<имя теста по номеру строки>" --reporter=verbose
   ```
   Посмотреть, какой `expect()` / `waitFor()` / `findBy*` зависает.
2. **Диагностировать корень** через один из трёх паттернов:
   - **Pattern A (fake timers race).** Тест использует `vi.useFakeTimers()` + реактный `useEffect`/setTimeout, и `await act(() => vi.runAllTimers())` не пропускает microtasks. Фикс: `vi.useFakeTimers({ shouldAdvanceTime: true })` или переход на `vi.useRealTimers()` в этом конкретном тесте.
   - **Pattern B (waitFor без expected shape).** `await waitFor(() => expect(screen.getByRole('...')))` падает не по таймауту expect'а, а потому что promise resolve происходит после teardown. Фикс: заменить на `await screen.findByRole(...)` (встроенный retry), убрать вложенный `waitFor`.
   - **Pattern C (unhandled promise from component).** Компонент делает `fetch()` / `i18next.changeLanguage()` / MSW handler, который не резолвится в happy-dom. Фикс: проверить, что MSW setup активен для теста (`app/frontend/src/test/setup.ts`), или мокнуть fetch явно через `vi.spyOn(global, 'fetch')`.
3. **Починить** — минимально invasive; не переписывать тест целиком, если можно подменить один хук / один waitFor / один timer-режим.
4. **Подтвердить** — `npm --prefix app/frontend run test -- <file>` теперь зелёный. Запустить 3 раза подряд, чтобы убедиться в отсутствии flakiness.

Если какой-то из тестов окажется fundamentally сломанным (тестирует состояние, которое больше не существует в компоненте после недавних рефакторов) — допустимо заменить на `describe.skip` с TODO-комментарием `// TODO(cleanup): test obsolete after <commit-ref>; rewrite or delete` и открыть отдельный мини-issue в плане, но **только** если 15 минут диагностики не дают воспроизведения в реальном user-flow. Skip — последний вариант, не первый.

## Acceptance
- `npm --prefix app/frontend run test` (без `-t`, весь suite) — exit 0, минимум 3 прогона подряд.
- Ни один тест не использует `vi.useFakeTimers()` без явного `vi.useRealTimers()` в `afterEach` / `afterAll` (чтобы fake timers не протекали в соседние тесты).
- `npx tsc --noEmit -p app/frontend/tsconfig.json` → 0 ошибок.
- 3 отдельных commit'а:
  - `fix(test): unstick App.test.tsx timeout at line 814`
  - `fix(test): unstick PosteriorPlot.test.tsx timeout at line 52`
  - `fix(test): unstick a11y-sidebar.test.tsx timeout at line 168`
- CI run на `main` после push: `verify` (оба) зелёный, lighthouse + update-metrics-badges зелёные. Tests badge должен отобразить реальный combined count (backend + frontend) — если после фикса frontend junit генерится корректно.

## Notes
- **Не снижать coverage / не выкидывать assertions** ради зелёного — это false completion. Если expect что-то проверял — сохранить намерение.
- Если находишь, что `testTimeout: 30000` в конфиге маскирует более быстрый баг — **не снижай глобальный timeout** как часть этой задачи; открой `// TODO` на тест, который действительно требует 30s, и оставь на будущее.
- В отчёте (10-15 строк) перечислить: для каждого теста — какой pattern (A/B/C), одна строка diff-сути фикса, количество подряд успешных прогонов.
