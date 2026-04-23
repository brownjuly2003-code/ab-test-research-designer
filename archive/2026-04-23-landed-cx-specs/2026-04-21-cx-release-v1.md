# CX Task: Ship v1.0.0 — CHANGELOG, version bump, release tag, deployment-readiness check

## Goal
Зафиксировать текущее состояние `D:\AB_TEST\` как релизную точку `v1.0.0`: обновить CHANGELOG, согласовать версии (frontend/backend/Docker), создать git tag, прогнать полный Docker verification, написать release notes.

## Context
- Репо: `D:\AB_TEST\`, HEAD = `4b28afb5 "docs: mark post-Phase-2 wave complete and index CX tasks"`. Не создавать новую ветку, работать на `main`.
- Remote пустой (`git remote -v` → пусто). Tag создаётся локально; push отдельным решением юзера.
- Текущие версии:
  - `app/backend/app/main.py` и `app/backend/app/config.py` — ищи `app_version` / `"0.1.0"`.
  - `app/frontend/package.json` — `"version": "0.1.0"` (проверь).
  - `Dockerfile` — если есть `LABEL version=...`.
  - `docs/API.md` header — если содержит версию.
- Verify-pipeline зелёный на HEAD: backend 165 pytest, frontend 160 unit, typecheck, build, smoke, e2e, workspace backup checksum+signed, benchmark (p95 ~0.005ms). Docker verification (`scripts/verify_docker_compose.py`) сейчас не запущен автоматически, но `scripts\verify_all.cmd --with-docker` должен проходить.
- Фичи, landed в 8 коммитах с `8413328e` по `4b28afb5`:
  - BCG Phase 1 refactor (Zustand stores, decomposed App/Results)
  - Phase 2 visual transformation (Recharts, themes, skeletons, Lucide)
  - Phase 3 stats: multi-metric guardrails, SRM, Bayesian, sequential, CUPED
  - Phase 3.4 shareable reports (PDF export, chart export)
  - Template gallery (5 yaml пресетов)
  - Project filters + keyboard shortcut help
  - Audit log endpoint + request trail
  - Lighthouse config (но не wired в CI — отдельный таск)
  - i18n scaffolding (en.json)

## Deliverables
1. Обновить `CHANGELOG.md`:
   - Новая секция `## [1.0.0] - 2026-04-21` над текущей историей.
   - Под ней три подраздела: `### Added`, `### Changed`, `### Fixed`. Каждый пункт со ссылкой на коммит (первые 7 символов) или на соответствующую phase-таску.
   - Использовать Keep-a-Changelog стиль (если CHANGELOG уже в этом стиле — продолжить; если нет — придерживаться существующего шаблона, не переделывать файл).
2. Version bump до `1.0.0`:
   - `app/frontend/package.json` → `"version": "1.0.0"`.
   - `app/frontend/package-lock.json` — автоматически через `npm install --package-lock-only` (не пересоздавать lock).
   - `app/backend/app/config.py` — `app_version` на `"1.0.0"`.
   - `app/backend/app/main.py` — если hardcoded строка `"0.1.0"`, заменить.
   - `Dockerfile` — если есть LABEL, обновить.
   - Regen `docs/API.md` через `python scripts/generate_api_docs.py` (если нужно — `--check` должен пройти после).
3. Release notes `docs/RELEASE_NOTES_v1.0.0.md`:
   - Executive summary (2–3 абзаца, non-tech аудитория).
   - Capability matrix: «Что умеет» таблица с колонками feature / status / notes.
   - Known limitations (a11y — awaiting axe full audit, lighthouse — not yet in CI, LLM advice optional).
   - Upgrade path (для 0.x не применимо — это первый релиз; напиши «No migration required — v1.0.0 is the first stable release»).
   - Verification commands (как проверить установку локально).
