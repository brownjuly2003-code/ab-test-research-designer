# CX Task: Seed demo workspace on Hugging Face Space startup

## Goal
Сделать так, чтобы публичный demo на `https://liovina-ab-test-research-designer.hf.space` при каждом cold start поднимался с уже пред-заполненным workspace: 3 sample проекта, по одному сохранённому analysis run на каждый, хотя бы одна export-запись на первый проект. Юзер, заходя на demo URL, сразу видит наполненный sidebar, историю и экспорт — а не пустой wizard. Реализация — через startup hook в FastAPI, идемпотентный, безопасный для рестартов.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `14259fff` (tag `v1.1.0`). Не создавать новую ветку, не push на remote.
- **Hosting.** Hugging Face Spaces (Docker SDK, CPU basic free). `Dockerfile` в корне, entry: `python -m uvicorn app.backend.app.main:app --host 0.0.0.0 --port ${PORT:-${AB_PORT:-8008}}`. HF frontmatter `app_port: 8008` в `README.md`.
- **Существующий seed-скрипт.** `scripts/seed_demo_workspace.py` уже создаёт 3 проекта из пресетов (`checkout_conversion`, `pricing_sensitivity`, `onboarding_completion`) через `TestClient`, поддерживает флаг `--idempotent` (skip по `project_name`). Сейчас запускается только вручную; в `fly.toml` он подвязан через `release_command`, но на HF такого механизма нет.
- **Пресеты шаблонов.** `app/backend/templates/*.yaml` — 5 шаблонов. Seed использует 3 первых.
- **API.** `POST /api/v1/projects` — создать, `POST /api/v1/analysis` — run analysis, `POST /api/v1/export/markdown` — записать export-event в history. История хранится в `analysis_runs` и `export_events` таблицах; seed сейчас НЕ трогает ни analysis, ни export.
- **Зависимость от auth.** HF demo поднят в open-mode (нет `AB_API_TOKEN`). Любая дополнительная логика должна честно читать `AB_API_TOKEN` из env и уметь работать и в open, и в secure режиме (Bearer header если токен задан).
- **SQLite path.** `AB_DB_PATH` в Dockerfile = `/app/data/projects.sqlite3`. HF контейнер не имеет persistent volume (на HF Space базового tier) — каждый рестарт = чистая БД. Это и есть причина делать seed автоматическим.
- **Почему НЕ cron / НЕ release_command.** HF Spaces Docker SDK не даёт pre-start hook и не имеет отдельного release-step. Единственная надёжная точка — FastAPI lifespan/startup.

## Deliverables

1. **Backend startup seeding hook** (`app/backend/app/main.py` или новый `app/backend/app/startup_seed.py`):
   - Новый env var `AB_SEED_DEMO_ON_STARTUP` (bool, default `false`). Включён только когда нужно наполнять демо — HF Space задаёт его через `Dockerfile` (или через `README.md` HF `environment` секцию, если CX-ник удобнее).
   - Логика hook:
     1. Выполняется однократно на startup, ПОСЛЕ того как SQLite репозиторий готов (миграции прошли).
     2. Если в БД уже есть ≥3 проекта с префиксом `"Demo - "` — skip и лог `demo-seed: already populated, skipping`.
     3. Иначе — вызвать код аналогичный `scripts/seed_demo_workspace.py`, но **in-process** (без `TestClient`), напрямую через существующие service-слои `project_service` / `analysis_service` / `export_service`. Через HTTP внутри того же процесса на startup — лишние request-ID, CORS, auth; надёжнее напрямую на сервисы.
     4. После создания каждого проекта — сразу run analysis (`analysis_service.run_analysis(payload)`) и сохранить результат через `project_service.save_analysis_run(project_id, result)`.
     5. На первом проекте (Checkout) — дополнительно выполнить export Markdown, чтобы `export_events` был непустым и история в UI отображала export badge.
     6. Все failures seed — залогировать `ERROR demo-seed: …`, **не ронять процесс** (запуск приложения важнее, чем наполненный demo). Есть продолжать старт даже если seed не удался.
   - Логирование через существующий `logging_utils` (`get_logger(__name__)`), уровень `INFO`.

2. **Dockerfile / HF README изменения:**
   - В `Dockerfile` добавить `ENV AB_SEED_DEMO_ON_STARTUP=false` (дефолт — выключен, чтобы локальный `docker run` не спамил БД).
   - В HF frontmatter `README.md` (верхняя YAML-секция до `# AB Test Research Designer`) — добавить блок `environment:` с `AB_SEED_DEMO_ON_STARTUP: "true"`. Проверить, что HF Spaces корректно передаёт эти env в контейнер (ключевое слово — `env_vars` / `environment` — уточнить по актуальной схеме frontmatter; если переменная именно для HF записывается иначе — записать так, как поддерживает HF, и оставить `ENV` в Dockerfile как local-safe дефолт).
   - **НЕ** включать `AB_SEED_DEMO_ON_STARTUP=true` как дефолт в Dockerfile или compose — только HF-специфичная настройка.

3. **Тест backend:**
   - `app/backend/tests/test_startup_seed.py` (pytest):
     1. Фикстура с чистой in-memory/tempdir SQLite.
     2. Устанавливает `AB_SEED_DEMO_ON_STARTUP=true`, создаёт app через `create_app()`, проходит через lifespan (`with TestClient(app):`).
     3. Проверяет: `GET /api/v1/projects` возвращает ≥3 проекта с префиксом `"Demo - "`, у каждого есть `last_analysis_run_id`, у первого в `history` есть export-запись.
     4. Второй тест — идемпотентность: повторный стартап (второй раз открыть `TestClient`) не дублирует проекты.
     5. Третий тест — при `AB_SEED_DEMO_ON_STARTUP=false` (или unset) никаких проектов не создаётся.

