# Phase 2 — Visual Transformation (land & gates)

Дата: 2026-04-21
База: `main` @ `eb06592`
Предусловие: BCG Phase 1 verify-pipeline зелёный (см. `2026-04-20-bcg-phase-1-report.md` + исправления 2026-04-21: api-contract.ts и docs/API.md regen, 422-UI bug устранён, smoke/e2e/unit/build — всё проходит).

## Текущее состояние

Весь код Phase 2 уже в working tree:
- `app/frontend/src/components/PowerCurveChart.tsx`, `SensitivityTable.tsx`, `SampleSizeBar.tsx`, `ForestPlot.tsx`, `results/*` — Recharts-графики
- `Skeleton.tsx`, `ProjectListSkeleton.tsx`, `ResultsSkeleton.tsx`, `ChartErrorBoundary.tsx`, `ErrorBoundary.tsx`, `ToastSystem.tsx` — loading + error UX
- `themeStore.ts` + theme toggle в header (`[data-theme]` атрибут, persist в localStorage)
- `Icon.tsx` уже на `lucide-react@^1.8.0` (inline SVG заменены)
- `recharts@^3.8.1` в `package.json`; bundle в последнем build: 396.71 KB JS / 114.80 KB gzip total; отдельный chunk для PowerCurveChart 359.30 KB / 107.09 KB gzip

Все это в uncommitted working tree (75 files modified, 7101 insertions / 5110 deletions плюс новые директории). Phase 3–4 код (stats/bayesian, stats/sequential, stats/srm, services/results_service, multi-metric schemas) тоже в том же working tree.

Задача Phase 2 — не писать новый код, а:
1. Подтвердить что реализация проходит constraints из `codex-tasks/phase-2-*.md`.
2. Закрыть 1–2 точечных gap (reduced-motion, bundle check).
3. Разнести working tree на читаемые коммиты поверх `main`.
4. Подтвердить verify-pipeline green на каждом коммите.

## Шаги (чанки 2–5 мин)

### A. Зафиксировать baseline
- Запустить `scripts\verify_all.cmd --with-e2e` → exit 0.
- Снять `git diff --stat HEAD` → сохранить в `docs/plans/2026-04-21-phase-2-baseline.txt`.
- Снять `npm run build` размеры: `docs/plans/2026-04-21-phase-2-bundle-baseline.txt` (dist имена + gzip).
- Точка коммита: нет.

### B. Gap-чек constraints Phase 2
- CSS проверка `prefers-reduced-motion` — `grep -r "prefers-reduced-motion" app/frontend/src/styles/`. Должен быть один блок, отключающий `transition` и `animation`. Если отсутствует — добавить в `styles/index.css` (или глобальный CSS). Unit-тестом не закрывается; визуальная проверка в DevTools → Rendering → Emulate reduced motion.
- A11y проверка: `Skeleton` имеет `aria-hidden="true"`, theme toggle — `aria-label` на каждой кнопке, `ChartErrorBoundary` не блокирует tab-order.
- Bundle budget: main JS gzip < 130 KB; PowerCurve chunk загружается только когда открыт Results. Если main JS ≥ 130 KB — проверить, не затянуло ли `recharts` в основной chunk (должен быть lazy через `React.lazy`).
- Результат: `docs/plans/2026-04-21-phase-2-gap-report.md` (пройдено / нужно правка / правка сделана).
- Точка коммита: если был fix — commit `style: honor prefers-reduced-motion in animated components` (или аналогичный).

### C. Commit 1 — Phase 1 core refactor
Stage только файлы рефакторинга App/ResultsPanel и Zustand-store:
- `app/frontend/src/App.tsx`, `App.test.tsx`
- `app/frontend/src/stores/**`
- `app/frontend/src/components/WizardPanel.tsx`, `WizardReviewStep.tsx`, `WizardDraftStep.tsx`, `SidebarPanel.tsx`, `ResultsPanel.tsx` (structural part only, без визуальных новых секций — если разделить неочевидно, см. Risks)
- `app/frontend/src/hooks/useCalculationPreview.ts`, `useToast.ts` + их тесты
- `app/backend/app/routes/**`, `frontend_routes.py`, `http_runtime.py`, `http_utils.py`
- `app/backend/tests/test_*.py` модифицированные (без test_bayesian, test_sequential, test_srm, test_results_service)
- `app/frontend/src/lib/field-config.ts`, `payload.ts`, `types.ts`, `validation.ts`
- `app/frontend/src/lib/generated/api-contract.ts`
- `docs/API.md`

Commit: `refactor: decompose App/ResultsPanel and introduce Zustand stores (BCG Phase 1)`.

Verify: `scripts\verify_all.cmd` = 0.

### D. Commit 2 — Phase 2 visual
Stage:
- `app/frontend/src/components/PowerCurveChart.tsx`, `SensitivityTable.tsx`, `SampleSizeBar.tsx`, `ForestPlot.tsx`, `results/*`
- `app/frontend/src/components/Skeleton.tsx`, `Skeleton.module.css`, `ProjectListSkeleton.tsx`, `ResultsSkeleton.tsx`
- `app/frontend/src/components/ChartErrorBoundary.tsx`, `ChartErrorBoundary.test.tsx`, `ErrorBoundary.tsx`, `ErrorBoundary.test.tsx`
- `app/frontend/src/components/ToastSystem.tsx`, `ToastSystem.module.css`, `hooks/useToast.*`
- `app/frontend/src/components/Icon.tsx` (Lucide версия), `Icon.test.tsx`
- `app/frontend/src/components/MetricCard.module.css`, `EmptyState.*`, `InlineConfirmButton.*`, `Spinner.module.css`, `StatusDot.module.css`, `Tooltip.module.css`, `SliderInput.*`, `ProgressBar.module.css`, `Accordion.module.css`, `SidebarPanel.module.css`, `ResultsPanel.module.css`, `WizardDraftStep.module.css`
- `app/frontend/src/styles/**`
- `app/frontend/src/i18n/**`
- `app/frontend/package.json` + `package-lock.json` (recharts, lucide-react)
- `app/frontend/playwright.config.ts` (если обновлён)