4. Полный Docker verification:
   - `scripts\verify_all.cmd --with-docker` = exit 0. Захватить stdout → `docs/plans/2026-04-21-v1-docker-verify.log`.
   - Или non-destructive: `python scripts/verify_docker_compose.py --preserve` + `curl 127.0.0.1:8008/health` → 200.
5. Git tag:
   - `git tag -a v1.0.0 -m "Release 1.0.0 — BCG Phase 1..5 complete"`
   - `git show v1.0.0` должно отображать annotated tag с сообщением.
   - **Не** push'ить tag (юзер решит).
6. Один коммит (до тега): `release: v1.0.0 — CHANGELOG, version bump, release notes`.
7. Финальный отчёт `docs/plans/2026-04-21-release-v1-report.md`:
   - `git log --oneline -3`
   - `git tag -l -n5 v1.0.0`
   - Результат `scripts\verify_all.cmd --with-e2e --with-docker`
   - Блок «Не попало в v1.0.0 / deferred to v1.1» (список из отдельных пунктов: Lighthouse CI, a11y full audit, если они не были сделаны до этого).

## Acceptance
- `git log --oneline -1` = `release: v1.0.0 — CHANGELOG, version bump, release notes`.
- `git tag -l v1.0.0` возвращает one line; `git cat-file -t v1.0.0` = `tag` (annotated).
- `CHANGELOG.md` содержит `## [1.0.0]` секцию с датой `2026-04-21` и не пустой.
- `app/frontend/package.json:version == "1.0.0"`, backend `app_version == "1.0.0"`.
- `scripts\verify_all.cmd --with-e2e --with-docker` = exit 0.
- `python scripts/generate_api_docs.py --check` = 0 (docs/API.md актуален под новую версию).
- `docs/RELEASE_NOTES_v1.0.0.md` и отчёт присутствуют.
- Commit содержит `Co-Authored-By: Codex <noreply@anthropic.com>`.

## How
1. `cd D:\AB_TEST`, `git status --short` → пусто (подтвердить baseline).
2. Найти все строки версии:
   - `grep -rn "0.1.0" app/backend/app/ app/frontend/package.json Dockerfile CHANGELOG.md docs/API.md`
3. Обновить их на `1.0.0`. `docs/API.md` регенерировать через `python scripts/generate_api_docs.py`.
4. Обновить `CHANGELOG.md` — собрать список изменений через `git log c29ab0d7..HEAD --oneline`.
5. Написать `docs/RELEASE_NOTES_v1.0.0.md`.
6. Запустить `scripts\verify_all.cmd --with-e2e --with-docker` и сохранить логи. Если Docker verification падает (например, порт занят, docker daemon недоступен) — **не** маскировать. Если это среда без Docker — использовать `scripts\verify_all.cmd --with-e2e`, а Docker пункт пометить в report как deferred.
7. Коммит: `release: v1.0.0 — CHANGELOG, version bump, release notes`.
8. Tag: `git tag -a v1.0.0 -m "..."`.
9. Написать отчёт.

## Notes
- **Не** пушить на remote. **Не** `git push --tags`.
- **Не** использовать `--amend`, `--force`, `reset --hard` если что-то пошло не так — сделать новый откатный коммит.
- **Не** менять structure CHANGELOG.md — только добавить новую секцию.
- Если Docker недоступен в CX-среде (нет docker daemon / нельзя запустить compose) — документировать как «Docker verify deferred, run locally before push». Это не блокер acceptance, но должно быть явно в отчёте.
- Если `generate_api_docs.py` после version bump меняет docs/API.md — включить diff в тот же коммит; `--check` после коммита должен проходить.
- Backend test_performance p95-guard может флапнуть — перезапустить один раз.
- `requirements.txt` трогать **не надо** — это отдельный bump.

## Out of scope
- Push на remote / создание GitHub Release
- Hosting демо (отдельный таск, если будет)
- SemVer-анализ breaking changes (первый релиз — не применимо)
- CI updates (не рилейтед к версии)
