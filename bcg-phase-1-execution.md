# BCG Phase 1 Execution

## Goal
Довести фронтенд до безопасного Phase 1 baseline из `BCG_plan.md`: сначала закрыть тестовые пробелы и стабилизировать текущие хуки, затем переходить к миграции состояния и декомпозиции крупных компонентов.

## Tasks
- [ ] Зафиксировать baseline фронтенда и рабочую область: проверить текущий dirty state, прогнать целевые frontend-тесты и определить, какие пункты `BCG_plan.md` уже частично реализованы. Verify: есть список ближайших задач и команды проверки для фронтенда.
- [ ] Закрыть пробел по safety-net тестам для `useAnalysis`, `useDraftPersistence`, `useProjectManager` без изменения их публичных контрактов. Verify: `npx vitest run src/hooks/useAnalysis.test.tsx src/hooks/useDraftPersistence.test.tsx src/hooks/useProjectManager.test.tsx`.
- [ ] Нормализовать feedback semantics в `useAnalysis`: статус и ошибка не должны жить одновременно, а persistable snapshot должен оставаться детерминированным. Verify: новые hook-тесты зелёные и `App.test.tsx` не теряет текущие сценарии анализа.
- [ ] После стабилизации хуков ввести store seam для миграции: сначала `analysis`/`draft`, затем `project`/`wizard`, без переписывания `App.tsx` целиком за один шаг. Verify: `App.tsx` читает state/actions из новых store-adapter слоёв, а старые тесты продолжают проходить.
- [ ] Уменьшить orchestration pressure в `App.tsx`: вытащить prop-heavy связки в компоненты/сторы, не ломая текущую UX-логику. Verify: `rg -n "wizardPanelProps|sidebarPanelProps" src/App.tsx` не находит старые большие prop-объекты.
- [ ] Разрезать `ResultsPanel.tsx` на секции по BCG critical path: сначала sensitivity, observed results, SRM, warnings, потом остальные блоки. Verify: `ResultsPanel.tsx` становится thin orchestrator, а выделенные секции покрываются существующими или новыми unit-тестами.
- [ ] Добавить error boundaries и финальный type-safety pass после декомпозиции, а не раньше. Verify: `npx tsc --noEmit` и `npx vitest run` проходят, авария в chart/result section не роняет весь layout.

## Done When
- [ ] Missing hook tests из начала `BCG_plan.md` существуют и зелёные.
- [ ] `useAnalysis` стабилен по TDD и не держит конфликтующие feedback states.
- [ ] Есть безопасный вход в store migration без полного переписывания фронтенда за одну итерацию.

## Notes
Текущий репозиторий уже содержит большой незавершённый набор изменений, поэтому реализация идёт через узкие, проверяемые итерации: сначала safety-net и стабилизация контрактов, потом структурный рефакторинг.
