# CX Task: HF Space persistent storage через private HF Dataset snapshot

## Goal
Сейчас HF Space (`liovina-ab-test-research-designer`) использует контейнерный SQLite внутри `/data/projects.sqlite3`, который теряется при каждом рестарте Space (rolling redeploy / billing sleep). Это делает демо disposable, а посетитель увидит пустой workspace. Цель — периодически снапшотить SQLite в private HuggingFace Dataset через `huggingface_hub`, и на старте Space восстанавливать последний snapshot. Tier 2 roadmap #2.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `1e8472b0`. Live HF Space: https://liovina-ab-test-research-designer.hf.space.
- **Backend.** FastAPI, entrypoint `app/backend/app/main.py`. SQLite путь берётся из env `AB_DB_PATH` (default в Dockerfile — `/data/projects.sqlite3`).
- **Существующий seed.** `AB_SEED_DEMO_ON_STARTUP=true` запускает создание 3 демо-проектов при пустой БД (см. `app/backend/app/startup_hooks.py` или аналог). Работает через `AB_ENV=production`-gate. Сохранить это поведение как fallback — если snapshot restore провалится, стартуем с фабричного seed.
- **HF auth.** Token юзера `liovina` сохранён локально в `C:\Users\uedom\.cache\huggingface\token`. В Space доступен как Space Secret через Settings → Variables and Secrets. Для push в Dataset нужен `write`-scope token.
- **HF Dataset.** Новый приватный dataset `liovina/ab-test-designer-snapshots` (создать в рамках задачи через `HfApi().create_repo(repo_type="dataset", private=True)`).
- **Snapshot format.** Один файл `projects.sqlite3` в корне dataset + `metadata.json` с `{"schema_version": "1.1.0", "ts": "2026-04-23T12:34:56Z", "sha256": "..."}`.
- **Не трогать** smoke / verify / CI workflow / frontend / release / Dockerfile port mapping. Область — backend startup + shutdown hooks + новый service модуль.

## Deliverables

1. **Новый service-модуль `app/backend/app/services/snapshot_service.py`:**
   - `class SnapshotService`:
     - `__init__(self, repo_id: str, local_db_path: Path, hf_token: str | None)` — принимает конфиг через DI.
     - `async def restore_latest(self) -> bool` — скачивает `projects.sqlite3` и `metadata.json` из HF Dataset через `HfApi().hf_hub_download()`. Возвращает `True` если restore успешен, `False` если dataset пустой / недоступен / не авторизован. Проверяет sha256 перед заменой локального файла (atomic rename через tempfile).
     - `async def push_snapshot(self) -> str` — рассчитывает sha256 локального SQLite, загружает через `HfApi().upload_file()` в HF Dataset с коммит-сообщением `snapshot: <timestamp>`. Возвращает commit hash.
     - Timeout 30s на каждую HF операцию, graceful fail (лог + return, не raise) — snapshot не должен ронять старт Space.
   - Использовать `huggingface_hub` уже существующий в `requirements.txt` (проверить; если нет — добавить).

2. **Startup hook в `app/backend/app/main.py`:**
   - Перед существующим `AB_SEED_DEMO_ON_STARTUP` hook'ом: если `AB_HF_SNAPSHOT_REPO` env задан и `AB_HF_TOKEN` env задан — вызвать `await snapshot_service.restore_latest()`.
   - Если restore вернул `True` — логировать `snapshot: restored from <commit>` и **пропустить** seed (данные уже есть).
   - Если `False` — логировать `snapshot: no snapshot available, falling back to seed` и продолжить обычный seed flow.
   - Если env не заданы вообще — проскипать snapshot logic целиком (не ломать локальный dev / тесты).

3. **Background snapshot task:**
   - Отдельный asyncio Task, запускаемый в startup event, с loop'ом `await asyncio.sleep(AB_HF_SNAPSHOT_INTERVAL_SECONDS)` + `await snapshot_service.push_snapshot()`. Default interval — 900s (15 мин).
   - На SIGTERM / shutdown event — один финальный `push_snapshot()` synchronous вызов с 10s timeout, чтобы последние изменения перед рестартом попали в snapshot.
   - Логировать каждый push: `snapshot: pushed <commit> (size=XKB, delta=YKB)`.

