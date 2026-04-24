# CX Task: Archive wave 2 landed CX specs

## Goal
Переместить 4 landed CX task спека из `docs/plans/codex-tasks/` в `archive/2026-04-24-landed-cx-specs-wave-2/`, чтобы active директория держала только queued / in-flight задачи. Продолжение прецедента `45079631` (wave 1, 27 files, 2026-04-23).

## Context
- **Repo.** `D:\AB_TEST\`, `main`, HEAD `fc93a0f6` (или новее — не rebase).
- **Landed spec files to move** (все уже отражены в main history):
  - `2026-04-23-cx-bundle-optimization.md` - landed в `28bd2fbc` (bundle -50%).
  - `2026-04-23-cx-hypothesis-edge-cases.md` - landed в `8b235f45` + `80e20961` (тест + fix обнаруженного bug'а).
  - `2026-04-23-cx-postgres-backend.md` - landed в `4dbcef63` (bundled with slack).
  - `2026-04-23-cx-slack-app.md` - landed в `4dbcef63` (bundled with postgres).
  - `2026-04-24-cx-archive-wave-2.md` - этот файл. В archive попадает после выполнения следующим cleanup'ом (wave 3).
- **Остаются active** после этого таска: пусто (backlog доработан). Если новые спеки появляются позже - работают независимо.
- **НЕ трогать:** `bcg-*.md`, `phase-*.md`, `index.md` - это roadmap / reference, не CX task'и.

## Baseline (измерить перед началом)
```bash
ls docs/plans/codex-tasks/ | grep -E "^2026-04-2[34]-cx-" | wc -l
ls docs/plans/codex-tasks/2026-04-23-cx-bundle-optimization.md \
   docs/plans/codex-tasks/2026-04-23-cx-hypothesis-edge-cases.md \
   docs/plans/codex-tasks/2026-04-23-cx-postgres-backend.md \
   docs/plans/codex-tasks/2026-04-23-cx-slack-app.md
git log --oneline -1
```
Запиши выводы в первой строке отчёта. Если файлов не 4 (plus этот) или HEAD не `fc93a0f6`+ - stop and report.

## Shared-file check
- `docs/plans/codex-tasks/index.md` - трогается редко, но проверить `git status --short` перед началом.
- Другие файлы не затрагиваются этим таском; если `git status` показывает modifications вне `docs/plans/` - stop, параллельная сессия в работе.

## Deliverables
1. **Создать** `archive/2026-04-24-landed-cx-specs-wave-2/` директорию.
2. **Переместить** 4 спека через `git mv` (сохраняет blame):
   ```bash
   git mv docs/plans/codex-tasks/2026-04-23-cx-bundle-optimization.md      archive/2026-04-24-landed-cx-specs-wave-2/
   git mv docs/plans/codex-tasks/2026-04-23-cx-hypothesis-edge-cases.md    archive/2026-04-24-landed-cx-specs-wave-2/
   git mv docs/plans/codex-tasks/2026-04-23-cx-postgres-backend.md         archive/2026-04-24-landed-cx-specs-wave-2/
   git mv docs/plans/codex-tasks/2026-04-23-cx-slack-app.md                archive/2026-04-24-landed-cx-specs-wave-2/
   ```
3. **Написать** `archive/2026-04-24-landed-cx-specs-wave-2/README.md` - one-liner на каждый спек с landing commit hash'ем:
   ```
   - 2026-04-23-cx-bundle-optimization.md - landed 28bd2fbc (main chunk 247.88->122.18 KB gzip)
   - 2026-04-23-cx-hypothesis-edge-cases.md - landed 8b235f45 (+80e20961 bug fix)
   - 2026-04-23-cx-postgres-backend.md - landed 4dbcef63 (with slack app, bundled)
   - 2026-04-23-cx-slack-app.md - landed 4dbcef63 (with postgres backend, bundled)
   ```
4. **Обновить** `docs/plans/codex-tasks/index.md` только если он ссылается на перемещаемые файлы (проверить `grep -l`).

## Hardcoded counts sync
- После move проверить что в docs / README / CLAUDE нет ссылок на пути перемещённых файлов:
  ```bash
  grep -rn "codex-tasks/2026-04-23-cx-\(bundle-optimization\|hypothesis-edge-cases\|postgres-backend\|slack-app\)" \
    docs/ README.md mkdocs.yml app/ scripts/ 2>/dev/null
  ```
- Обновить найденные ссылки на новый archive path.

## Commit gates (do ALL before commit)
1. `git status --short` содержит ТОЛЬКО 4 move'а + README + опционально `index.md`.
2. `ls archive/2026-04-24-landed-cx-specs-wave-2/` содержит 5 файлов (4 specs + README).
3. `git log --stat -- archive/2026-04-24-landed-cx-specs-wave-2/` показывает rename'ы (R100), не delete+add.
4. Никаких изменений вне `docs/plans/` и `archive/` в staged diff.

## Deliverable: commit
Один коммит, explicit pathspec:
```bash
git add \
  archive/2026-04-24-landed-cx-specs-wave-2/ \
  docs/plans/codex-tasks/index.md   # только если обновлён
# (moves уже в index через git mv)
git commit -m "chore(docs): archive wave 2 landed CX task specs"
```

Subject: `chore(docs): archive wave 2 landed CX task specs`.

## Push
```bash
git push origin main
```
CI run ожидается зелёным (docs-only change). Если не зелёный - report и не продолжать.

## Acceptance
- `ls docs/plans/codex-tasks/ | grep "2026-04-23-cx-"` = пусто.
- `ls docs/plans/codex-tasks/ | grep "2026-04-24-cx-"` = 1 file (этот).
- `ls archive/2026-04-24-landed-cx-specs-wave-2/ | wc -l` = 5.
- `git log --stat -1 --name-status` показывает R100 на 4 move'ах.
- CI `Tests` run на main зелёный.
- `git status --short` = пусто после push.

## Report
Короткий (10-15 строк): baseline numbers, count landed вместе с их commit hashes, CI run id + conclusion, любые grep hits которые требовали обновления ссылок.

## Notes
- **`git mv` а не cp+rm** - сохраняет history.
- **НЕ** менять содержимое перемещаемых файлов.
- **НЕ** трогать `bcg-*.md` / `phase-*.md` / `index.md` если не требуется обновление ссылок.
- Commit scope: только archive move + README + optional index.md.
- Если auto-push badge-metrics commit опередил на remote перед push - `git pull --rebase origin main` + retry push, это штатно.

## Out of scope
- Wave 1 archive cleanup - уже сделано в `45079631`.
- Чистка `docs/plans/*.md` report файлов (отдельная hygiene).
- Split `docs-site/` vs `docs/` структуры.
