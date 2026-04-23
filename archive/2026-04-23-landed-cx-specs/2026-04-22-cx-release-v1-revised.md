# CX Task (revised): Ship v1.0.0 — complete the release, sweep stale task docs, tag

## Goal
Зафиксировать `D:\AB_TEST\` как `v1.0.0`: обновить версии (frontend + backend), написать CHANGELOG entry и release notes, подобрать в коммит все untracked CX-таск файлы из `docs/plans/codex-tasks/`, создать annotated git tag, прогнать verify. Предыдущий запуск таска (`2026-04-21-cx-release-v1.md`) был пропущен — этот — обязательный.

## Context
- Репо: `D:\AB_TEST\`. Работать на `main`, НЕ создавать новую ветку. Remote пустой (`git remote -v`), push не делается.
- HEAD сейчас: смотри `git log --oneline -1`. Ожидается что-то вроде `9882d079` (`feat: expand axe a11y coverage...` timing fix) или более поздний, **если появились новые коммиты — работать поверх реального HEAD**.
- Verify-pipeline на текущем HEAD должен быть зелёным до начала работы: `scripts\verify_all.cmd --with-e2e` = 0. Если нет — **остановиться и сообщить**; этот таск не про отладку чужих багов.
- Состояние работ на 2026-04-22:
  - BCG Phase 1..5 landed в 10+ коммитах с `8413328e` по HEAD
  - A11y axe-покрытие расширено (wizard / results / sidebar / modals), 184 frontend тестов
  - Lighthouse CI подключён (perf 0.99 / a11y 1.00 / bp 0.93 / seo 0.82 median)
  - PDF-report, template gallery (5 yaml пресетов), project filters, shortcut help, audit log — landed
  - Версии сейчас: `app/frontend/package.json` = `"version": "0.1.0"`, backend `AB_APP_VERSION` default `"0.1.0"` (см. `app/backend/app/config.py`)
- Untracked CX-таск файлы, которые **должны попасть в этот релизный коммит**:
  - `docs/plans/codex-tasks/2026-04-21-cx-a11y-audit.md`
  - `docs/plans/codex-tasks/2026-04-21-cx-lighthouse-ci.md`
  - `docs/plans/codex-tasks/2026-04-21-cx-release-v1.md` (предыдущая версия этого таска)
  - `docs/plans/codex-tasks/2026-04-22-cx-release-v1-revised.md` (этот файл)
  - любые другие `2026-04-22-cx-*.md` в этой папке
- Эти файлы описывают landed работу — история без них неполная.

## Deliverables
1. **Version bump до `1.0.0`:**
   - `app/frontend/package.json` → `"version": "1.0.0"`.
   - `app/frontend/package-lock.json` — обновить только `lockfileVersion`/root version через `npm install --package-lock-only --prefix app/frontend` (не пересоздавать lock полностью).
   - `app/backend/app/config.py` — default `AB_APP_VERSION` значение с `"0.1.0"` на `"1.0.0"`.
   - `Dockerfile` — если содержит `LABEL version=`, обновить; если нет — не добавлять.
   - Regen `docs/API.md`: `python scripts/generate_api_docs.py` (без `--check`); после регена `--check` должен проходить.

2. **`CHANGELOG.md` секция `## [1.0.0] - 2026-04-22`** над текущими записями (existing style preserve):
   - `### Added`: templates gallery, PDF/shareable reports, project filters, shortcut help, audit log, SRM/Bayesian/sequential/CUPED stats, multi-metric guardrails, Recharts visualization, theme toggle, a11y axe coverage, Lighthouse CI. Каждый пункт с коротким commit-hash.
   - `### Changed`: decomposed App/ResultsPanel, Zustand stores, Lucide icons, generated API contract, workspace backup flow.
   - `### Fixed`: (если есть релевантные — например, dup fixes) — иначе пропустить секцию.

3. **`docs/RELEASE_NOTES_v1.0.0.md`**:
   - Executive summary (2–3 абзаца, non-tech).
   - Capability matrix: таблица feature / status (GA / beta) / notes.
   - Known limitations (если LLM advice требует локального оркестратора — перечислить; a11y screen-reader manual тесты не прогонялись; prod Docker hosting не шифруется HTTPS по умолчанию).
   - Upgrade path: «No migration required — v1.0.0 is the first stable release».
   - Verification commands.

4. **Staging untracked CX-таск файлов** — все `docs/plans/codex-tasks/2026-04-21-cx-*.md` и этот файл (`2026-04-22-cx-release-v1-revised.md`) — добавить в release-коммит через `git add`.

5. **Один коммит** с сообщением строго:
   ```
   release: v1.0.0 — CHANGELOG, version bump, release notes
   ```
   **НЕ дублировать subject** прошлых коммитов. Если в `git log` уже есть `release:` коммит — остановиться и сообщить (это регрессия).

6. **Annotated git tag `v1.0.0`** с сообщением `Release 1.0.0 — BCG Phases 1..5 complete, a11y + lighthouse hardening`. **Не push-ить**.

7. **Docker verify (с fallback)**:
   - Попытаться `scripts\verify_all.cmd --with-docker` → сохранить stdout в `docs/plans/2026-04-22-v1-docker-verify.log`.
   - Если Docker daemon недоступен в CX-среде (error `Cannot connect to the Docker daemon` / `docker-compose: command not found`) — **не маскировать**, зафиксировать в отчёте как `Docker verify deferred — daemon unavailable in CX environment. Run locally before push.` Это НЕ блокирует acceptance.
   - Если Docker доступен, но compose падает — разбираться, не маскировать. Если root cause не фиксится за 15 мин — зафиксировать как blocker в отчёте и НЕ закрывать таск как done.

