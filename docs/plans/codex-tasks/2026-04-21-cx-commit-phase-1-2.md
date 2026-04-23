# CX Task: Split uncommitted BCG Phase 1+2(+3+4) работа на коммиты и land

## Goal
Разнести огромный uncommitted working tree в `D:\AB_TEST\` на 4 читаемых коммита поверх `main@eb06592` и подтвердить `scripts\verify_all.cmd --with-e2e` = 0 на финале. Цель — чистая история, без сломанного verify.

## Context
- Репо: `D:\AB_TEST\` (Windows, bash shell доступен).
- Base branch: `main`, HEAD сейчас `eb06592 "Unify cross-platform verify entrypoint"`. Не создавать новую ветку.
- `git status` выдаёт 75 modified + большой список новых файлов (см. Acceptance для списка untracked, которые остаются untracked).
- Verify-pipeline **уже зелёный** на working tree: backend 144 tests, frontend 152 unit tests, workspace backups (checksum + signed), benchmark, typecheck, build, smoke, e2e. `python scripts\generate_frontend_api_types.py --check` и `python scripts\generate_api_docs.py --check` → up to date.
- Задача — **не сломать зелёный verify**; история должна читаться: refactor → visual → stats features → infra/docs.
- План на который опираться: `docs\plans\2026-04-21-phase-2-visual.md`, секции C–H.

## Deliverables
1. 4 локальных commit поверх `eb06592` в таком порядке (повторяют план):
   1. `refactor: decompose App/ResultsPanel and introduce Zustand stores (BCG Phase 1)`
   2. `feat: visual transformation with Recharts, skeletons, theme toggle, and Lucide icons (BCG Phase 2)`
   3. `feat: multi-metric guardrails, SRM, sequential, CUPED, and bayesian power (BCG Phases 3-4)`
   4. `chore: lighthouse CI config, verification scripts, and BCG phase docs`
2. После последнего коммита: `scripts\verify_all.cmd --with-e2e` завершается exit 0.
3. Финальный отчёт `docs\plans\2026-04-21-phase-2-commit-log.md` с:
   - `git log --oneline -8`
   - для каждого из 4 новых коммитов: title, хэш, кол-во файлов, `+N / -M` строк
   - короткий раздел «verify после commit N»: какой verify запускался и результат
   - блок «что осталось uncommitted намеренно» (tmp/, archive/ runs, .qa/, .hypothesis/, .docker-cli/)

## Acceptance
- `git log --oneline -5` показывает 4 новых коммита сверху, ниже `eb06592`.
- Каждый коммит компилируется (`python -m pytest app\backend\tests -q` и `cd app\frontend && npm.cmd exec tsc -- --noEmit -p .`) самостоятельно; full verify — на втором и четвёртом.
- `git status` на конце: чисто (только намеренно untracked).
- Финальный отчёт присутствует и точен.
- Каждый commit содержит trailer `Co-Authored-By: Codex <noreply@anthropic.com>`.

## How to split
Подход — staging через `git add` конкретных файлов по спискам ниже. Если один файл содержит изменения для двух phase-буcket одновременно (`App.tsx`, `SidebarPanel.tsx`, `ResultsPanel.tsx`, `Icon.tsx`, `schemas/api.py`, `services/calculations_service.py`, `stats/binary.py`, `stats/continuous.py`) — использовать `git add -p` для hunk-уровня. Если hunk-разбор невозможен/лоссовый/ломает tests, **fallback**: сливать Commits 1+2 в один (`refactor+viz bundle`, Phase 1+2) и Commits 3+4 в один (`features+infra`). В report зафиксировать «bundled into 2 commits instead of 4 because of entanglement in <file>».

### Commit 1 — Phase 1 refactor
- `app/frontend/src/App.tsx`, `App.test.tsx`
- `app/frontend/src/stores/**`
- `app/frontend/src/hooks/useCalculationPreview.*`, `useToast.*` (**nota bene**: useToast также явно используется новым `ToastSystem` из Commit 2 — если тест `useToast.test.tsx` падает без ToastSystem, переложить файл в Commit 2)
- `app/frontend/src/components/WizardPanel.tsx`, `WizardPanel.test.tsx`, `WizardReviewStep.tsx`, `WizardReviewStep.test.tsx`, `WizardDraftStep.tsx`, `WizardDraftStep.test.tsx`
- `app/frontend/src/lib/field-config.ts`, `payload.ts`, `types.ts`, `validation.ts`, `api.ts`, `api.test.ts`, `experiment.ts`, `experiment.test.ts`, `lib/generated/api-contract.ts`
- `app/backend/app/routes/**`, `frontend_routes.py`, `http_runtime.py`, `http_utils.py`
- `app/backend/app/main.py` (структурные части — роутинг, startup; не отдельные фичи)
- `app/backend/tests/test_api_routes.py`, `test_calculations.py`, `test_config.py`, `test_design_service.py`, `test_export_api.py`, `test_frontend_serving.py`, `test_projects_api.py`, `test_repository.py`
- `docs/API.md` (перегенерирован контрактом)

### Commit 2 — Phase 2 visual
- `app/frontend/src/components/PowerCurveChart.tsx`, `SensitivityTable.tsx`, `SampleSizeBar.tsx`, `ForestPlot.tsx`, `results/**`
- `app/frontend/src/components/Skeleton.tsx`, `Skeleton.module.css`, `ProjectListSkeleton.tsx`, `ResultsSkeleton.tsx`
- `app/frontend/src/components/ChartErrorBoundary.tsx`, `ChartErrorBoundary.test.tsx`, `ErrorBoundary.tsx`, `ErrorBoundary.test.tsx`
- `app/frontend/src/components/ToastSystem.tsx`, `ToastSystem.module.css`
- `app/frontend/src/components/Icon.tsx`, `Icon.test.tsx` (Lucide версия)
- `app/frontend/src/components/MetricCard.module.css`, `EmptyState.tsx`, `EmptyState.module.css`, `InlineConfirmButton.tsx`, `InlineConfirmButton.module.css`, `Spinner.module.css`, `StatusDot.module.css`, `Tooltip.module.css`, `SliderInput.tsx`, `SliderInput.module.css`, `ProgressBar.module.css`, `Accordion.module.css`, `SidebarPanel.module.css`, `ResultsPanel.module.css`, `ResultsPanel.test.tsx`, `LivePreviewPanel.tsx`, `__snapshots__/**`
- `app/frontend/src/styles/**`
- `app/frontend/src/i18n/**`
- `app/frontend/package.json`, `package-lock.json` (recharts@^3.8.1, lucide-react@^1.8.0)
- `app/frontend/playwright.config.ts` если изменён
- Затронутые hunk-уровневые правки в `App.tsx` / `SidebarPanel.tsx` / `ResultsPanel.tsx` относящиеся к встраиванию новых секций (если не получилось положить в Commit 1)

### Commit 3 — Phase 3+4 stats
- `app/backend/app/stats/bayesian.py`, `sequential.py`, `srm.py`
- `app/backend/app/services/results_service.py`
- `app/backend/tests/test_bayesian.py`, `test_sequential.py`, `test_srm.py`, `test_results_service.py`
- `app/backend/app/schemas/api.py`, `schemas/report.py` — hunks добавляющие `GuardrailMetricInput`, `SrmCheckRequest/Response`, `SensitivityRequest/Response`, `ResultsRequest/Response`, bayesian/sequential поля в `CalculationRequest/Response` и `ConstraintsConfig`
- `app/backend/app/rules/catalog.py`, `rules/engine.py` — multi-metric warning codes
- `app/backend/app/services/calculations_service.py`, `design_service.py`, `export_service.py` — hunks под новые фичи
- `app/backend/app/stats/binary.py`, `continuous.py` — multi-variant/multi-metric правки

### Commit 4 — Infra & docs
- `.env.example`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/test.yml`, `.gitignore`, `.lighthouserc.json`, `README.md`, `CHANGELOG.md`, `archive/2026-04-23-bcg-planning-docs/progress.md`
- `scripts/run_frontend_e2e.py`, `update_ai_state_new.py`, `run_local_smoke.py`, `run_backend_for_e2e.py`, `generate_api_docs.py`, `verify_all.cmd`, `verify_all.ps1`, `verify_all.py`, `verify_docker_compose.py`, `verify_workspace_backup.py`, `benchmark_backend.py`
- `docs/ARCHITECTURE.md`, `HISTORY.md`, `RUNBOOK.md`, `RELEASE_CHECKLIST.md`
- `docs/plans/**` (включая `2026-04-21-phase-2-visual.md`, этот CX-таск, и новый commit-log)
- `docs/research-grey-market-digital-subscriptions.md`
- `docs/demo/*.png`, `docs/demo/sample-project.json`
- `app/backend/app/main.py`, `config.py`, `repository.py` — оставшиеся infra-only hunks
- `archive/2026-04-23-bcg-planning-docs/BCG_audit.md`, `archive/2026-04-23-bcg-planning-docs/BCG_plan.md`, `archive/2026-04-23-bcg-planning-docs/bcg-phase-1-execution.md`, `archive/2026-04-23-bcg-planning-docs/commercial-upgrade-plan.md`
- Новые файлы под `archive/` (если их планируется хранить в истории; если нет — оставить untracked)

## Runbook

1. `cd D:\AB_TEST` (не создавать новую ветку, не trigger-ить remote).
2. `git status`, `git diff --stat HEAD | tail -3` — подтвердить baseline.
3. Для Commit 1:
   - `git add <список файлов выше>`
   - `git diff --cached --stat | tail -3`
   - `git commit -m "refactor: decompose App/ResultsPanel and introduce Zustand stores (BCG Phase 1)" -m "" -m "Co-Authored-By: Codex <noreply@anthropic.com>"`
   - `python -m pytest app\backend\tests -q && cd app\frontend && npm.cmd exec tsc -- --noEmit -p . && cd ..\..`
4. Для Commit 2 — аналогично + `scripts\verify_all.cmd --with-e2e`.
5. Для Commit 3 — аналогично + backend pytest обязателен.
6. Для Commit 4 — финал + `scripts\verify_all.cmd --with-e2e`.
7. Удалить временные файлы: `tmp\test_hydrated.json`, `tmp\verify.log` (они untracked — просто `rm` без git).
8. Записать `docs\plans\2026-04-21-phase-2-commit-log.md`.

## Notes
- **Не** использовать `--amend`, `--force`, `reset --hard`. Если commit пошёл не в ту кучу — `git reset HEAD~1` (mixed, сохраняет working tree) и перестроить stage.
- **Не** пушить на remote (origin). Локальная история.
- **Не** запускать `scripts\generate_frontend_api_types.py` без `--check` — файл уже up-to-date.
- CRLF warnings от Git на Windows игнорировать (нормальная нормализация).
- Если pre-commit hook провалится (в репо hooks нет, но на всякий случай) — **не** использовать `--no-verify`, починить причину.
- `.hypothesis/`, `.docker-cli/`, `tmp/`, `.qa/`, `archive/verify-workspace-backup/`, `archive/smoke-runs/`, `archive/e2e-runs/`, `archive/manual-smoke-runs/` — намеренно untracked. Проверить `.gitignore`; если не покрыто — **не** добавлять их в коммит и **не** расширять `.gitignore` (это отдельный тикет).
- Если тесты покраснеют после Commit 3 из-за флаппи backend `test_performance.py` — перезапустить один раз; если продолжает — останов и report (не маскировать sleep-ом).

## Out of scope
- Push / PR на remote
- Новые фичи / рефакторы кода
- Обновление чеклиста в `archive/2026-04-23-bcg-planning-docs/BCG_plan.md` (это сделает главный агент после merge)
- Regen `api-contract.ts` / `API.md` (они уже up-to-date)
- Исправление reduced-motion / bundle-budget gaps (отдельный CX-таск)
