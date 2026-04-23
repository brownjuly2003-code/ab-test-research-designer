# CX Task: Sync `archive/2026-04-23-bcg-planning-docs/BCG_plan.md` и старые phase-report чекбоксы с реальным состоянием

## Goal
Привести `D:\AB_TEST\archive\2026-04-23-bcg-planning-docs\BCG_plan.md` и `docs\plans\2026-04-20-bcg-phase-1-report.md` в соответствие с фактом: отметить `[x]` то, что реально сделано в landed коммитах с `8413328e` по `v1.0.0`. Чтобы reader не думал, что 73 пункта открыты.

## Context
- Репо: `D:\AB_TEST\`, `main`, HEAD после tag `v1.0.0`. Не создавать ветку, не пушить.
- `archive/2026-04-23-bcg-planning-docs/BCG_plan.md`: `grep -c "^- \[ \]" archive/2026-04-23-bcg-planning-docs/BCG_plan.md` = 73 нез-отмеченных, 0 отмеченных. Фактически Phase 1, 2, 3 полностью landed.
- `docs\plans\2026-04-20-bcg-phase-1-report.md`: в разделе «Чеклист archive/2026-04-23-bcg-planning-docs/BCG_plan.md L186» перечислены блокеры с `[ ]`, которые устранены 2026-04-21 (api-contract regen, UI 422 bug, smoke/e2e sync).
- Verify на HEAD сейчас зелёный. Этот таск — docs-only, тесты не трогаются.
- Не удалять пункты, не переформулировать их — только менять `[ ]` на `[x]` + при необходимости добавлять inline-ссылку на коммит (`(landed in 8413328e)`).

## Deliverables
1. **`archive/2026-04-23-bcg-planning-docs/BCG_plan.md`**:
   - Для каждого `- [ ] **N.N.N** ...` проверить: landed ли?
   - Критерий landed: тест проходит (`grep` в `git log` соответствующую функциональность), или файл существует (`ls app/frontend/src/stores/`), или строка длины/метрика достигнута (`wc -l App.tsx ResultsPanel.tsx`).
   - Если landed → `[ ]` → `[x]`, добавить `(landed in <commit-7>)` где понятно из какого коммита.
   - Если частично (например, i18n scaffold есть, но react-i18next не интегрирован) → оставить `[ ]`, добавить inline комментарий `(partial: scaffold only)`.
   - Если не начато → оставить `[ ]` как есть.

2. **`docs\plans\2026-04-20-bcg-phase-1-report.md`**:
   - В секции «Чеклист archive/2026-04-23-bcg-planning-docs/BCG_plan.md L186» — отметить все `[ ]` как `[x]` (блокеры устранены).
   - В секции «Verify Pipeline» — отметить `[x]` всё что зелёное сейчас.
   - В секции «Известные проблемы / отложенное» — заменить описание на короткое `Resolved on 2026-04-21; see docs\plans\2026-04-21-phase-2-report.md`.
   - Раздел «Готовность к Phase 2» — заменить на `Да. Phase 2-5 landed; v1.0.0 released on 2026-04-22.`

3. **Один коммит**:
   ```
   docs: sync BCG_plan checklist and Phase-1 report with landed state
   ```

4. **Короткий отчёт `docs\plans\2026-04-22-bcg-sync-report.md`** (8–15 строк):
   - До: `X [ ] / Y [x]` в archive/2026-04-23-bcg-planning-docs/BCG_plan.md.
   - После: `X' [ ] / Y' [x]`.
   - Список секций которые частично landed (`partial`) с причиной.
   - Список секций совсем не начатых (чтобы юзер видел честный roadmap).

## Acceptance
- `grep -c "^- \[x\]" archive/2026-04-23-bcg-planning-docs/BCG_plan.md` возвращает значение, равное числу фактически landed пунктов (ожидается ≥ 50, см. фактическое состояние).
- `grep -c "^- \[ \]" archive/2026-04-23-bcg-planning-docs/BCG_plan.md` показывает только реально открытые пункты (ожидается 15–25 — секции 4.x Growth + §5 полировки).
- `docs\plans\2026-04-20-bcg-phase-1-report.md` — ни одного `[ ]` в секциях «Чеклист archive/2026-04-23-bcg-planning-docs/BCG_plan.md L186» и «Verify Pipeline».
- Коммит `docs: sync BCG_plan checklist and Phase-1 report with landed state` на HEAD, уникальный subject, `Co-Authored-By: Codex <noreply@anthropic.com>`.
- Этот CX-файл `2026-04-22-cx-bcg-plan-sync.md` **стадж в тот же коммит**.
- `scripts\verify_all.cmd` = exit 0 (docs не ломают verify; если ломают — не тот файл правили).
- `git status --short` = пусто после коммита.

## How
1. `cd D:\AB_TEST`; baseline `git status --short` = пусто, `scripts\verify_all.cmd` = 0.
2. `grep -n "^- \[ \]" archive/2026-04-23-bcg-planning-docs/BCG_plan.md > /tmp/bcg-open.txt` — собрать все.
3. Для каждого пункта — быстрый факт-чек:
   - §1.1.x (тесты hooks) — файлов `useAnalysis.ts` / `useProjectManager.ts` / `useDraftPersistence.ts` нет; вместо них Zustand stores (`git ls-files app/frontend/src/stores/`). Помечаем как landed, т.к. replaced.
   - §1.2.x (stores) — `ls app/frontend/src/stores/` покажет `themeStore.ts`, `wizardStore.ts`, `analysisStore.ts`, `projectStore.ts`, `draftStore.ts`. Все landed.
   - §1.3.x (results sections) — `ls app/frontend/src/components/results/` покажет все 11 секций. Landed.
   - §1.4.x (ErrorBoundary) — `ls app/frontend/src/components/*Boundary*`. Landed.
   - §1.5.x (CSS Modules) — `ls app/frontend/src/components/*.module.css`. Частично/полностью landed.
   - §1.6.x (enum status) — `grep -rn "status:" app/frontend/src/lib/types.ts`.
   - §2.x, §3.x (Phase 2/3 фичи) — сопоставить с коммит-логом `git log --oneline c29ab0d7..v1.0.0`.
   - §4.x (Growth) — реально не начаты; оставлять `[ ]`.
4. Патч `archive/2026-04-23-bcg-planning-docs/BCG_plan.md` точечными заменами через sed или редактор, **не пересочиняя** пункты.
5. Патч `docs\plans\2026-04-20-bcg-phase-1-report.md`.
6. Написать отчёт.
7. `git add archive/2026-04-23-bcg-planning-docs/BCG_plan.md docs/plans/2026-04-20-bcg-phase-1-report.md docs/plans/2026-04-22-bcg-sync-report.md docs/plans/codex-tasks/2026-04-22-cx-bcg-plan-sync.md`.
8. Коммит + verify.

## Notes
- **CX-файл hygiene:** staging этот файл в свой коммит.
- **Commit subject hygiene:** `git log --oneline -15 | awk '{$1=""; print $0}' | sort | uniq -d` должно быть пусто.
- **НЕ** переформулировать пункты, **НЕ** удалять их, **НЕ** реструктурировать план. Только `[ ]`→`[x]` и inline-ссылки.
- **НЕ** править v1.0.0 release notes / CHANGELOG — они закрыты.
- Если при факт-чеке выяснится что что-то landed не полностью — честно помечать `(partial)` с причиной; не надо заливать зелёным, если оно жёлтое.
- Backend `test_performance` может флапнуть — перезапустить один раз.
- **НЕ** пушить на remote.

## Out of scope
- Закрытие открытых пунктов Phase 4/5
- Изменения контента вне checkbox-states
- Переформатирование markdown