4. **Env vars документирование (README + `.env.example`):**
   - `AB_HF_SNAPSHOT_REPO` — repo_id (e.g. `liovina/ab-test-designer-snapshots`).
   - `AB_HF_TOKEN` — HF write token (Space Secret в production).
   - `AB_HF_SNAPSHOT_INTERVAL_SECONDS` — override default (тесты могут выставить `0` для отключения, тогда background task не запускается).

5. **Тесты.** `app/backend/tests/test_snapshot_service.py`:
   - Unit-тесты с мокнутым `HfApi` через `pytest-mock` / `unittest.mock.patch`:
     - `restore_latest` успешный flow (mock скачивает tmp SQLite, sha256 совпадает, rename происходит).
     - `restore_latest` sha mismatch → return `False`, локальный файл не меняется.
     - `restore_latest` HF 404 (dataset пустой) → return `False`, нет exception.
     - `restore_latest` HF 401 (bad token) → return `False` + log warning, нет exception.
     - `push_snapshot` успешный flow (mock upload_file, возврат commit hash).
     - `push_snapshot` 500 / network error → лог + return "", нет exception.
   - Integration-тест не требуется (рисковано бить live HF в CI). Один smoke в `scripts/verify_snapshot_local.py` — опциональный ручной запуск с живым token, документирован в RUNBOOK.

6. **HF Space Dockerfile / config:**
   - Space Secret `AB_HF_TOKEN` и `AB_HF_SNAPSHOT_REPO` задать через HF Space UI (юзер делает вручную, не в коде — секрет не уезжает в git).
   - `README.md` (YAML frontmatter для HF) или Dockerfile — **не менять** `app_port`, HEALTHCHECK, existing env. Добавить только описание новых env в body README.

## Acceptance
- Новый модуль + hooks проходят `python -m pytest app/backend/tests/test_snapshot_service.py -v` — зелёный.
- `python scripts/verify_all.py --with-e2e --with-coverage --skip-build` — зелёный (новые тесты добавили покрытие, старые не сломались).
- Локально без env `AB_HF_SNAPSHOT_REPO` / `AB_HF_TOKEN` — backend стартует как обычно, snapshot logic пропускается (лог: `snapshot: disabled (env not set)`).
- После deploy на HF Space с секретами: в логах Space через 15 минут после рестарта появляется `snapshot: pushed <commit>`. Перезапуск Space (trigger Settings → Restart) → в логах `snapshot: restored from <commit>`, workspace содержит проекты из предыдущей сессии, не seed.
- Один коммит: `feat(snapshot): persist SQLite to HF Dataset for HF Space resume`.
- Обновлён memory-note в `MEMORY.md` / `project_ab_test.md` (если кто-то из участников захочет — user сделает сам, не в scope CX).

## Notes
- **НЕ коммитить HF token.** Secret только через Space Variables. Локально — через `.env` / shell export, не через `.env.example` с реальным значением.
- **HF Dataset rate limits.** 15-минутный interval — безопасный дефолт (HF не ругается на commits < 1/min). Если юзер захочет чаще — пусть выставит `AB_HF_SNAPSHOT_INTERVAL_SECONDS=300` (5 мин), но не меньше.
- **Atomic rename при restore.** SQLite открытый backend'ом заменять напрямую нельзя. Restore делается ДО `uvicorn` startup (лайфспан-зависимость), либо через `sqlite3.connect(':memory:').backup()` API. Выбрать первый вариант — проще.
- **Size limits.** Private HF Dataset — без hard limit на отдельный файл до ~50GB. SQLite демо Space — сотни KB, запас огромен.
- **Branch / PR.** Этот таск достаточно большой (1 модуль + hooks + tests + HF setup). Если нужно разбить — допустимо 2 PR'а: (A) SnapshotService + tests, (B) startup/shutdown hooks + deploy. В этом случае (A) сначала merge'ать, CI зелёный, потом (B).
- Отчёт (20-30 строк): какой env var настроен, HF Dataset URL, первый snapshot commit hash, verify output, replay-check result (stop Space → restart Space → данные те же).