4. **Тест отсутствия регрессий:**
   - Убедиться, что `test_main_app_startup_disabled_seed` (или аналогичный существующий тест, который уже проверяет что startup проходит без сайд-эффектов) продолжает зелёным. Если нет — не менять его, но пометить в отчёте.

5. **Обновить `docs/RUNBOOK.md`:**
   - Новая секция `## Demo seeding on Hugging Face` — как работает, как выключить (`AB_SEED_DEMO_ON_STARTUP=false`), как форсировать re-seed (delete SQLite при рестарте контейнера или ручной `DELETE /api/v1/projects/{id}` через admin token + рестарт).

6. **Обновить `README.md`:**
   - В секции `## Demo` дописать 1 абзац: «The hosted demo is seeded with three sample projects (checkout conversion, pricing sensitivity, onboarding completion), each with a completed analysis run and an export on the first one, so the sidebar and history views are populated on first load.»
   - **НЕ** менять HF frontmatter ручной правкой кроме пункта 2.

7. **Один коммит:**
   ```
   feat: seed demo workspace on hf startup with idempotent backend hook
   ```
   Co-Authored-By: Codex <noreply@anthropic.com>
   В коммит обязательно включить этот CX-файл (`docs/plans/codex-tasks/2026-04-22-cx-seed-hf-startup.md`).

8. **Отчёт `docs/plans/2026-04-22-seed-hf-startup-report.md`:**
   - Список изменённых/созданных файлов.
   - Вывод нового теста (3 сценария).
   - Результат `scripts/verify_all.cmd --with-e2e`.
   - Чек-лист юзера для HF deploy: какие env выставить в HF UI (если нужно), как проверить `/api/v1/projects` после деплоя через `curl`.
   - Известные риски: SQLite на HF без persistent volume — каждый рестарт seed заново (это OK, это фича); seed занимает ~2-3s на startup (терпимо для free tier).

## Acceptance
- `scripts/verify_all.cmd --with-e2e` = exit 0 после коммита.
- Новые тесты (3 сценария из #3) проходят, `test_startup_seed.py` включён в дефолтный pytest run.
- `git status --short` пусто после коммита.
- Локальный smoke: `docker build -t ab-test:seed-test .` → `docker run --rm -e AB_SEED_DEMO_ON_STARTUP=true -p 18010:8008 ab-test:seed-test` → через 10s `curl localhost:18010/api/v1/projects | jq '.projects | length'` ≥ 3. Логировать output в отчёт.
- Локальный smoke БЕЗ флага: `docker run --rm -p 18011:8008 ab-test:seed-test` → через 10s `curl localhost:18011/api/v1/projects | jq '.projects | length'` == 0. Логировать в отчёт.
- Коммит subject не коллизит с предыдущими (`git log --oneline -20 | awk '{$1=""; print}' | sort | uniq -d` == пусто).
- CX-файл застейджен в тот же коммит.
- **НЕ** `git push` на remote, **НЕ** `hf upload`, **НЕ** трогать HF Space через API — юзер релизит вручную.

## How
1. Baseline: `git status --short` пусто, `scripts/verify_all.cmd` = 0. Если нет — stop.
2. Прочитать `app/backend/app/main.py` (lifespan / startup), `app/backend/app/services/project_service.py`, `analysis_service.py`, `export_service.py` — найти точки вызова.
3. Написать `startup_seed.py` с модульной функцией `seed_demo_workspace(settings) -> SeedResult`.
4. Подключить в `main.py` lifespan только если `settings.seed_demo_on_startup` = true.
5. Написать тесты. Прогнать pytest локально до зелёного.
6. Обновить `Dockerfile`, `README.md` HF frontmatter, RUNBOOK, README Demo секцию.
7. Docker smoke (2 прогона — с флагом и без).
8. `git add` список файлов + CX-файл. Commit. `git status --short` → пусто.
9. `scripts/verify_all.cmd --with-e2e`.
10. Отчёт.

## Notes
- **НЕ** делать seed через HTTP к самому себе внутри startup — может быть race с readiness, bind порта ещё не готов.
- **НЕ** трогать `scripts/seed_demo_workspace.py` — он остаётся рабочим для `fly.toml release_command` и ручного запуска. Если в нём есть код, который можно переиспользовать — вынести общую часть в `app/backend/app/startup_seed.py` и заставить скрипт импортировать оттуда.
- **НЕ** коммитить `data/projects.sqlite3` или любые артефакты локальных прогонов.
- **НЕ** переименовывать существующие env vars.
- Если при тестах всплывёт, что `create_app()` не вызывается с lifespan в `TestClient` — использовать `with TestClient(app) as client:` (это корректный паттерн для FastAPI lifespan).
- Логи HF Space видны через `huggingface_hub.HfApi().get_space_runtime(repo_id="liovina/ab-test-research-designer").stage` + HF UI — записать в отчёт как дебаг-подсказку для юзера.
- Если обнаружится, что `analysis_service.run_analysis` требует LLM call — использовать deterministic fallback path, который уже есть в коде (`design composer` без AI). Seed НЕ должен требовать Ollama / внешний LLM.

## Out of scope
- Persistent storage на HF (это отдельный Tier 2 #7 таск).
- Реальный `hf upload` / HF Space restart — юзер делает сам.
- UI-изменения кроме README.
- Миграция на Postgres.
- Добавление новых пресетов шаблонов.
- Seed webhook subscriptions / comparison history.
