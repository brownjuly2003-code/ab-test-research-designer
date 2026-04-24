# CX Task: Sync Hugging Face Space с main @ 68c355bf

## Goal
Обновить live demo `https://liovina-ab-test-research-designer.hf.space` до текущего `main` HEAD `68c355bf` так, чтобы публичный demo показывал: template gallery (10 пресетов), LLM adapter Settings panel, Monte-Carlo distribution view в ComparisonDashboard, Plan A a11y перф фикс. Предыдущий HF sync был на `cb31cc28` (v1.1.0 baseline).

## Context
- **Repo.** `D:\AB_TEST\`, `main`, HEAD `68c355bf`. История: `68c355bf` (feat bundle Task #5/#6/#7), `04639702` (Plan A a11y), `fa9a3f23` / `880e510e` / `0c59a6bf` (docs trio), `4ea6ea1b` / `f4178dd3` (badge auto-updates), `3255df3c` (HF snapshot service).
- **HF Space repo.** `liovina/ab-test-research-designer`, Docker SDK.
- **Local HF token.** `C:\Users\uedom\.cache\huggingface\token` — работает без prompt'а.
- **Staging dir.** `C:\Users\uedom\AppData\Local\Temp\hf-push` — clean, recreate.
- **Новое в этом sync (vs `cb31cc28`):**
  - Backend: `app/backend/app/services/monte_carlo_service.py`, `app/backend/app/llm/openai_adapter.py` + `anthropic_adapter.py`, обновления в `routes/projects.py` (MC query params), `routes/analysis.py` (LLM provider routing), `main.py` (CORS для `X-AB-LLM-Provider` / `X-AB-LLM-Token`), `logging_utils.py` (token masking), `schemas/api.py` (MonteCarloSimulationResponse), `snapshot_service.py` (HF Dataset SQLite persistence — НЕ включать HF_TOKEN на HF Space, оставить snapshot opt-in через env vars).
  - Backend templates: 5 новых YAML в `app/backend/templates/` (total 10 presets).
  - Frontend: `components/ComparisonDashboard/DistributionView.tsx` + `.test.tsx`, `components/Settings/llm-provider.tsx` + `.test.tsx`, `components/TemplateGallery.tsx` правки, обновления в `SidebarPanel.tsx`, `ComparisonDashboard.tsx`, `WizardPanel.tsx`, `lib/api.ts`, `lib/generated/api-contract.ts`, `i18n/*.json` (4 локали: monteCarlo + llm + templateGallery keys).
  - Docs: `docs-site/features/comparison.md` (distribution view), `docs-site/features/llm-adapter.md` (новый), `docs-site/features/wizard.md`, `docs-site/getting-started/quickstart.md`, `mkdocs.yml`, `README.md` (roadmap update).
  - `docs-site/assets/screenshots/comparison-distribution-view.png` (2.0MB) — **не** пушить на HF, оставить только на GitHub raw.
- **Binary policy.** HF отклоняет binary >LFS threshold. Исключать `docs/demo/*.png`, `docs-site/assets/screenshots/*.png`, `*.sqlite3` / `*.db`, `badges/*.json`, `node_modules/`, `.git/`, `.github/`, `.ci-artifacts/`, `.coverage`, `docs/plans/`, `archive/`, `exports/`, `.env*`.
- **README image rewrite** (как было в прошлый HF sync). Все `docs/demo/*.png` refs → `https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/docs/demo/<file>.png`. Аналогично `docs-site/assets/screenshots/*.png` → `https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/docs-site/assets/screenshots/<file>.png`.

## Deliverables

1. **Build frontend dist под текущий main.**
   ```bash
   npm --prefix app/frontend ci
   npm --prefix app/frontend run build
   ```
   `app/frontend/dist/` должен содержать index.html + assets/ с актуальной bundle.

2. **Stage HF push.**
   - Clean `C:\Users\uedom\AppData\Local\Temp\hf-push`.
   - Copy working tree за исключением excluded списка (см. Context).
   - Include `app/frontend/dist/` (backend FastAPI mount'ит его как static в HF Docker).
   - Rewrite README image refs (см. Context).

3. **Upload via `huggingface_hub`.**
   ```python
   from huggingface_hub import HfApi
   HfApi().upload_folder(
       repo_id="liovina/ab-test-research-designer",
       repo_type="space",
       folder_path=r"C:\Users\uedom\AppData\Local\Temp\hf-push",
       commit_message="sync main@68c355bf — template gallery + LLM adapter + Monte-Carlo distribution view + a11y perf",
   )
   ```
   Token читается из `~/.cache/huggingface/token` автоматически.

4. **Verify** (HF rebuild занимает 2-5 мин — poll пока не станет готов):
   - `GET /health` → 200, `{"version":"1.1.0"}`.
   - `GET /api/v1/projects` → `total > 0` (seeded workspace).
   - `GET /api/v1/templates` → ровно 10 built-in templates (проверить имена содержат `email_campaign`, `trial_to_paid` и остальные 3 новых).
   - `POST /api/v1/projects/compare?include_monte_carlo=true&monte_carlo_simulations=1000` с payload на 2 seeded project_ids → response содержит `monte_carlo_distribution` c `num_simulations=1000`.
   - Open root в browser (или curl → grep) — README image refs должны резолвиться через raw.githubusercontent.com.

5. **Cleanup staging dir.**

6. **Report `docs/plans/2026-04-23-hf-sync-post-mc-report.md`.** Содержание:
   - Synced commit: `68c355bf`.
   - HF Space build status + время до зелёного.
   - Curl outputs `/health`, `/api/v1/projects` (total), `/api/v1/templates` (count + names), `/api/v1/projects/compare?include_monte_carlo=true` (keys в response).
   - Staging dir file count (sanity).
   - Любые rejection'ы от HF (binary size, etc.) — отдельно.

## Acceptance
- `curl https://liovina-ab-test-research-designer.hf.space/api/v1/templates | jq '.items | length'` = 10.
- `curl https://liovina-ab-test-research-designer.hf.space/health` = 200 + `version: 1.1.0`.
- Report file закоммичен в `main` одним коммитом: `docs: sync HF Space with main@68c355bf`.
- Staging dir удалён после upload'а.
- На HF Space README image refs не битые (через raw.githubusercontent.com).

## Notes
- **НЕ** push'ить на GitHub remote кроме report'а.
- **НЕ** uploading `docs/demo/*.png` или `docs-site/assets/screenshots/*.png` — оставить только raw GitHub.
- **НЕ** uploading `badges/*.json`.
- **НЕ** uploading `app/backend/data/` (runtime SQLite).
- HF snapshot service (`AB_HF_SNAPSHOT_REPO` / `AB_HF_TOKEN`) — **не настраивать на HF Space**, оставить opt-in. HF Space не должен писать себе же в snapshot — это цикл.
- Если binary rejection — log путь, exclude'ить, ретрай.
- Если `npm run build` долгое / ломается — `npm ci` в `app/frontend` заново.
- Healthcheck в Dockerfile уже respect'ит `PORT` — не трогать.

## Out of scope
- Изменения `main` исходников (кроме report файла).
- Upgrade HF hardware.
- GitHub→HF auto-sync webhook (отдельный follow-up).
