# T2: Zustand + themeStore + wizardStore

**Phase:** BCG Phase 1
**Depends on:** T1 (safety-net тесты зелёные)
**Effort:** ~2h

## Context

Первый шаг миграции state с `useState` в `App.tsx` на Zustand. Начинаем с самых простых стейтов — theme и wizard navigation. Цель — положить seam, не ломая `App.tsx`.

Читать перед стартом:
- `app/frontend/src/App.tsx` (487 стр) — строки с `theme`, `step`, `showOnboarding`, `importingDraft`
- `BCG_plan.md` §1.2.1-1.2.3

## Goal

1. Установить Zustand
2. Создать `themeStore` (theme + localStorage sync)
3. Создать `wizardStore` (step + onboarding + importingDraft)
4. В `App.tsx` заменить соответствующий `useState` на эти stores
5. Остальной state (`useAnalysis`, `useProjectManager`, `useDraftPersistence`) НЕ трогать

## Steps

### 1. Установить Zustand

```bash
cd app/frontend
npm i zustand
```

Проверить `package.json`: `"zustand": "^5.x"` в `dependencies` (НЕ devDependencies).

### 2. Создать `src/stores/themeStore.ts`

Перенести логику theme из `App.tsx`:
- state: `theme: "light" | "dark"`
- action: `setTheme(theme)`, `toggleTheme()`
- persist: localStorage ключ `ab-test:theme`
- initial: читать localStorage, fallback `"light"`
- side effect: при смене — применять `document.documentElement.dataset.theme = theme`

Интерфейс:
```ts
export type Theme = "light" | "dark";
export interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}
export const useThemeStore: () => ThemeState;
```

### 3. Создать `src/stores/wizardStore.ts`

Перенести:
- state: `step: number`, `showOnboarding: boolean`, `importingDraft: boolean`
- actions: `setStep`, `setShowOnboarding`, `setImportingDraft`, `openWizard()` (сброс step в 0, закрытие onboarding)

Onboarding persist: localStorage ключ `ab-test:onboarding-seen` (boolean). Если true → `showOnboarding = false` при старте.

### 4. Тесты

Создать:
- `src/stores/themeStore.test.ts` — set/toggle, localStorage persist, initial из localStorage
- `src/stores/wizardStore.test.ts` — setStep, openWizard сброс, onboarding persist

Использовать `beforeEach(() => { localStorage.clear(); useThemeStore.setState(initialState); })` для изоляции.

### 5. Интегрировать в `App.tsx`

- Удалить `useState` для theme/step/showOnboarding/importingDraft
- Заменить на `const { theme, setTheme } = useThemeStore()` и т.д.
- Проверить: theme applies к `<html data-theme>`, onboarding показывается первый раз, wizard navigation работает

### 6. Verify

```bash
cd app/frontend
npm ls zustand
npx vitest run
npx tsc --noEmit
npm run build
```

Все команды без ошибок. Ручная проверка: `npm run dev` → toggle theme, onboarding first-visit, step navigation.

## Done When

- [ ] `zustand` в `dependencies`
- [ ] `src/stores/themeStore.ts` + `.test.ts` (≥ 3 теста)
- [ ] `src/stores/wizardStore.ts` + `.test.ts` (≥ 3 теста)
- [ ] `App.tsx` использует stores вместо useState для theme/step/onboarding/importingDraft
- [ ] `npx vitest run` и `npm run build` зелёные
- [ ] Ручная UI-проверка пройдена

## Constraints

- НЕ трогать `useAnalysis`, `useProjectManager`, `useDraftPersistence` в T2
- НЕ создавать `analysisStore`/`projectStore`/`draftStore` — это T3-T4
- `App.tsx` остаётся функциональным, НО размер ещё не нужно резать до 120 стр — это T5
