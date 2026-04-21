# CX Task: Archive hygiene — gitignore runtime artefacts, rescue historical docs

## Goal
Очистить `D:\AB_TEST\archive\` и корневые untracked остатки от шумовых diagnostic runs; решить какие исторические файлы сохранить в истории Git, какие — оставить untracked навсегда. Без правок кода и тестов.

## Context
- Запускать **после** `2026-04-21-cx-post-phase-2-commit-wave.md` (post-Phase-2 волна должна быть залита).
- В `archive/` сейчас копится:
  - Run-артефакты (создаются скриптами verify): `archive/e2e-runs/`, `archive/manual-smoke-runs/`, `archive/smoke-runs/`, `archive/verify-workspace-backup/` — это timestamped папки, постоянно растут. Не нужны в истории.
  - Исторические docs (один раз созданы): `archive/audit.md`, `archive/rec.md`, `archive/questions.md`, `archive/prompt_for_github.md`, `archive/ab_test_for_gihub.md` — может быть ценны.
- Плюс корневые untracked, которые уже попали в `.gitignore` во время Phase 2 cleanup: `tmp/`, `.hypothesis/`, `.qa/`, `.docker-cli/`. Проверить что они действительно в `.gitignore` и в истории.

## Deliverables
1. `.gitignore` расширен чтобы покрыть run-артефакт-директории в `archive/` (conditional: только паттерны `archive/e2e-runs/**`, `archive/manual-smoke-runs/**`, `archive/smoke-runs/**`, `archive/verify-workspace-backup/**`). Отдельные `.md` файлы в `archive/` **не** игнорируются.
2. Решение по историческим archive .md-файлам: commit или оставить untracked. **Default: commit** (они будут ценным контекстом для будущих CX-задач).
3. Один коммит: `chore: ignore archive run artefacts, restore historical docs`.
4. Финальный `git status --short` возвращает пусто (или только папки, покрытые `.gitignore`).
5. `scripts\verify_all.cmd` после коммита = exit 0 (не --with-e2e, достаточно базы).

## Acceptance
- `git log --oneline -2` показывает этот коммит на HEAD.
- `git check-ignore archive/e2e-runs/20260421-015318` возвращает match.
- `git ls-files archive/` не содержит diagnostic runs.
- Исторические `.md` в `archive/` либо в `git ls-files` (committed), либо явно отмечены в commit-msg как «оставлены untracked по решению».
- `scripts\verify_all.cmd` = 0.

## Runbook
1. `cd D:\AB_TEST`, `git status --short` — подтвердить baseline.
2. Дополнить `.gitignore`:
   ```
   # archive run artefacts (timestamped diagnostic runs)
   archive/e2e-runs/
   archive/manual-smoke-runs/
   archive/smoke-runs/
   archive/verify-workspace-backup/
   ```
3. `git check-ignore archive/e2e-runs/<some-timestamped-dir>` — подтвердить match.
4. Если run-артефакты уже затрекены (маловероятно, но проверить `git ls-files archive/e2e-runs/`) — `git rm -r --cached archive/e2e-runs/ archive/manual-smoke-runs/ archive/smoke-runs/ archive/verify-workspace-backup/`.
5. `git add archive/audit.md archive/rec.md archive/questions.md archive/prompt_for_github.md archive/ab_test_for_gihub.md` (если решили commit).
6. `git add .gitignore`.
7. `git diff --cached --stat` — проверить что diff ≤ 10 файлов.
8. `git commit -m "chore: ignore archive run artefacts, restore historical docs" -m "" -m "Co-Authored-By: Codex <noreply@anthropic.com>"`
9. `scripts\verify_all.cmd` — exit 0.
10. `git status --short` — должно быть пусто.

## Notes
- **Не** удалять папки с диска. Только gitignore.
- **Не** трогать `tmp/`, `.hypothesis/`, `.qa/`, `.docker-cli/` в `.gitignore` (уже должны быть покрыты post-Phase-2 коммитом).
- Если `.qa/` не в `.gitignore` — добавить; если есть — оставить.
- Если решаем **не** commit-ить исторические md — в commit-msg добавить секцию `# Skipped`: `archive/audit.md, archive/rec.md, … оставлены untracked по решению` и в отдельный коммит не делать.
- **Не** пушить.

## Out of scope
- Реорганизация `archive/` структуры
- Новые фичи, рефакторы, тесты
