# CX Task: Demo hosting prep — Fly.io config, GitHub Release draft, no actual deploy

## Goal
Подготовить `D:\AB_TEST\` к публичному demo-хостингу на Fly.io: написать `fly.toml`, проверить что v1.0.0 Docker образ запускается с Fly-compatible env (PORT binding, read-write volume для SQLite), составить GitHub Release draft markdown. **Без реального deploy и без реального push** — юзер нажимает кнопки сам, когда решит.

## Context
- Репо: `D:\AB_TEST\`, `main`, HEAD после v1.0.0 (tag должен существовать). Не ветка, не push.
- Docker образ `ab-test-research-designer:1.0.0` уже протестирован в `docs/plans/2026-04-22-docker-publish-readiness-report.md`.
- `docs/DEPLOY.md` уже документирует локальный Docker run.
- Платформу выбираем — Fly.io. Причины: бесплатный tier, поддержка Docker images напрямую (без Dockerfile-rewrite), возможность persistent volume для SQLite без внешнего DB, регион выбираем ams/fra (close to RU/EU users).
- Альтернативы (Vercel, Render, Railway) — **вне scope**: Vercel требует рефактор фронта отдельно от backend; Render имеет cold starts; Railway похож, но менее стабилен.
- Предусловие: `v1.0.0` tag создан (`git tag -l v1.0.0` возвращает строку). Если нет — **stop**.

## Deliverables
1. **`fly.toml`** в корне репо:
   - `app = "ab-test-research-designer"` (placeholder; юзер переименует при `fly apps create`).
   - Primary region `ams` (или `fra`).
   - `[build]` → `image = "ab-test-research-designer:1.0.0"` (либо `dockerfile = "Dockerfile"` — выбирай ту опцию, которая проще, но задокументируй в комментарии внутри `fly.toml`).
   - `[env]`: `AB_SERVE_FRONTEND_DIST=true`, `AB_WORKSPACE_DIR=/data`, `AB_DB_PATH=/data/projects.sqlite3`, `AB_ENV=demo`.
   - `[[mounts]]`: `source = "ab_test_data"`, `destination = "/data"` — persistent volume 1GB.
   - `[http_service]`: `internal_port = 8008`, `force_https = true`, `auto_stop_machines = true`, `auto_start_machines = true`, `min_machines_running = 0`.
   - `[[http_service.checks]]`: `grace_period = "10s"`, `interval = "30s"`, `timeout = "5s"`, `method = "get"`, `path = "/health"`.
   - `[[vm]]`: `cpu_kind = "shared"`, `cpus = 1`, `memory_mb = 512`.
   - Закомментированные секции для secure mode: `# [secrets] → fly secrets set AB_API_TOKEN=... AB_READONLY_API_TOKEN=... AB_WORKSPACE_SIGNING_KEY=...`.

2. **Bug-fixes если Fly-incompatible:**
   - Проверить что бекенд биндится на `0.0.0.0`, не `127.0.0.1`, когда `AB_ENV=demo` или через env `AB_HOST`. Если нет — патч в `app/backend/app/main.py` или uvicorn launch (скорее всего в `Dockerfile` CMD).
   - SQLite path — должен браться из `AB_DB_PATH` env, не hardcode. Проверить `app/backend/app/repository.py` / `config.py`. Если hardcoded — патч.
   - Writable `/data` volume — SQLite WAL mode нужны write permissions. Убедиться, что директория создается при первом запуске если её нет.

3. **Demo seed data (опционально, но полезно):**
   - `scripts/seed_demo_workspace.py` — скрипт, который создаёт 2–3 sample projects через внутренний API, используя пресеты из `app/backend/templates/`. Запускается один раз в `fly deploy` через `release_command`.
   - Добавить в `fly.toml`: `[deploy] release_command = "python scripts/seed_demo_workspace.py --idempotent"`.
   - `--idempotent`: если проекты уже существуют — пропускаем.

4. **Secrets placeholder secure mode:**
   - `docs/DEPLOY.md` дополнить секцией «Fly.io deploy (secure)» с командами:
     ```
     fly secrets set AB_API_TOKEN=... AB_READONLY_API_TOKEN=... AB_WORKSPACE_SIGNING_KEY=...
     fly deploy
     ```
   - Пояснение: без секретов — open demo (рекомендуемо для публичного showcase); с секретами — private.

