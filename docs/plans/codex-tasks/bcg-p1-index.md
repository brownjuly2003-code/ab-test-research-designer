# BCG Phase 1 — CX Tasks Index

**Source plan:** `docs/plans/2026-04-20-bcg-phase-1.md`
**Dates:** 2026-04-20 onwards
**Execution mode:** строго последовательно, один CX-батч на задачу, review перед следующей

## Sequence

| # | Task | Depends on | Effort | Key verify |
|---|------|------------|--------|------------|
| T1 | [Audit hook tests](bcg-p1-01-audit-hook-tests.md) | — | 1.5h | все hook-тесты зелёные, пробелы BCG 1.1 закрыты |
| T2 | [Zustand + theme/wizard stores](bcg-p1-02-zustand-theme-wizard.md) | T1 | 2h | theme и wizard навигация на stores |
| T3 | [analysisStore + draftStore](bcg-p1-03-analysis-draft-stores.md) | T2 | 3h | старые hook-файлы удалены |
| T4 | [projectStore](bcg-p1-04-project-store.md) | T3 | 4h | полный API projectManager на store |
| T5 | [App.tsx refactor](bcg-p1-05-app-refactor.md) | T4 | 3h | App.tsx < 120 стр, prop drilling убран |
| T6 | [ResultsPanel декомпозиция](bcg-p1-06-results-decompose.md) | T5 | 4h | 11 секций, ResultsPanel < 150 стр |
| T7 | [Error Boundaries](bcg-p1-07-error-boundaries.md) | T6 | 1.5h | ErrorBoundary + ChartErrorBoundary |
| T8 | [CSS унификация](bcg-p1-08-css-unify.md) | T7 | 2h | layout/components/utilities + CSS Modules |
| T9 | [Type safety pass](bcg-p1-09-type-safety.md) | T8 | 1.5h | enum вместо string-matching, нет `as` |
| T10 | [Финальная верификация](bcg-p1-10-verify-phase-1.md) | T9 | 1h | verify_all.cmd + отчёт |

**Total effort:** ~23.5h (≈3 рабочих дня чистого времени)

## Правила

- **Без параллели.** Каждая T задача — отдельный CX-батч. Code review после каждой.
- **Тесты — контракт.** Все существующие backend + frontend тесты проходят на каждом шаге.
- **Если застряли.** После 2 неудачных попыток остановиться, откатить изменения, пересмотреть подход.
- **Отчёт после каждой задачи.** CX возвращает: что изменено (файлы, строки), что проверено (команды + вывод), что осталось.

## Прогресс

- [ ] T1
- [ ] T2
- [ ] T3
- [ ] T4
- [ ] T5
- [ ] T6
- [ ] T7
- [ ] T8
- [ ] T9
- [ ] T10
