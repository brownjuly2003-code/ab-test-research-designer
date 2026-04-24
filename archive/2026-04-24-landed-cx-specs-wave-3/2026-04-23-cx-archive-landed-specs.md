# CX Task: Archive landed CX specs из post-v1.1 волны

## Goal
Переместить landed CX task спеки из `docs/plans/codex-tasks/` в `archive/2026-04-23-landed-cx-specs/`, чтобы активная директория содержала только queued / in-flight задачи. Следовать прецеденту `df3a8c10` (archive loose docs + BCG planning).

## Context
- **Repo.** `D:\AB_TEST\`, `main`, HEAD `68c355bf` (или новее — не rebase).
- **Текущий каталог.** `docs/plans/codex-tasks/` содержит ~20 спеков 2026-04-21..04-23 + `bcg-*.md` + `phase-*.md` + `index.md`.
- **Landed specs (нужно переместить):**
  - `2026-04-21-cx-a11y-audit.md`
  - `2026-04-21-cx-archive-hygiene.md`
  - `2026-04-21-cx-commit-phase-1-2.md`
  - `2026-04-21-cx-lighthouse-ci.md`
  - `2026-04-21-cx-phase-2-gap-check.md`
  - `2026-04-21-cx-post-phase-2-commit-wave.md`
  - `2026-04-21-cx-release-v1.md`
  - `2026-04-22-cx-advanced-viz.md`
  - `2026-04-22-cx-bcg-plan-sync.md`
  - `2026-04-22-cx-comparison-dashboard.md`
  - `2026-04-22-cx-demo-hosting-prep.md`
  - `2026-04-22-cx-docker-publish-readiness.md`
  - `2026-04-22-cx-dynamic-badges.md`
  - `2026-04-22-cx-fix-line-endings.md`
  - `2026-04-22-cx-ghcr-publish.md`
  - `2026-04-22-cx-i18n-full.md`
  - `2026-04-22-cx-integrations-webhooks.md`
  - `2026-04-22-cx-locales-de-es.md`
  - `2026-04-22-cx-property-based-tests.md`
  - `2026-04-23-cx-apply-a11y-perf-plan-a.md` (landed в `04639702`)
  - `2026-04-23-cx-monte-carlo-comparison.md` (landed в `68c355bf`)
  - `2026-04-22-cx-hf-sync-seed.md` (outdated — superseded by `2026-04-23-cx-hf-sync-post-mc.md`)
- **Остаются в `docs/plans/codex-tasks/`:**
  - `2026-04-23-cx-hf-sync-post-mc.md` (active — queued)
  - `2026-04-23-cx-archive-landed-specs.md` (этот файл — после выполнения переедет в archive в следующем cleanup)
  - `2026-04-23-cx-locales-fr-zh-ar.md` (queued)
  - `bcg-p1-index.md`, `index.md`, `phase-*.md` — это roadmap / reference docs, НЕ трогать.

## Deliverables
1. **Создать** `archive/2026-04-23-landed-cx-specs/` директорию.
2. **Переместить** 22 landed файла из списка выше через `git mv` (сохраняет blame/history).
3. **Написать** `archive/2026-04-23-landed-cx-specs/README.md` — one-liner на каждый спек с landed-commit hash'ем. Референс для будущего forensic анализа.
4. **Обновить** `docs/plans/codex-tasks/index.md` (если ссылается на перемещённые — убрать ссылки или пометить archive).
5. **Один коммит:** `chore(docs): archive 22 landed CX task specs (post-v1.1 wave through Tier 2/3)`.
6. **Push** на origin/main.

## Acceptance
- `ls docs/plans/codex-tasks/ | wc -l` уменьшился на 22.
- `ls archive/2026-04-23-landed-cx-specs/ | wc -l` = 23 (22 specs + README).
- `git log --stat -- archive/2026-04-23-landed-cx-specs/` показывает rename'ы (не delete+add).
- `git ls-files docs/plans/codex-tasks/ | grep -E "2026-04-2[123]-cx-"` возвращает только 3 файла: `cx-hf-sync-post-mc.md`, `cx-archive-landed-specs.md`, `cx-locales-fr-zh-ar.md`.
- CI `Tests` workflow проходит зелёным (docs-only коммит — должен пройти быстро).
- `git status --short` = пусто после push.

## Notes
- **`git mv` а не cp+rm** — сохраняет history и размер diff'а.
- **`index.md` hygiene** — если этот файл поддерживает list of active specs, refresh его. Если не поддерживает — игнорировать.
- **НЕ** менять содержимое перемещаемых файлов. Только move.
- **НЕ** трогать `bcg-*.md` / `phase-*.md` / `index.md` (кроме ссылок на archived — и то аккуратно).
- **Коммит scope:** только archive move + README + optional index update. Больше ничего в этот коммит.

## Out of scope
- Любые правки в `archive/` прошлых лет / других волн.
- Чистка `docs/plans/*.md` report файлов (они уже в `docs/plans/`, отдельная hygiene задача).
- Split `docs-site/` vs `docs/` — отдельно.
