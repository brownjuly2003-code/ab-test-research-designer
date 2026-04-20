# T5: App.tsx refactor → <120 строк

**Phase:** BCG Phase 1
**Depends on:** T4 (все 5 stores: theme, wizard, analysis, project, draft)
**Effort:** ~3h

## Context

После T2-T4 `App.tsx` всё ещё большой (≈487 стр) потому что:
1. Собирает объекты `wizardPanelProps` (≈30 полей) и `sidebarPanelProps` (≈50 полей) и передаёт их в дочерние компоненты
2. Содержит orchestration: keyboard shortcuts, side effects, toasts, onboarding

Цель T5: `App.tsx` становится тонким shell — layout + роутинг + keyboard shortcuts. Дочерние компоненты читают из stores напрямую.

Читать:
- `app/frontend/src/App.tsx`
- `src/components/WizardPanel.tsx`
- `src/components/SidebarPanel.tsx` (994 стр)
- `BCG_plan.md` §1.2.7, §1.2.8

## Goal

- `App.tsx` < 120 строк
- `WizardPanel` и `SidebarPanel` читают stores напрямую, prop drilling убран
- `rg "wizardPanelProps|sidebarPanelProps" src/App.tsx` → пусто
- Все существующие тесты зелёные

## Steps

### 1. Аудит `App.tsx`

Составить список того, что остаётся в `App.tsx`:
- Layout (`<div className="page">`, grid)
- Theme initialization side effect (применение `data-theme`)
- Keyboard shortcuts (Ctrl+S для save и т.п.)
- Top-level routing (если есть)
- Backend state bootstrap (первый `refreshBackendState` при mount)
- ErrorBoundary wrappers (будут в T7 — пока оставить слот)

Всё остальное — в компоненты.

### 2. `WizardPanel.tsx` — убрать пропсы

- Было: `<WizardPanel step={step} draft={draft} onDraftChange={...} onAnalyze={...} ... />`
- Стало: `<WizardPanel />` — внутри использует `useWizardStore()`, `useDraftStore()`, `useAnalysisStore()`

Оставить только UI-специфичные пропсы (например, `className`), если такие были.

### 3. `SidebarPanel.tsx` — то же самое

Убрать ≈50 пропсов. Компонент читает из `useProjectStore()`, `useWizardStore()`, `useDraftStore()`.

### 4. Keyboard shortcuts — оставить в `App.tsx`

Если были — оставить, они завязаны на top-level. Вызывать actions через `useProjectStore.getState().saveProject()`.

### 5. Side effects (toasts, onboarding timers)

Перенести в соответствующие stores (через `subscribe` middleware) либо в dedicated компонент `<GlobalSideEffects />` который `App.tsx` рендерит.

### 6. Тесты

- Если есть `App.test.tsx` — обновить под новый размер и stores
- Убедиться, что `WizardPanel.test.tsx` и `SidebarPanel.test.tsx` (если есть) тоже обновлены под минимальные пропсы

### 7. Verify

```bash
cd app/frontend
wc -l src/App.tsx  # < 120
rg "wizardPanelProps|sidebarPanelProps" src/App.tsx  # пусто
npx vitest run
npx tsc --noEmit
npm run build
```

Полный e2e flow:
- Новый проект → wizard → Run Analysis → Save → Load → Archive → Restore
- Theme toggle
- Onboarding показывается первый раз
- Keyboard shortcuts работают

## Done When

- [ ] `wc -l src/App.tsx` даёт число < 120
- [ ] `rg "wizardPanelProps|sidebarPanelProps" src/App.tsx` пусто
- [ ] `WizardPanel` и `SidebarPanel` принимают 0-3 UI пропса, остальное читают из stores
- [ ] Все frontend тесты зелёные
- [ ] Полный e2e flow работает вручную

## Constraints

- НЕ разрезать `SidebarPanel` на подкомпоненты (это BCG §2.2.1, не Phase 1)
- НЕ трогать `ResultsPanel` — это T6
- Если какой-то prop передавался из-за циклической зависимости stores — описать в отчёте, не хакать
