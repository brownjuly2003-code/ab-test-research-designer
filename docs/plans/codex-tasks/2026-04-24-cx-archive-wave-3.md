# CX Task: Archive wave 3 landed CX specs (cleanup тех что пропустил wave 2)

## Goal
Переместить 4 landed CX спека из `docs/plans/codex-tasks/` в `archive/2026-04-24-landed-cx-specs-wave-3/`. Это cleanup недосмотра wave-2 спека (`a7ef3116`) — он не включил 3 older landed спека + сам wave-2 спек. После этого active `docs/plans/codex-tasks/` содержит только roadmap файлы (bcg-*.md, phase-*.md, index.md) + сам wave-3 (в wave-4 позже).

## Context
- **Repo.** `D:\AB_TEST\`, `main`, HEAD `a7ef3116` (или новее — не rebase).
- **Landed spec files to move** (все landing commit hashes уже в main history):
  - `2026-04-23-cx-archive-landed-specs.md` - landed в `45079631` (wave 1 archive — 27 файлов в `archive/2026-04-23-landed-cx-specs/`).
  - `2026-04-23-cx-hf-sync-post-mc.md` - landed в `84642af8` (HF Space sync с main@68c355bf, `AB_SEED_DEMO_ON_STARTUP=true`).
  - `2026-04-23-cx-locales-fr-zh-ar.md` - landed в `d72356cd` (fr/zh/ar locales + RTL для ar, 913 leaf keys на locale).
  - `2026-04-24-cx-archive-wave-2.md` - landed в `a7ef3116` (wave 2 archive для bundle/hypothesis/postgres/slack specs).
  - `2026-04-24-cx-archive-wave-3.md` - этот файл. В archive попадает следующим cleanup'ом (wave 4), если он когда-либо понадобится.
- **Останутся active после task'а:** только `bcg-*.md`, `phase-*.md`, `index.md` (roadmap reference docs) + сам wave-3 спек. **Ни одного queued CX таска** - значит следующих CX-прогонов в пайплайне нет.
- **НЕ трогать:** `bcg-*.md`, `phase-*.md`, `index.md`, `wave-3.md` (себя).

## Baseline (измерить перед началом)
```bash
cd D:\AB_TEST
git log --oneline -1
ls docs/plans/codex-tasks/2026-04-2[34]-cx-*.md
ls docs/plans/codex-tasks/2026-04-2[34]-cx-*.md | wc -l
git ls-files archive/ | wc -l
```
Ожидание: HEAD `a7ef3116`+, 5 файлов в фильтре (4 для перемещения + сам этот wave-3). Запиши в первой строке отчёта. Если HEAD старее `a7ef3116` или файлов не 5 — stop and report (спек устарел, пересмотреть список).

## Shared-file check
- Файлы задачи: только перемещения внутри `archive/` и `docs/plans/codex-tasks/`.
- `docs/plans/codex-tasks/index.md` трогается ТОЛЬКО если `grep -l "2026-04-23-cx-archive-landed-specs\|2026-04-23-cx-hf-sync-post-mc\|2026-04-23-cx-locales-fr-zh-ar\|2026-04-24-cx-archive-wave-2" docs/plans/codex-tasks/index.md` возвращает hits.
- Перед началом `git status --short`: ожидание ЛИБО пусто, ЛИБО только `?? docs/plans/codex-tasks/2026-04-24-cx-archive-wave-3.md` (этот файл). Любые другие modified/untracked — параллельная сессия, STOP.

## Deliverables

1. **Создать** `archive/2026-04-24-landed-cx-specs-wave-3/` директорию.

2. **Переместить 4 спека через `git mv`:**
   ```bash
   git mv docs/plans/codex-tasks/2026-04-23-cx-archive-landed-specs.md archive/2026-04-24-landed-cx-specs-wave-3/
   git mv docs/plans/codex-tasks/2026-04-23-cx-hf-sync-post-mc.md      archive/2026-04-24-landed-cx-specs-wave-3/
   git mv docs/plans/codex-tasks/2026-04-23-cx-locales-fr-zh-ar.md     archive/2026-04-24-landed-cx-specs-wave-3/
   git mv docs/plans/codex-tasks/2026-04-24-cx-archive-wave-2.md       archive/2026-04-24-landed-cx-specs-wave-3/
   ```

3. **Написать `archive/2026-04-24-landed-cx-specs-wave-3/README.md`** с one-liner на каждый спек:
   ```
   # Wave 3 archived CX specs (landed, moved 2026-04-24)

   - 2026-04-23-cx-archive-landed-specs.md — landed 45079631 (wave 1: 27 files moved to archive/2026-04-23-landed-cx-specs/)
   - 2026-04-23-cx-hf-sync-post-mc.md — landed 84642af8 (HF Space sync with main@68c355bf, AB_SEED_DEMO_ON_STARTUP=true, Monte-Carlo endpoint live)
   - 2026-04-23-cx-locales-fr-zh-ar.md — landed d72356cd (fr/zh/ar locales + RTL for ar, 913 leaf keys per locale)
   - 2026-04-24-cx-archive-wave-2.md — landed a7ef3116 (wave 2: 4 specs — bundle/hypothesis/postgres/slack — to archive/2026-04-24-landed-cx-specs-wave-2/)
   ```

## Hardcoded counts sync
После move проверить что в docs / README / mkdocs / app / scripts нет ссылок на перемещаемые пути:
```bash
grep -rn "codex-tasks/2026-04-2[34]-cx-\(archive-landed-specs\|hf-sync-post-mc\|locales-fr-zh-ar\|archive-wave-2\)" \
  docs/ README.md mkdocs.yml app/ scripts/ 2>/dev/null
