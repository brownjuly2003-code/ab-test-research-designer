# CX Task: Multi-experiment comparison dashboard

## Goal
Превратить существующий project-comparison endpoint в полноценный dashboard в `D:\AB_TEST\`: поддержать выбор 2–5 экспериментов одновременно, side-by-side визуализацию (power curves, sensitivity matrices, observed effects forest plot), unified diff risks/assumptions, export comparison отчёта в PDF/Markdown.

## Context
- Репо: `D:\AB_TEST\`, `main`, HEAD после `4099f73c`. Не ветка, не push.
- Verify зелёный: backend 177, frontend 197.
- Сейчас есть `POST /api/v1/projects/{base_id}/compare/{candidate_id}` → `ProjectComparisonResponse` (см. `app/backend/app/schemas/api.py`): сравнивает ровно 2 проекта, возвращает deltas и highlights. Используется в `app/frontend/src/components/results/ComparisonSection.tsx`.
- Существующие виз-компоненты уже есть: `PowerCurveChart`, `SensitivityTable`, `ForestPlot`, `PosteriorPlot`, `SequentialBoundaryChart`.
- UI сейчас: pairwise compare кнопка в SidebarPanel, result в ResultsPanel.

## Deliverables
1. **Backend:**
   - Новый endpoint `POST /api/v1/projects/compare`:
     - Body: `{ "project_ids": ["id1", "id2", "id3", ...] }` — minimum 2, maximum 5.
     - Response: `MultiProjectComparisonResponse`:
       - `projects: list[ProjectComparisonItem]` (reuse existing schema)
       - `shared_warnings: list[str]`, `shared_risks: list[str]`, `shared_assumptions: list[str]`
       - `unique_per_project: dict[str, {warnings, risks, assumptions}]`
       - `sample_size_range: {min, max, median}`
       - `duration_range: {min, max, median}`
       - `metric_types_used: list[str]` (binary / continuous mix)
       - `recommendation_highlights: list[str]` (diff vs pairwise — aggregate)
   - Сохранить обратную совместимость: старый `/compare/{candidate_id}` остаётся (deprecated header `Deprecation: true`), внутренне вызывает новый.
   - Тесты: 2-project, 3-project, 5-project, 6-project (422 validation error), mixed metric types.

2. **Frontend:**
   - Новый компонент `app/frontend/src/components/ComparisonDashboard.tsx`:
     - Multiselect project picker (checkboxes в SidebarPanel, enable 2–5).
     - Button «Compare selected» → открывает dashboard.
     - Dashboard структура:
       - Top: project cards (name, metric_type, sample_size, duration, warning count, severity pill).
       - Section «Power curves» — multi-series `PowerCurveChart` (каждый проект — отдельная линия, legend с именем проекта).
       - Section «Sensitivity grid» — grid из `SensitivityTable` per project.
       - Section «Observed effects» — `ForestPlot` с каждым проектом как отдельный row.
       - Section «Shared / unique insights» — tabular diff: shared risks, unique per project.
   - Lazy-loaded.
   - Export button: `Export comparison PDF` / `Export comparison Markdown` — вызывает `POST /api/v1/export/comparison` (новый endpoint, см. ниже).
   - A11y: `role="region"` + `aria-labelledby` per section; multiselect с `aria-multiselectable="true"`.
   - i18n: keys в `comparison.*` — en/ru/de/es (последние две — если локалевый таск уже landed).

3. **Export endpoint:**
   - `POST /api/v1/export/comparison`:
     - Body: `{ "project_ids": [...], "format": "pdf" | "markdown" }`
     - Response: `{ "content": "..." }` (как существующий `/api/v1/export/{format}`).
   - Markdown: один document с per-project sections + summary.
   - PDF: reuse `pdf_service.py` генератор; multi-page с title page, per-project page, shared diff page.

4. **Тесты frontend:**
   - `ComparisonDashboard.test.tsx`: render 3 projects, проверить что 3 power curve lines, 3 sensitivity tables, forest plot с 3 rows.
   - `a11y-comparison-dashboard.test.tsx`: 0 axe violations, focus management при открытии/закрытии dashboard.
   - Snapshot если нужен — обновить.

5. **Тесты backend:**
   - `test_api_routes.py` extend:
     - `test_compare_multi_two_projects`, `_three_projects`, `_five_projects`, `_six_422`, `_single_422`, `_mixed_metric_types`.
   - `test_export_api.py` extend:
     - `test_export_comparison_markdown`, `test_export_comparison_pdf`.

6. **Regen:**
   - `python scripts/generate_frontend_api_types.py --check` = 0.
   - `python scripts/generate_api_docs.py --check` = 0 — `docs/API.md` включает новые endpoints.

7. **Docs:**
   - `docs/API.md` — auto.
   - `docs/RUNBOOK.md` — секция «Multi-project comparison» с curl-flow.

8. **Один коммит:**
   ```
   feat: multi-experiment comparison dashboard with export
   ```

9. **Отчёт `docs/plans/2026-04-22-comparison-dashboard-report.md`:**
   - Screenshot или ASCII-структура dashboard.
   - Bundle size growth (ожидается < 10 KB gzip т.к. reuse existing charts).
   - Backend perf: endpoint должен отвечать < 200ms на 5 projects.

## Acceptance
- `scripts\verify_all.cmd --with-e2e` = exit 0.
- Backend tests: +8–12 новых.
- Frontend tests: +4–6 новых.
- Main JS gzip < 145 KB (небольшой growth допустим; ComparisonDashboard lazy).
- Lighthouse a11y ≥ 0.9.
- `curl -X POST http://127.0.0.1:8008/api/v1/projects/compare -H "Content-Type: application/json" -d '{"project_ids":["<id1>","<id2>","<id3>"]}'` возвращает 200 с `projects.length == 3`.
- Commit subject уникальный, `Co-Authored-By: Codex <noreply@anthropic.com>`.
- Этот CX-файл стадж в свой коммит.
- `git status --short` = пусто.

## How
1. Baseline: `git status --short` = пусто, verify = 0.
2. Backend: schema → route → service → tests. Сохранить обратную совместимость старого pairwise.
3. Frontend: новый компонент, sidebar multi-select.
4. Export endpoint + PDF reuse.
5. Regen contracts.
6. Commit + verify + report.

## Notes
- **CX-файл hygiene:** staging этого файла.
- **Commit subject hygiene:** проверка на дубль.
- **Bundle budget:** если новые chart imports разгоняют main > 145 KB — lazy-load dashboard через `React.lazy`. Reuse existing chart components (они уже lazy).
- **НЕ** переписывать существующий `/compare/{candidate_id}` endpoint — добавить новый рядом; старый deprecated.
- **НЕ** добавлять новые deps.
- **Mixed metric types:** если в selection есть `binary` + `continuous` — отображать, но помечать «Mixed metric types — direct effect comparison not meaningful» warning в dashboard.
- **Dashboard export PDF:** reuse `pdf_service.render_report` — может потребоваться расширить с multi-section. Если усложнение >30 мин — fallback: PDF только для single project в сравнении, markdown — полный multi.
- Backend `test_performance` может флапнуть — перезапустить один раз.
- **НЕ** пушить на remote.

## Out of scope
- Drag-n-drop reordering в dashboard
- Saved comparison presets
- Scheduled comparison reports (cron + email)
- Live collaboration (multi-user comments)
- Baseline / treatment vs control highlighting (все проекты равные)