5. **GitHub Release draft** в `docs/RELEASE_NOTES_v1.0.0-github-draft.md`:
   - Title: `v1.0.0 — A/B Test Research Designer`
   - Description: скопировано из `docs/RELEASE_NOTES_v1.0.0.md` с добавлением:
     - Link to demo: `<placeholder — fill after fly deploy>` 
     - Link to Docker image: `<placeholder — after docker push>` 
     - Verification steps для юзера.
   - Список assets для attach: `ab-test-research-designer_1.0.0.tar.gz` (tarball репо HEAD + `fly.toml`), `docs/RELEASE_NOTES_v1.0.0.md`, `docs/DEPLOY.md`.
   - Instruction block внизу: `# How to publish: gh release create v1.0.0 --draft --notes-file docs/RELEASE_NOTES_v1.0.0-github-draft.md`.

6. **Обновить `README.md`:**
   - Новая секция `## Demo` с placeholder `<fly-url-after-deploy>` и instruction «Deploy your own: see docs/DEPLOY.md».
   - Ссылка на `fly.toml` и GitHub Release draft.

7. **Один коммит:**
   ```
   ops: prep fly.io demo hosting config and github release draft
   ```

8. **Отчёт `docs/plans/2026-04-22-demo-hosting-prep-report.md`:**
   - Список файлов созданных/изменённых.
   - Bug-fixes: какие env/path patch применены и почему.
   - Чек-лист юзера для deploy (что нажать чтобы задеплоить).
   - Известные риски: cold start latency, 512MB RAM limit, SQLite не scales horizontally.

## Acceptance
- `fly.toml` в корне, валидный TOML (`python -c "import tomllib; tomllib.load(open('fly.toml','rb'))"` = 0).
- `docker build -t ab-test-research-designer:1.0.0 .` всё ещё проходит (если были bug-fixes в Dockerfile).
- `docker run --rm -p 18008:8008 -e AB_WORKSPACE_DIR=/tmp/abtest -e AB_DB_PATH=/tmp/abtest/p.sqlite3 ab-test-research-designer:1.0.0` стартует и `/health` → 200 с volume-path persistence.
- `docs/RELEASE_NOTES_v1.0.0-github-draft.md` присутствует и ссылки-плейсхолдеры явно помечены.
- Commit subject уникальный, `Co-Authored-By: Codex <noreply@anthropic.com>`.
- Этот CX-файл стадж в тот же коммит.
- `scripts\verify_all.cmd --with-e2e` = exit 0.
- `git status --short` = пусто.

## How
1. Baseline: `git status --short` = пусто, tag `v1.0.0` существует, `scripts\verify_all.cmd` = 0.
2. Прочитать текущий `Dockerfile` и `app/backend/app/config.py` — найти SQLite path / host binding.
3. Если path hardcoded — патч на чтение из env.
4. Написать `fly.toml` на основе структуры выше.
5. Протестировать локально: `docker run` с env имитирующими Fly volume (`-e AB_WORKSPACE_DIR=/tmp/x -v /tmp/x:/tmp/x`).
6. Написать `scripts/seed_demo_workspace.py`.
7. Расширить `docs/DEPLOY.md` и `README.md`.
8. Написать GitHub Release draft.
9. Commit, verify, report.

## Notes
- **CX-файл hygiene:** staging этот файл.
- **Commit subject hygiene:** проверка на дубль.
- **НЕ** регистрировать fly.io app, **НЕ** запускать `fly deploy`, **НЕ** `gh release create`. Юзер всё делает сам.
- **НЕ** ставить fly CLI в CI / devDeps. Это локальный tool юзера.
- **НЕ** захардкодить имя приложения Fly — placeholder в `fly.toml` и readme.
- **НЕ** коммитить секреты — использовать только env-var имена в документации.
- Если demo будет public — рекомендовать read-only token (AB_READONLY_API_TOKEN) чтобы выставить наружу только GET; write-protected. Документировать в DEPLOY.md.
- SQLite на Fly — ОК для single-machine demo, но явно задокументируй в risks что horizontal scaling требует Postgres/LiteFS (вне scope).
- Backend `test_performance` может флапнуть — перезапустить один раз.
- **НЕ** пушить на remote.

## Out of scope
- Реальный `fly deploy` / `gh release create` / `docker push`
- Migration на LiteFS / Postgres
- CDN для статики
- Custom domain config
- Monitoring/Sentry/Datadog интеграции
- CI autodeploy на мерж в main