```
Каждый hit обновить на новый archive path или снести если ссылка устарела. Ожидание: пусто или несколько hits в `docs/plans/*-report.md` (безопасно обновить).

## Commit gates (do ALL before commit)
1. `git status --short` — только 4 R100 rename'а + новый README + сам `wave-3.md` как `??`.
2. `ls archive/2026-04-24-landed-cx-specs-wave-3/ | wc -l` = 5 (4 spec'а + README).
3. `ls docs/plans/codex-tasks/ | grep "2026-04-2[34]-cx-" | wc -l` = 1 (только `wave-3.md` сам).
4. `git log --stat --name-status -- archive/2026-04-24-landed-cx-specs-wave-3/` показывает R100 на 4 файлах.
5. Никаких модификаций вне `docs/plans/codex-tasks/` + `archive/` + опциональный `index.md`.

## Commit
Один коммит, explicit pathspec:
```bash
git add archive/2026-04-24-landed-cx-specs-wave-3/
# move'ы уже staged через git mv
# index.md если обновлялся:
git add docs/plans/codex-tasks/index.md
# wave-3.md НЕ стейджим — он останется untracked до wave-4
git commit -m "chore(docs): archive wave 3 landed CX task specs (cleanup wave-2 miss)"
```

Subject: `chore(docs): archive wave 3 landed CX task specs (cleanup wave-2 miss)`.

## Push
```bash
git fetch origin main   # auto badge-metrics commits иногда опережают
git pull --rebase origin main   # если есть divergence — штатно
git push origin main
```

Если CI `Tests` workflow не зелёный на этот commit — report и не продолжать.

## Acceptance
- `ls docs/plans/codex-tasks/ | grep "2026-04-2[34]-cx-"` возвращает ровно 1 файл (`2026-04-24-cx-archive-wave-3.md`).
- `ls archive/2026-04-24-landed-cx-specs-wave-3/ | wc -l` = 5.
- `git log --stat -1` показывает R100 на 4 rename'ах + добавленный README.
- CI `Tests` run на main = success.
- `git status --short` = только `?? docs/plans/codex-tasks/2026-04-24-cx-archive-wave-3.md` после push.

## Report
10-15 строк: baseline numbers, 4 commit hashes от перемещённых спеков, CI run id + conclusion, любые grep hits которые требовали обновления ссылок.

## Notes
- **`git mv` а не cp+rm** — сохраняет blame и размер diff.
- **НЕ** менять содержимое перемещаемых файлов.
- **НЕ** включать `wave-3.md` в этот коммит (он останется active reference до wave-4 если когда-либо).
- Commit scope: только archive rename + README + optional index.md update. Ничего больше.

## Out of scope
- Waves 1 и 2 (уже archived в `45079631` и `a7ef3116`).
- Чистка `docs/plans/*-report.md` report файлов — отдельная hygiene если понадобится.
- Split `docs-site/` vs `docs/` структуры — отдельно.
