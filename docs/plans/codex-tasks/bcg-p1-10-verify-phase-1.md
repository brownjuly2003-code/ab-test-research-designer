# T10: Финальная верификация Phase 1

**Phase:** BCG Phase 1
**Depends on:** T9 (type safety pass)
**Effort:** ~1h

## Context

Последняя задача Phase 1. Проверить, что все цели из `archive/2026-04-23-bcg-planning-docs/BCG_plan.md` L186 (checkpoint Фаза 1) достигнуты, и запустить полный verify-pipeline.

## Goal

Подтвердить, что фронтенд готов к Phase 2 (UX Transformation).

## Steps

### 1. Чеклист из `archive/2026-04-23-bcg-planning-docs/BCG_plan.md` §1 checkpoint

Проверить по одному пункту:

```bash
cd app/frontend

# 1. App.tsx < 120 строк
wc -l src/App.tsx

# 2. ResultsPanel.tsx < 150 строк
wc -l src/components/ResultsPanel.tsx

# 3. 5 Zustand stores
ls src/stores/
# ожидается: themeStore, wizardStore, analysisStore, projectStore, draftStore + тесты

# 4. Старых hook-файлов нет
ls src/hooks/
# не должно быть useAnalysis.ts, useProjectManager.ts, useDraftPersistence.ts

# 5. Prop drilling убран
rg "wizardPanelProps|sidebarPanelProps" src/App.tsx
# пусто

# 6. TypeScript strict
npx tsc --noEmit

# 7. Все тесты
npx vitest run
```

### 2. Полный verify-pipeline

Из корня проекта:
```bash
cd D:\AB_TEST
cmd /c scripts\verify_all.cmd
```

Должны пройти:
- backend pytest
- frontend vitest
- typecheck
- build
- smoke (Playwright)

Если `--with-e2e` флаг поддерживается и важен — запустить:
```bash
cmd /c scripts\verify_all.cmd --with-e2e
```

### 3. Ручной e2e smoke-тест

Запустить `npm run dev` и пройти основной flow:
1. Fresh browser (или incognito) → onboarding показывается
2. Load template / ввести данные в wizard → Review → Run Analysis
3. Results — все 11 секций рендерятся (warnings, design, metrics, risks, sensitivity, power curve, SRM, observed, sequential, AI, comparison)
4. Save project → появляется в sidebar
5. Toggle theme → dark mode применяется
6. Reload страницы → draft восстановился
7. Load another project → Compare
8. Archive → Restore → Delete
9. Export Markdown + HTML

Всё должно работать.

### 4. Отчёт

Создать `D:\AB_TEST\docs\plans\2026-04-20-bcg-phase-1-report.md`:

```md
# BCG Phase 1 — Completion Report

Дата: YYYY-MM-DD

## Чеклист `archive/2026-04-23-bcg-planning-docs/BCG_plan.md` L186
- [x] App.tsx < 120 строк (фактически: NN)
- [x] ResultsPanel.tsx < 150 строк (фактически: NN)
- [x] 5 Zustand stores работают
- [x] Все тесты зелёные
- [x] `npx tsc --noEmit` = 0

## Метрики
- Строк кода: до / после по ключевым файлам
- Количество тестов: до / после
- Bundle size: `npm run build` output

## Известные проблемы / отложенное
- [...]

## Готовность к Phase 2
Да/Нет + обоснование
```

### 5. Verify отчёта

```bash
ls D:\AB_TEST\docs\plans\2026-04-20-bcg-phase-1-report.md
```

## Done When

- [ ] Чеклист из BCG L186 пройден полностью
- [ ] `scripts\verify_all.cmd` прошёл без ошибок
- [ ] Ручной e2e smoke-тест пройден
- [ ] Отчёт создан

## Constraints

- Если какой-то пункт чеклиста не выполнен — НЕ закрывать Phase 1, вернуться к соответствующей T-задаче
- Отчёт — сухой, фактический. Без маркетинговых формулировок.
