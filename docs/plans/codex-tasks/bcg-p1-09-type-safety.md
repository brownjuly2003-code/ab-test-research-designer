# T9: Type safety pass

**Phase:** BCG Phase 1
**Depends on:** T8 (CSS унифицирован)
**Effort:** ~1.5h

## Context

Финальная фаза — закрыть type-safety дыры после всех рефакторингов.

Читать:
- `BCG_plan.md` §1.6.1-1.6.2

## Goal

- String-matching заменить на enum-типы
- Убрать `as`-assertions
- `npx tsc --noEmit` — 0 ошибок (должно быть уже)

## Steps

### 1. Toast type — явный enum

`src/components/ToastSystem.tsx` (или где живёт `resolveStatusToastType`):
- Было: функция, которая ищет подстроку в сообщении и возвращает `"error" | "warning" | "success" | "info"`
- Стало: вызывающий код явно передаёт `ToastType`

Тип уже должен быть:
```ts
export type ToastType = "success" | "error" | "warning" | "info";
```

Обновить все места вызова (`analysisStore.showStatus`, `showError` и т.д.) — пусть принимают `type: ToastType` параметром.

Удалить функцию `resolveStatusToastType` если она больше не нужна.

### 2. `draftStorageWarning` — явный enum

В `draftStore` сейчас warning определяется через `startsWith("Storage full")`. Заменить:

```ts
export type StorageWarningLevel = "full" | "nearFull" | "cleared" | null;

interface DraftState {
  draftStorageWarning: StorageWarningLevel;
  draftStorageMessage: string | null;  // human-readable, если нужно показать
}
```

UI-компоненты проверяют `level`, не строку.

### 3. Убрать `as` assertions

```bash
rg " as " src --type ts --type tsx -n
```

Для каждого найти:
- Если это narrowing типа — заменить на type guard или `satisfies`
- Если это фикстура тестовая — использовать `satisfies`
- Если это `as const` — оставить (это OK)
- Если есть `sampleProject as Parameters<typeof hydrateLoadedPayload>[0]` — типизировать `sample-project.json` через `satisfies ExperimentDraft` в импорте

Оставить только осознанные случаи, где `as` действительно необходим (например, `as unknown as X` для тестовых моков). Их заком ментировать одной строкой: `// as needed because X`.

### 4. strict mode проверка

В `tsconfig.json`: `"strict": true` должен быть включён (ожидается, что уже). Проверить:
```bash
grep '"strict"' tsconfig.json
```

Если не `true` — включить. Если появились ошибки — исправить.

### 5. Verify

```bash
cd app/frontend
npx tsc --noEmit  # 0 ошибок
rg " as " src --type ts --type tsx -n | wc -l  # сократилось
npx vitest run
npm run build
```

## Done When

- [ ] `ToastType` используется явно, `resolveStatusToastType` удалён (или сильно упрощён)
- [ ] `StorageWarningLevel` enum-тип используется вместо string-matching
- [ ] Количество `as` в `src/*.ts, *.tsx` заметно сократилось (осознанные случаи прокомментированы)
- [ ] `npx tsc --noEmit` — 0 ошибок
- [ ] `strict: true` в tsconfig
- [ ] Все тесты зелёные

## Constraints

- Не менять публичные API сторов — только внутренние типы
- Не менять сигнатуры API endpoints (бэкенд не трогаем)