Commit: `feat: visual transformation with Recharts, skeletons, theme toggle, and Lucide icons (BCG Phase 2)`.

Verify: `scripts\verify_all.cmd --with-e2e` = 0.

### E. Commit 3 — Phase 3+4 stats features
Stage:
- `app/backend/app/stats/bayesian.py`, `sequential.py`, `srm.py`
- `app/backend/app/services/results_service.py`
- `app/backend/tests/test_bayesian.py`, `test_sequential.py`, `test_srm.py`, `test_results_service.py`
- Изменения в `app/backend/app/schemas/api.py` и `schemas/report.py` связанные с multi-metric / guardrails / CUPED / sequential / bayesian полями
- `app/backend/app/rules/catalog.py`, `rules/engine.py`
- `app/backend/app/services/calculations_service.py`, `design_service.py`, `export_service.py` в части новых фич
- `app/backend/app/stats/binary.py`, `continuous.py` правки под multi-metric

Commit: `feat: multi-metric guardrails, SRM, sequential, CUPED, and bayesian power (BCG Phases 3-4)`.

Verify: `scripts\verify_all.cmd` = 0.

### F. Commit 4 — Infra, docs, scripts
Stage:
- `.env.example`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/test.yml`, `.gitignore`, `.lighthouserc.json`, `README.md`, `CHANGELOG.md`, `progress.md`
- `scripts/run_frontend_e2e.py`, `scripts/update_ai_state_new.py`, `scripts/run_local_smoke.py`, `scripts/run_backend_for_e2e.py`, `scripts/generate_api_docs.py`, `scripts/verify_*.cmd/.ps1/.py`, `scripts/verify_docker_compose.py`, `scripts/verify_workspace_backup.py`, `scripts/benchmark_backend.py`
- `docs/ARCHITECTURE.md`, `docs/HISTORY.md`, `docs/RUNBOOK.md`, `docs/RELEASE_CHECKLIST.md`, `docs/plans/**`, `docs/research-grey-market-digital-subscriptions.md`
- `docs/demo/*.png`, `docs/demo/sample-project.json`
- `app/backend/app/main.py`, `config.py`, `repository.py` только оставшиеся infra-правки
- `BCG_audit.md`, `BCG_plan.md`, `bcg-phase-1-execution.md`, `commercial-upgrade-plan.md`
- `archive/**` добавления исторических отчётов

Commit: `chore: lighthouse CI config, verification scripts, and BCG phase docs`.

Verify: `scripts\verify_all.cmd --with-e2e` = 0.

### G. Cleanup
- Убедиться что `tmp/`, `.qa/`, `.hypothesis/`, `.docker-cli/` в `.gitignore`.
- Удалить рабочие артефакты разбора: `tmp/test_hydrated.json`, `tmp/verify.log`.
- `git status` → должны остаться только папки, которые намеренно untracked (archive runs, tmp, .qa).

### H. Финальный gate
- `scripts\verify_all.cmd --with-e2e` → exit 0.
- `git log --oneline -6` читается линейно, без merge-коммитов.
- Обновить `docs/plans/2026-04-20-bcg-phase-1-report.md` или написать короткий `docs/plans/2026-04-21-phase-2-report.md` (готовность к Phase 3 = yes/no, deltas, bundle sizes).

## Acceptance
- 4 коммита поверх `eb06592`, каждый проходит хотя бы базовый verify (backend tests + typecheck + unit + build). Full e2e обязательно на Commit 2 и последнем.
- Main JS gzip < 130 KB либо чёткое обоснование в gap-report.
- Reduced-motion правило присутствует в CSS.
- `docs/plans/2026-04-21-phase-2-report.md` фиксирует итог.

## Risks
- **Entanglement.** Некоторые файлы (`App.tsx`, `ResultsPanel.tsx`, `Icon.tsx`, `SidebarPanel.tsx`, `schemas/api.py`, `services/calculations_service.py`) затронуты и Phase 1, и Phase 2/3/4. Разделить построчно через `git add -p` возможно, но трудоёмко. **Fallback:** если разбор затягивается >30 мин или ломает verify — слить Commits 1+2 в один («refactor+viz bundle», Phase 1+2) и Commits 3+4 в один («features+infra», Phase 3–5). Получится 2 коммита — это тоже читаемо и соответствует правилу юзера «одна PR vs churn». Зафиксировать решение в report.
- **CRLF шум.** `git diff` показывает LF→CRLF warnings на Windows. Игнорировать: Git сам нормализует, diff остаётся корректным.
- **Backend test_performance.py** содержит p95-guard. Если между commit 1 и commit 3 порядок импортов/моков в stats изменит производительность — локальный p95 может флапнуть. Перегенерация benchmark baseline не требуется; повторный запуск обычно зелёный.

## Searched / decisions
- `docs/plans/codex-tasks/phase-2-1-data-visualization.md` constraint: main JS gzip < 130 KB. Источник: явно написано в конце таска.
- `prefers-reduced-motion` требование: `phase-2-2-visual-polish.md`. Источник: секция Constraints.
- `SensitivityTable` без canvas — это уже реализовано (чистая HTML-таблица в `SensitivityTable.tsx`).
- Бандл-сплит: PowerCurveChart в отдельном chunk — видно по последнему build (separate `assets/PowerCurveChart-HBJ2y2s-.js`).
