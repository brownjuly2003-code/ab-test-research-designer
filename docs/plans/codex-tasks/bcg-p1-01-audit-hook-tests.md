# T1: Аудит hook-тестов против BCG 1.1

**Phase:** BCG Phase 1 (Foundation Fix)
**Depends on:** nothing
**Effort:** ~1.5h

## Context

Hook-тесты уже существуют:
- `app/frontend/src/hooks/useAnalysis.test.tsx` (292 стр)
- `app/frontend/src/hooks/useProjectManager.test.tsx` (479 стр)
- `app/frontend/src/hooks/useDraftPersistence.test.tsx` (194 стр)

BCG план (`archive/2026-04-23-bcg-planning-docs/BCG_plan.md` §1.1) требует закрытия конкретных сценариев. Нужно сверить существующие тесты с чек-листом и дописать недостающее БЕЗ изменения публичных контрактов хуков — это safety-net перед миграцией на Zustand.

## Goal

Убедиться, что каждый сценарий из BCG 1.1.1-1.1.4 покрыт. Дописать отсутствующие тесты. Ничего в самих хуках не трогать.

## Steps

### 1. Сверить `useAnalysis.test.tsx` с BCG 1.1.1

Должны быть покрыты:
- `runAnalysis` happy path (binary + continuous)
- `clearAnalysis`
- `invalidateResults`
- `validateDraft` с ошибками валидации
- `showStatus`/`showError` toggle (status и error не живут одновременно)
- persistable snapshot детерминированный (одинаковый вход → одинаковый выход)

Если чего-то нет — дописать.

### 2. Сверить `useProjectManager.test.tsx` с BCG 1.1.2

Должны быть покрыты:
- `refreshBackendState` (health + diagnostics)
- `saveProject` — новый проект
- `saveProject` — обновление существующего (dirty state clearing)
- `loadProject` (с историей и snapshot'ом)
- `archiveProject` + `restoreProject`
- `markDraftChanged` / `hasUnsavedChanges`
- `persistAnalysisSnapshot` (после первого save)

Моки: `lib/api.ts` функции (уже протестированы в `api.test.ts`).

### 3. Сверить `useDraftPersistence.test.tsx` с BCG 1.1.3

Должны быть покрыты:
- `readDraftBootstrap` — localStorage пустой
- `readDraftBootstrap` — localStorage с валидными данными
- `readDraftBootstrap` — corrupted JSON (fallback на initial state)
- `replaceDraft`, `resetDraft`
- `parseImportedDraftText` — valid JSON
- `parseImportedDraftText` — invalid JSON (ошибка)
- `draftStorageWarning` при quota exceeded

### 4. Snapshot-тесты для WizardPanel и WizardReviewStep (BCG 1.1.4)

Проверить наличие файлов `WizardPanel.test.tsx` и `WizardReviewStep.test.tsx` с render-тестами на типовые пропсы. Если нет — создать минимальный render + `toMatchSnapshot()` с 1-2 типовыми наборами пропсов.

### 5. Verify

```bash
cd app/frontend
npx vitest run src/hooks src/components/WizardPanel.test.tsx src/components/WizardReviewStep.test.tsx
```

Все тесты зелёные. Покрытие:
- `useAnalysis`: ≥ 5 тестов
- `useProjectManager`: ≥ 8 тестов
- `useDraftPersistence`: ≥ 6 тестов
- `WizardPanel` + `WizardReviewStep`: по ≥ 1 snapshot-тесту

### 6. Отчёт

В конце: список добавленных тестов (имена + что проверяют). Если в существующих тестах найдены пробелы в проверке контракта (например, не проверяется что status и error взаимоисключающи) — отдельно отметить в отчёте.

## Done When

- [ ] Все 4 чек-листа (1.1.1-1.1.4) покрыты
- [ ] `npx vitest run` зелёный без падений/skip
- [ ] Публичные контракты хуков не изменены (`git diff src/hooks/*.ts` — пусто, только `*.test.tsx` затронуты)
- [ ] Backend pytest не запускался — изменений в backend нет

## Constraints

- НЕ менять `useAnalysis.ts`, `useProjectManager.ts`, `useDraftPersistence.ts`
- НЕ добавлять новые dev-зависимости
- НЕ рефакторить существующие тесты, если они проходят — только дописывать недостающие