8. **Отчёт `docs/plans/2026-04-22-release-v1-report.md`**:
   - `git log --oneline -5`
   - `git tag -l -n5 v1.0.0` (вывод annotated tag)
   - Результаты verify: `scripts\verify_all.cmd --with-e2e` (обязательный) и `--with-docker` (если доступен).
   - Версии после bump: `package.json version`, backend `AB_APP_VERSION`, `docs/API.md` версия.
   - Блок `Deferred to v1.1`: что НЕ попало в v1 (если что-то всплыло — например, Docker undeployed, manual screen-reader audit).

## Acceptance
- `git log --oneline -1` = `release: v1.0.0 — CHANGELOG, version bump, release notes` (строго этот subject, без вариаций).
- `git tag -l v1.0.0` возвращает одну строку; `git cat-file -t v1.0.0` = `tag` (annotated, не lightweight).
- `grep '"version"' app/frontend/package.json` = `"version": "1.0.0"`.
- `grep 'app_version' app/backend/app/config.py` содержит `"1.0.0"` (default для env).
- `CHANGELOG.md` содержит `## [1.0.0]` секцию с датой `2026-04-22` и списком changes.
- `docs/RELEASE_NOTES_v1.0.0.md` присутствует, не пустой, содержит все 5 секций (summary, matrix, limitations, upgrade, verify).
- `scripts\verify_all.cmd --with-e2e` = 0 на HEAD после коммита.
- `python scripts/generate_api_docs.py --check` = 0 (docs/API.md актуален под v1.0.0).
- `git status --short` = пусто (или только намеренно untracked run-артефакты).
- `git ls-files docs/plans/codex-tasks/ | grep 2026-04-21-cx-` возвращает все прошлые CX-таск файлы (a11y, lighthouse, release-original) — они в истории.
- Commit содержит trailer `Co-Authored-By: Codex <noreply@anthropic.com>`.

## How
1. `cd D:\AB_TEST`; подтвердить baseline: `git status --short`, `git log --oneline -1`, `scripts\verify_all.cmd --with-e2e` = 0. **Если baseline не зелёный — stop, report.**
2. Найти все строки версии: `grep -rn "0\.1\.0" app/backend/app/ app/frontend/package.json Dockerfile CHANGELOG.md docs/API.md docs/RUNBOOK.md docs/ARCHITECTURE.md 2>&1`. Обновить каждую на `1.0.0`.
3. `python scripts/generate_api_docs.py`; проверить diff `docs/API.md` — только version-строка, иначе разобраться.
4. `cd app/frontend && npm install --package-lock-only` (обновит lock only для version field); `cd ../..`.
5. Собрать список коммитов для CHANGELOG: `git log c29ab0d7..HEAD --oneline` — это вся post-Phase-2 работа. Сгруппировать по Added / Changed / Fixed.
6. Написать `CHANGELOG.md` и `docs/RELEASE_NOTES_v1.0.0.md`.
7. `git status` — все ли untracked CX task файлы видны. `git add docs/plans/codex-tasks/2026-04-21-cx-*.md docs/plans/codex-tasks/2026-04-22-cx-*.md`.
8. `git add` остальных изменений (package.json, config.py, CHANGELOG, RELEASE_NOTES, docs/API.md, Dockerfile если трогали, package-lock.json).
9. `git diff --cached --stat | tail -5` — проверить scope (ожидается 10–20 файлов).
10. Commit:
    ```bash
    git commit -m "release: v1.0.0 — CHANGELOG, version bump, release notes" -m "" -m "Co-Authored-By: Codex <noreply@anthropic.com>"
    ```
11. Tag:
    ```bash
    git tag -a v1.0.0 -m "Release 1.0.0 — BCG Phases 1..5 complete, a11y + lighthouse hardening"
    ```
12. Verify: `scripts\verify_all.cmd --with-e2e` = 0. Затем попытаться `scripts\verify_all.cmd --with-docker` (с fallback по policy выше).
13. Написать отчёт `docs/plans/2026-04-22-release-v1-report.md`.
14. Финальный `git status --short` — пусто.

## Notes
- **Commit subject hygiene (важно, учитывая прошлые промахи):**
  - `git log --oneline -15 | awk -F' ' '{for(i=2;i<=NF;i++) printf "%s ", $i; print ""}' | sort | uniq -d` должно быть пусто; **если есть дубликаты — пометить в отчёте, не пытаться rewrite landed history.**
  - Subject этого коммита строго `release: v1.0.0 — CHANGELOG, version bump, release notes` — без вариаций.
- **CX-файл hygiene (учитывая прошлые промахи):** любой markdown файл из `docs/plans/codex-tasks/`, не в `git ls-files`, должен быть staged в этот коммит или явно оставлен с обоснованием в отчёте. **Нельзя закончить таск пока в `docs/plans/codex-tasks/` есть untracked файлы, относящиеся к уже landed работе.**
- **НЕ** использовать `--amend`, `--force`, `reset --hard`.
- **НЕ** push'ить на remote, **НЕ** `git push --tags`.
- **НЕ** менять structure `CHANGELOG.md` — только добавить новую секцию поверх.
- Backend `test_performance` p95-guard может флапнуть — перезапустить один раз.
- Если `generate_api_docs.py` после version bump меняет только version-строку — OK. Если меняет другие секции — значит backend routes изменились; разбираться отдельно.
- `requirements.txt` трогать **не надо** — это отдельный bump.

## Out of scope
- Push на remote
- GitHub Release creation
- Docker image publish в registry (см. соседний таск `2026-04-22-cx-docker-publish-readiness.md`)
- Demo hosting (Vercel/Fly/Render)
- Дальнейшие a11y / lighthouse улучшения (landed)
