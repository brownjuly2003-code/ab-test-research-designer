# CX Task: Workspace cleanup — убрать transient артефакты и навести порядок в корне

## Goal
Привести рабочую копию `D:\AB_TEST\` в чистое состояние: удалить gitignored transient-артефакты (локальные CI-прогоны, tmp-логи, пустой `node_modules` в корне, `.hypothesis/`, старые smoke-дампы), разобрать loose-файлы планирования в корне и в `archive/`, добить `.gitignore` для оставшихся шумных путей. После уборки `git status --short` должен быть пуст, все ссылки из README/docs — рабочими.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `f1316300` (all pushed).
- **Почему сейчас.** Tier 1 roadmap закрыт, Ubuntu CI green. Перед Tier 2 работой нужно убраться, чтобы `git status` давал сигнал (сейчас после каждого `verify_all` / `run_local_smoke` в working tree остаются артефакты, которые забивают сигнал и провоцируют случайные commits через `git add .`).
- **НЕ ТРОГАТЬ** ничего в `app/`, `scripts/`, `.github/`, `badges/`, `docs/` (кроме явно перечисленных перемещений), `exports/.gitkeep`, `archive/smoke-runs/.gitkeep`, `archive/smoke-runs/README.md`, `pytest.ini`, `.lighthouserc.json`, `Dockerfile`, `docker-compose.yml`, `fly.toml`, `CHANGELOG.md`, `README.md`, `LICENSE`, `.dockerignore`, `.env.example`, `.gitattributes`. Цель — transient cruft + reorg loose docs, не рефакторинг.

## Inventory (снимок перед работой — перепроверить `ls -la` / `du -sh` самостоятельно на старте)

**Gitignored каталоги в корне (безопасно удалить — не в git):**
- `tmp/` (~3.1 MB: `app_snapshot.txt`, `codex-stage/`, `css-unify/`, `final-verify.log`, `frontend-dev.*.log`, `readme-demo.patch`, `verify-a11y-lh.log`, `verify-debug.sqlite3`, `verify-final.log`, `verify-head.log`, `vite-preview.{err,out}`)
- `.ci-artifacts/` (~528 KB: `backend-junit.xml`, `coverage-backend.json`, `frontend-junit.xml` — локальные прогоны `verify_all.py --artifacts-dir .ci-artifacts`)
- `.tmp-gh-artifacts/` (0 B полезного контента, подпапка `run-24811054759/` от прошлых `gh run download`)
- `node_modules/` в КОРНЕ (~1 KB, аномалия — настоящий `node_modules` живёт в `app/frontend/node_modules/`; корневой создан случайно, probably от `npm install` запущенного не из той папки)
- `.hypothesis/` (129 KB — Hypothesis example database, регенерируется)
- `.coverage` (бинарник pytest-cov, в `.gitignore`, регенерируется)

**Gitignored, внутри archive/ — тоже безопасно удалить:**
- `archive/e2e-runs/` (в `.gitignore`)
- `archive/manual-smoke-runs/` (в `.gitignore`)
- `archive/smoke-runs/20260307-*/`, `20260308-*/` и прочие timestamped dumps (88 MB, паттерн `archive/smoke-runs/*` в `.gitignore`, оставить только `.gitkeep` + `README.md`)
- `archive/verify-workspace-backup/*` (в `.gitignore`)

**Tracked loose-файлы в корне (перенести):**
- `BCG_audit.md` (28 KB)
- `BCG_plan.md` (35 KB)
- `bcg-phase-1-execution.md`
- `commercial-upgrade-plan.md`
- `progress.md`

Это архивные BCG-планы и historical progress log. Переместить в `archive/2026-04-23-bcg-planning-docs/` (новая папка). Проверить, не ссылается ли на них `README.md`, `CHANGELOG.md`, `docs/*.md` — если да, обновить пути. Если ссылок нет — просто `git mv`.

**Tracked loose-файлы в archive/ (перенести в дата-неймспейс):**
- `archive/ab_test_for_gihub.md` (typo: "gihub", не переименовывать — это historical)
- `archive/audit.md`
- `archive/prompt_for_github.md`
- `archive/questions.md`
- `archive/rec.md`

Переместить в `archive/2026-03-08-legacy-loose-docs/` (новая папка), чтобы архивный корень стал однородным (только dated subdirs + README если есть).

**`.gitignore` патчи:**
- Добавить `.tmp-gh-artifacts/` (сейчас не в ignore)
- Добавить `node_modules` (уже есть строка `node_modules/` — проверить, что покрывает и корень, и `app/frontend/node_modules/`; если нет — добавить `**/node_modules/`)
- Ничего не удалять из существующего `.gitignore`

## Deliverables

1. **Hard-delete gitignored transient (одна Bash-команда с echo'ами для логирования):**
   ```bash
   rm -rf tmp .ci-artifacts .tmp-gh-artifacts node_modules .hypothesis .coverage
   rm -rf archive/e2e-runs archive/manual-smoke-runs archive/verify-workspace-backup
   find archive/smoke-runs -mindepth 1 ! -name '.gitkeep' ! -name 'README.md' -exec rm -rf {} + 2>/dev/null || true
   ```
   Перед запуском — `git status --short` и убедиться, что ни один из этих путей не содержит tracked файлов (grep по `git ls-files` — если попадает хоть один tracked в эти пути, остановиться и вернуться с отчётом).

2. **Переместить root-level planning docs:**
   ```bash
   mkdir -p archive/2026-04-23-bcg-planning-docs
   git mv BCG_audit.md BCG_plan.md bcg-phase-1-execution.md commercial-upgrade-plan.md progress.md archive/2026-04-23-bcg-planning-docs/
   ```
   После этого — `grep -rn "BCG_audit\|BCG_plan\|bcg-phase-1-execution\|commercial-upgrade-plan\|progress\.md" README.md CHANGELOG.md docs/` и обновить все найденные ссылки на новый путь. Если ссылок нет — ok.

3. **Переместить archive loose docs:**
   ```bash
   mkdir -p archive/2026-03-08-legacy-loose-docs
   git mv archive/ab_test_for_gihub.md archive/audit.md archive/prompt_for_github.md archive/questions.md archive/rec.md archive/2026-03-08-legacy-loose-docs/
   ```
   Аналогично — `grep -rn` для ссылок, обновить.

4. **Патч `.gitignore`:**
   - Добавить строку `.tmp-gh-artifacts/` в секцию "verify artifacts".
   - Проверить, что `node_modules/` матчит и корневой, и вложенные. Если `git check-ignore -v node_modules/ app/frontend/node_modules/` не показывает совпадение по корневому — заменить на `**/node_modules/` ИЛИ добавить отдельную строку `/node_modules/`.
   - Не трогать остальное.

5. **Verify-пасс (после уборки + reorg):**
   ```
   git status --short         → пусто после staged moves и .gitignore патча (staged diff будет, working tree чистый)
   python scripts/verify_all.py --skip-build
   ```
   Если verify падает из-за сломанной ссылки в docs/README/тестах — починить ссылку или откатить соответствующий `git mv` и вернуться в отчёт.

6. **Commit план (три отдельных коммита, не squash):**
   - Commit 1: `chore(gitignore): add .tmp-gh-artifacts, tighten node_modules match`
   - Commit 2: `chore(archive): move BCG planning docs out of repo root into archive/2026-04-23-bcg-planning-docs`
   - Commit 3: `chore(archive): group legacy loose docs under archive/2026-03-08-legacy-loose-docs`

   Каждый коммит с одной темой — если нужно обновить ссылки в README.md, делать это в том же коммите, что и `git mv`.

## Acceptance

- `git status --short` → пусто (чистое working tree).
- `ls /d/AB_TEST/` в корне: отсутствуют `tmp/`, `.ci-artifacts/`, `.tmp-gh-artifacts/`, `node_modules/`, `.hypothesis/`, `.coverage`, `BCG_audit.md`, `BCG_plan.md`, `bcg-phase-1-execution.md`, `commercial-upgrade-plan.md`, `progress.md`.
- `ls /d/AB_TEST/archive/` показывает только dated subdirs + `smoke-runs/` (с `.gitkeep` и `README.md` внутри) + новые созданные папки.
- `du -sh /d/AB_TEST/archive/smoke-runs/` — ≤ 8 KB (только tracked файлы).
- `grep -rn "BCG_audit\.md\|bcg-phase-1-execution\.md\|commercial-upgrade-plan\.md\|progress\.md" README.md CHANGELOG.md docs/ 2>/dev/null` — либо пусто, либо все ссылки указывают на новый путь `archive/2026-04-23-bcg-planning-docs/...`.
- `python scripts/verify_all.py --skip-build` → exit 0 (ничего из тестов / docs-ссылок не сломалось).
- 3 коммита на `main`, push'нуто (`gh run list --branch main --limit 1` → workflow запущен, дожидаться прохождения не обязательно в рамках этой задачи, но проверить старт).

## Notes
- Если в ходе работы обнаружится tracked файл внутри любого из "gitignored" путей (`git ls-files tmp/` выдаст что-то) — **остановиться**, не удалять, вернуться с отчётом: это значит, что у кого-то в истории закоммитился артефакт, и решение требует обсуждения.
- `progress.md` исторически в корне (в git-логе отдельные коммиты "docs: update progress log"), перемещение в archive = явное решение отказаться от дальнейшего ведения этого лога в пользу CHANGELOG + roadmap в README. Если в последнем коммите `progress.md` есть полезный свежий контент — скопировать релевантное в CHANGELOG перед git mv.
- Не запускать `git gc` / `git prune` / `git filter-branch` — они не требуются и рискованны; дисковый след от старых больших файлов в `.git/objects` — это не скоуп этой задачи.
- Отчёт в конце (markdown, 15-20 строк): сколько мегабайт освобождено, какие ссылки в docs/README обновлены, какие коммиты созданы, остались ли неожиданности.
