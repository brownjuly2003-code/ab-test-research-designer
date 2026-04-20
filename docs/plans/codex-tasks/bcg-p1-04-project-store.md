# T4: projectStore

**Phase:** BCG Phase 1
**Depends on:** T3 (analysisStore + draftStore работают)
**Effort:** ~4h (самая крупная миграция)

## Context

Перенос 850 строк логики из `useProjectManager.ts` в `src/stores/projectStore.ts`. Это самый большой stateful hook: проекты, health, diagnostics, history, revisions, comparison, API token, archive/restore, snapshot persistence.

Читать перед стартом:
- `app/frontend/src/hooks/useProjectManager.ts` — полный файл
- `src/hooks/useProjectManager.test.tsx` (479 стр) — все сценарии должны работать
- `app/frontend/src/lib/api.ts` — какие endpoints вызываются
- `BCG_plan.md` §1.2.5

## Goal

1. `src/stores/projectStore.ts` с полным API `useProjectManager`
2. Адаптировать тест
3. Удалить `useProjectManager.ts`
4. `App.tsx` работает на новом store

## Steps

### 1. Спроектировать store

Разделить внутри файла на секции (комментариями):
- **Projects:** `projects`, `activeProjectId`, `loadProject`, `saveProject`, `archiveProject`, `restoreProject`, `deleteProject`, `refreshProjects`
- **Backend state:** `health`, `diagnostics`, `refreshBackendState`, `apiToken`, `setApiToken`
- **History:** `history`, `loadHistory`, `loadMoreHistory`
- **Revisions:** `revisions`, `loadRevisions`, `restoreRevision`
- **Comparison:** `comparison`, `compareProjects`, `clearComparison`
- **Snapshot:** `persistAnalysisSnapshot`, `markDraftChanged`, `hasUnsavedChanges`, `dirtyState`

Весь API, который читал `App.tsx` через `projectManager.*` — должен работать идентично через `useProjectStore()`.

### 2. Реализовать `src/stores/projectStore.ts`

Перенос механический: `useState` → `set({ ... })`, `useEffect` — либо в init action (`refreshBackendState` вызывается из `App.tsx` при mount), либо триггерится явно.

API mocking: все вызовы остаются через `lib/api.ts`.

### 3. Адаптировать тест

`src/hooks/useProjectManager.test.tsx` → `src/stores/projectStore.test.ts`.

Сохранить ВСЕ ≥8 сценариев из T1. `beforeEach` сбрасывает state + localStorage.

### 4. Удалить hook

```bash
git rm app/frontend/src/hooks/useProjectManager.ts
```

Убедиться: `rg "useProjectManager" src` → пусто (кроме нового store, если он импортирует типы).

### 5. Обновить импорты в `App.tsx`

```ts
const projectManager = useProjectManager(...);  // было
const projectManager = useProjectStore();       // стало
```

Сайт-эффекты `useEffect` в `App.tsx` (refreshBackendState при mount) остаются в `App.tsx`, пока не переедут в T5.

### 6. Verify

```bash
cd app/frontend
npx vitest run src/stores
npx tsc --noEmit
npm run build
```

Ручная проверка (критично):
- Health indicator показывает статус
- API token вводится и сохраняется в session
- Save → Load → Archive → Restore → Delete флоу
- History и revisions подгружаются
- Compare two projects работает
- Draft dirty state отображается в sidebar

## Done When

- [ ] `src/stores/projectStore.ts` с полным API
- [ ] `src/stores/projectStore.test.ts` ≥ 8 тестов, зелёные
- [ ] `src/hooks/useProjectManager.ts` удалён
- [ ] `npx tsc --noEmit` = 0
- [ ] `npm run build` проходит
- [ ] Полный e2e flow вручную пройден

## Constraints

- API идентичен — `App.tsx` должен компилироваться с минимальной заменой `const projectManager = useProjectStore()`
- НЕ менять `lib/api.ts`
- НЕ трогать backend
- Если какой-то метод сложно перенести 1:1 — НЕ упрощать семантику, описать проблему в отчёте и дождаться ревью
