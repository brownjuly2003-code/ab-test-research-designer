# T3: analysisStore + draftStore

**Phase:** BCG Phase 1
**Depends on:** T2 (Zustand установлен, themeStore/wizardStore работают)
**Effort:** ~3h

## Context

Перенос логики из `useAnalysis.ts` (181 стр) и `useDraftPersistence.ts` (170 стр) в Zustand stores. Hook-файлы удаляются, но ПУБЛИЧНЫЙ КОНТРАКТ (имена методов и полей) сохраняется 1:1 для плавной миграции `App.tsx` в T5.

Читать перед стартом:
- `app/frontend/src/hooks/useAnalysis.ts` — полный файл
- `app/frontend/src/hooks/useDraftPersistence.ts` — полный файл
- `src/hooks/useAnalysis.test.tsx` — все сценарии должны продолжать работать
- `src/hooks/useDraftPersistence.test.tsx`
- `BCG_plan.md` §1.2.4, §1.2.6

## Goal

1. `src/stores/analysisStore.ts` с тем же API что у `useAnalysis`
2. `src/stores/draftStore.ts` с тем же API что у `useDraftPersistence`
3. Удалить старые hook-файлы
4. Адаптировать тесты под stores
5. `App.tsx` продолжает работать (временно через `useAnalysisStore` и `useDraftStore` вместо хуков)

## Steps

### 1. `src/stores/analysisStore.ts`

Перенести ВСЕ поля и методы из `useAnalysis`:
- state: `results`, `isAnalyzing`, `analysisError`, `statusMessage`, `validationErrors`
- actions: `runAnalysis`, `clearAnalysis`, `invalidateResults`, `showStatus`, `showError`, `clearFeedback`, `validateDraft`, `ensureValidForm`, `linkResultToProject`, `getPersistableAnalysis`

Сохранить семантику: status и error взаимоисключающи (setError чистит status, setStatus чистит error).

`runAnalysis` — async, вызывает `requestAnalysis` из `lib/api`. Оставить текущую обработку ошибок и retry логику (если есть).

### 2. `src/stores/draftStore.ts`

Перенести из `useDraftPersistence`:
- state: `draft`, `draftStorageWarning`
- actions: `readDraftBootstrap`, `replaceDraft`, `resetDraft`, `updateDraftField`, `parseImportedDraftText`, `clearStorageWarning`

Persist: localStorage ключ `ab-test:draft:v1`. При quota exceeded — ставить `draftStorageWarning` вместо throw.

### 3. Миграция тестов

Переименовать:
- `src/hooks/useAnalysis.test.tsx` → `src/stores/analysisStore.test.ts`
- `src/hooks/useDraftPersistence.test.tsx` → `src/stores/draftStore.test.ts`

Адаптировать: вместо `renderIntoDocument` и `act` — прямые вызовы `useAnalysisStore.getState().runAnalysis(...)` и проверки через `useAnalysisStore.getState()`. `beforeEach` сбрасывает состояние.

Все сценарии из T1 должны пройти.

### 4. Удалить старые файлы

```bash
git rm app/frontend/src/hooks/useAnalysis.ts app/frontend/src/hooks/useDraftPersistence.ts
```

Убедиться, что НИКТО в codebase не импортирует эти файлы (`rg "from ['\"].*useAnalysis['\"]" src` → пусто).

### 5. Обновить импорты

В `App.tsx` (и везде, где использовались хуки):
```ts
// было
const analysis = useAnalysis(draft);
// стало
const analysis = useAnalysisStore();
```

Если API store-а идентичен хуку — замена механическая. Если разошлось (например, хук принимал `draft` параметром, а store читает из `useDraftStore`) — описать в отчёте.

### 6. Verify

```bash
cd app/frontend
npx vitest run src/stores src/components
npx tsc --noEmit
npm run build
```

Ручная проверка: `npm run dev` → заполнить wizard → Run Analysis → результаты отображаются → draft сохраняется при reload.

## Done When

- [ ] `src/stores/analysisStore.ts` + `.test.ts` (≥ 5 тестов, все зелёные)
- [ ] `src/stores/draftStore.ts` + `.test.ts` (≥ 6 тестов, все зелёные)
- [ ] `src/hooks/useAnalysis.ts`, `src/hooks/useDraftPersistence.ts` удалены
- [ ] Публичный контракт совпадает (те же имена методов и полей)
- [ ] `npx tsc --noEmit` = 0 ошибок
- [ ] `npm run build` проходит
- [ ] Ручной e2e flow работает

## Constraints

- НЕ менять `useProjectManager` — это T4
- Семантика status/error взаимоисключения сохраняется
- Все существующие тесты из T1 должны пройти после миграции (возможно с минимальной переработкой вызовов)
