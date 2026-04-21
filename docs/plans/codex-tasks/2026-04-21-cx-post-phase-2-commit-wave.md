# CX Task: Commit post-Phase-2 feature wave (templates, PDF, filters/shortcuts, audit)

## Goal
Разнести текущий working tree в `D:\AB_TEST\` на 4 коммита поверх `main@c29ab0d7` и подтвердить `scripts\verify_all.cmd --with-e2e` = exit 0 на финале. Код уже готов и зелёный (backend 165 / frontend 160 / typecheck / contract --check), нужна только чистая история.

## Context
- Репо: `D:\AB_TEST\`, ветка `main`, HEAD = `c29ab0d7 "chore: lighthouse CI config, verification scripts, and BCG phase docs"`.
- Phase 1–5 BCG-работа уже в истории (3 коммита); полная verify на чистом HEAD зелёная.
- Текущий working tree содержит следующую волну фич, landed как код, но uncommitted:
  - **Templates gallery:** 5 yaml-пресетов в `app/backend/templates/` + `routes/templates.py` + `services/template_service.py` + `schemas/template.py` + `components/TemplateGallery.tsx`
  - **PDF / shareable reports:** `services/pdf_service.py` + `components/ChartExport.tsx` + `ChartExport.test.tsx` + правки в результатных секциях (`results/PowerCurveSection.tsx`, `results/SensitivitySection.tsx`, `results/internal/SensitivityOverview.tsx`, `results/__tests__/SensitivitySection.test.tsx`) + `stores/projectStore.{ts,test.ts}` (добавлен формат `"pdf"` в `ExportFormat`) — соответствует `docs/plans/codex-tasks/phase-3-4-shareable-reports.md`
  - **UX helpers:** `components/ProjectListFilters.tsx` + `components/ShortcutHelp.tsx` + изменения в `SidebarPanel.tsx`, `WizardPanel.tsx`, `App.test.tsx`, `WizardDraftStep.test.tsx`, `WizardReviewStep.test.tsx`, `components/__snapshots__/WizardPanel.test.tsx.snap`, `components/WizardDraftStep.tsx`, `components/WizardReviewStep.tsx`
  - **Audit log:** `app/backend/app/routes/audit.py` + соответствующие изменения в `schemas/api.py` (`AuditLogResponse`), `app/backend/app/main.py` (роутер), `repository.py` (persist), `tests/test_api_routes.py` новые кейсы
  - **Sidecar правки:** `routes/projects.py` (поддержка filters), `services/export_service.py` (PDF integration), `requirements.txt` (если добавлена reportlab или аналог), `lib/api.ts` + `lib/generated/api-contract.ts` + `lib/types.ts` (новые endpoints), `index.html` (если есть правки шрифта/мета)
  - **Docs:** `docs/plans/2026-04-10-next-features.md` (+110/-32), `docs/plans/2026-04-20-bcg-phase-1.md` (+32), `docs/plans/2026-04-21-phase-2-visual.md` (+23), `docs/API.md` (+40), `docs/plans/2026-04-21-phase-2-report.md` (новый)
- Текущее состояние: `git diff HEAD --stat | tail -3` = `31 files changed, 2923 insertions(+), 180 deletions(-)` плюс untracked новые файлы.
- **Весь код уже проходит тесты и типчек** — задача только commit-split, без изменений логики.

## Deliverables
1. 4 локальных коммита поверх `c29ab0d7` в таком порядке:
   1. `feat: experiment template gallery with yaml presets`
   2. `feat: shareable PDF reports with chart export` (Phase 3.4 shareable reports)
   3. `feat: project list filters and keyboard shortcut help`
   4. `feat: audit log endpoint and request trail persistence`
2. После последнего коммита: `scripts\verify_all.cmd --with-e2e` = exit 0.
3. Финальный отчёт `docs\plans\2026-04-21-post-phase-2-commit-log.md`:
   - `git log --oneline -8`
   - для каждого из 4 новых коммитов: title, хэш, `+N / -M` строк, # файлов
   - что осталось untracked намеренно (archive/e2e-runs, archive/manual-smoke-runs, archive/verify-workspace-backup, archive/smoke-runs, tmp/, .hypothesis/, .qa/, .docker-cli/)

## Acceptance
- `git log --oneline -5` показывает 4 новых коммита сверху, ниже `c29ab0d7`.
- После финального коммита: `scripts\verify_all.cmd --with-e2e` = 0 (включая `generate_frontend_api_types.py --check` и `generate_api_docs.py --check`).
- `git status --short` на конце: пусто ИЛИ только намеренно untracked (archive/* run-artifacts + untracked файлы из .gitignore).
- Финальный отчёт присутствует, точен.
- Каждый commit содержит trailer `Co-Authored-By: Codex <noreply@anthropic.com>`.

## How to split

Порядок важен: templates → PDF → UX helpers → audit. Audit трогает `main.py`/`repository.py`, PDF трогает `projectStore.ts`/`api-contract.ts`; чтобы избежать повторных staging конфликтов — разбивать по фичам, а связанные sidecar-правки группировать с основной фичей.

### Commit 1 — Templates gallery
Stage (новые):
- `app/backend/app/routes/templates.py`
- `app/backend/app/services/template_service.py`
- `app/backend/app/schemas/template.py`
- `app/backend/templates/*.yaml` (все 5: checkout_conversion, feature_adoption, latency_impact, onboarding_completion, pricing_sensitivity)
- `app/frontend/src/components/TemplateGallery.tsx`
Stage hunks (modified) — только секции, относящиеся к templates:
- `app/backend/app/main.py` — регистрация templates-роутера
- `app/backend/app/schemas/api.py` — `TemplateRecord`-типы / re-exports, если есть
- `app/backend/tests/test_api_routes.py` — хаки templates endpoints (если добавлены)
- `app/frontend/src/lib/api.ts` — `listTemplatesRequest`, `useTemplateRequest`
- `app/frontend/src/lib/types.ts`, `lib/experiment.ts` — `TemplateRecord` type export
- `app/frontend/src/lib/generated/api-contract.ts` — template-related entries
- `app/frontend/src/components/SidebarPanel.tsx` / `App.tsx` / `App.test.tsx` — точка монтирования TemplateGallery (если там)
- `docs/API.md` — templates endpoints

Commit msg: `feat: experiment template gallery with yaml presets`

Verify: `python -m pytest app\backend\tests -q` + `cd app\frontend && npm.cmd exec tsc -- --noEmit -p .` + оба `--check` скрипта — все exit 0.

### Commit 2 — Shareable PDF reports
Stage (новые):
- `app/backend/app/services/pdf_service.py`
- `app/frontend/src/components/ChartExport.tsx`
- `app/frontend/src/components/ChartExport.test.tsx`
Stage hunks:
- `app/backend/app/schemas/api.py` — `ExportFormat` добавление `pdf` и export-ответ
- `app/backend/app/services/export_service.py` — PDF-рендеринг
- `app/backend/app/routes/projects.py` / `routes/export.py` — POST `/api/v1/export/pdf` или расширение существующего
- `app/backend/requirements.txt` — добавленный PDF-генератор (reportlab / weasyprint / fpdf — проверить по актуальному коду)
- `app/backend/tests/test_export_api.py` / `test_api_routes.py` — PDF-кейсы
- `app/frontend/src/components/results/PowerCurveSection.tsx`, `SensitivitySection.tsx`, `__tests__/SensitivitySection.test.tsx`, `internal/SensitivityOverview.tsx` — props `canExportPdf` / `onExportPdf` / ChartExport wiring
- `app/frontend/src/components/ResultsPanel.tsx` — проброс колбэков
- `app/frontend/src/stores/projectStore.ts`, `projectStore.test.ts` — `"pdf"` в `ExportFormat`
- `app/frontend/src/lib/api.ts`, `lib/types.ts`, `lib/generated/api-contract.ts` — PDF endpoint
- `docs/API.md` — PDF endpoint

Commit msg: `feat: shareable PDF reports with chart export (BCG Phase 3.4)`

Verify: `scripts\verify_all.cmd --with-e2e` = 0.

### Commit 3 — Project filters + Shortcut help
Stage (новые):
- `app/frontend/src/components/ProjectListFilters.tsx`
- `app/frontend/src/components/ShortcutHelp.tsx`
Stage hunks:
- `app/frontend/src/components/SidebarPanel.tsx` — подключение ProjectListFilters
- `app/frontend/src/components/WizardPanel.tsx`, `WizardDraftStep.tsx`, `WizardReviewStep.tsx`, `WizardDraftStep.test.tsx`, `WizardReviewStep.test.tsx` — keyboard hooks
- `app/frontend/src/components/__snapshots__/WizardPanel.test.tsx.snap` — обновлённый snapshot (если обусловлено shortcut-help overlay)
- `app/frontend/src/App.test.tsx` — тесты shortcut-help и фильтров
- `app/backend/app/routes/projects.py` — query params (status / search) если не попало в Commit 2
- `app/backend/tests/test_projects_api.py` / `test_api_routes.py` — фильтр-кейсы
- `docs/API.md` — query params (если меняется)

Commit msg: `feat: project list filters and keyboard shortcut help`

Verify: `python -m pytest app\backend\tests -q` + `npm.cmd run test:unit` + `npm.cmd exec tsc -- --noEmit -p .` — все exit 0.

### Commit 4 — Audit log endpoint
Stage (новые):
- `app/backend/app/routes/audit.py`
Stage hunks:
- `app/backend/app/schemas/api.py` — `AuditLogResponse`, `AuditLogEntry`
- `app/backend/app/main.py` — регистрация audit-роутера
- `app/backend/app/repository.py` — persistence audit-записей (если не попало в Commit 1)
- `app/backend/tests/test_api_routes.py` — audit endpoint тесты
- `app/frontend/src/lib/api.ts` / `lib/types.ts` / `lib/generated/api-contract.ts` — audit-типы
- `docs/API.md` — audit endpoint

Stage docs (в финальный коммит попадают одним махом):
- `docs/plans/2026-04-10-next-features.md` (status update)
- `docs/plans/2026-04-20-bcg-phase-1.md` (status update)
- `docs/plans/2026-04-21-phase-2-visual.md` (status update)
- `docs/plans/2026-04-21-phase-2-report.md`
- `docs/plans/codex-tasks/2026-04-21-cx-post-phase-2-commit-wave.md` (этот файл)
- `.gitignore` (если изменён и ещё не в истории)

Commit msg: `feat: audit log endpoint and request trail persistence`

Verify: `scripts\verify_all.cmd --with-e2e` = 0.

## Runbook
1. `cd D:\AB_TEST`, `git status --short` — зафиксировать baseline.
2. Сохранить `git diff HEAD --stat > tmp\post-phase-2-baseline.txt` (файл окажется untracked, ОК).
3. Commit 1:
   - `git add <файлы templates>`; `git add -p` для shared-файлов — брать только template-хунки
   - `git diff --cached --stat | tail -3`
   - `git commit -m "feat: experiment template gallery with yaml presets" -m "" -m "Co-Authored-By: Codex <noreply@anthropic.com>"`
   - Quick verify (см. Commit 1 Verify).
4. Commit 2: `git add -p` для модифицированных; новые файлы `git add <path>` прямо. Финальный `verify_all --with-e2e`.
5. Commit 3, Commit 4 — аналогично.
6. Удалить `tmp\post-phase-2-baseline.txt` если больше не нужен (untracked).
7. Записать `docs\plans\2026-04-21-post-phase-2-commit-log.md`.

## Notes
- **Не** использовать `--amend`, `--force`, `reset --hard`. Если попал не в ту кучу — `git reset HEAD~1` (mixed) и перестроить stage.
- **Не** пушить на remote.
- Если `git add -p` разрезать не удаётся (hunks слишком связаны) — bundle в меньше коммитов: допустимо слить Commit 1+2 (templates+PDF = "experiment content pipeline") или Commit 3+4 (UX+audit = "ops helpers"). Минимум 2 коммита, максимум 4. Зафиксировать deviation в commit-log.
- **Не** коммитить `archive/e2e-runs/**`, `archive/manual-smoke-runs/**`, `archive/verify-workspace-backup/**`, `archive/smoke-runs/**` — это diagnostic runs, они мусорят историю. Если они не покрыты `.gitignore` — **не** расширять `.gitignore` в этом таске (оставить untracked, упомянуть в commit-log).
- Архивные файлы `archive/audit.md`, `archive/rec.md`, `archive/questions.md`, `archive/prompt_for_github.md`, `archive/ab_test_for_gihub.md` — оставить untracked, они исторические; если юзер решит их сохранить — отдельный docs-таск.
- Регенерация `api-contract.ts` / `docs/API.md` — только через `python scripts\generate_*.py` (без `--check`); после регена `--check` должен проходить.
- Backend test_performance p95-guard может флапнуть — перезапустить один раз.

## Out of scope
- Push / PR
- Новые фичи или рефактор
- Архивная гигиена (отдельный таск, см. `2026-04-21-cx-archive-hygiene.md`)
- Phase 3 gap-аудит (отдельный таск)
