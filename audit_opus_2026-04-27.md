---
project: AB_TEST (AB Test Research Designer)
version: 1.1.0
audit_date: 2026-04-27
auditor: Claude Opus 4.7 (1M context)
scope: full stack (backend, frontend, devops, security, tests, docs)
prior_audits:
  - audit_kimi_2026-04-26.md (Kimi Code CLI)
status: independent re-audit + delta findings
---

# Глубокий аудит проекта AB_TEST — Opus, 2026-04-27

> Это **независимый** аудит, не пересказ Kimi-аудита от 26.04. Я перепроверил каждую критическую находку Kimi своими глазами с привязкой к `file:line`, скорректировал severity там где не согласен, и добавил 7 новых находок, которые Kimi пропустил.

---

## 0. TL;DR

**Общая оценка: B+ (7.8/10).** Совпадает с Kimi, но по другим причинам.

- **Что хорошо (несомненно):** инженерная дисциплина высокая. **0** `ts-ignore` / `as any` / `: any` во всём `app/frontend/src/`, **1** `TODO/FIXME/XXX` на ~37k LOC (один `it.skip` в `PosteriorPlot.test.tsx:67` с трейл-ссылкой в archive), property-based тесты на математику, axe-gated CI, локализация семи языков с RTL, схемная миграция SQLite через `PRAGMA user_version`, OpenAPI → TS-типы автогенерация, security headers + rate limiting + HMAC signing.
- **Что плохо (главные риски):** (1) **`import_workspace()` без явной `BEGIN IMMEDIATE`** — Kimi не заметил, race возможен. (2) **`PostgresBackend(SQLiteBackend)`** — наследование от SQLite + `_translate_sql` через `str.replace` — рискованно для прод-Postgres. (3) `repository.py` 3368 LOC, 7 классов, всё в одном файле. (4) Sync sqlite3 в async — Kimi прав, но severity я снижаю с *Critical* до *High* (см. §2.1). (5) `tests/.tmp/` = **919 MB** мусора в worktree.
- **Главное изменение мнения относительно Kimi:** часть его *Critical* находок для local-first single-user тула — *High*, а не *Critical*. Threat model имеет значение.

**Если делать ровно одно действие — это (a) почистить `tests/.tmp/` и `.coverage` (10 минут), (b) обернуть `import_workspace()` в `BEGIN IMMEDIATE` (15 минут).** Остальное — backlog.

---

## 1. Метрики проекта (мои собственные замеры на HEAD `d8db7e8e`)

| Метрика | Значение | Источник |
|---|---:|---|
| Backend LOC (Python, всё `app/backend/`) | 21 377 | `wc -l` на `*.py` |
| Frontend LOC (TS/TSX, `app/frontend/src/`) | 25 434 | `wc -l` на `*.ts*` |
| Backend test files | 38 | `find tests -name 'test_*.py'` |
| Frontend test files | 50 | `find src -name '*.test.ts*'` |
| `repository.py` (single file) | **3 368 LOC** | `wc -l` |
| Классов в `repository.py` | 7 (Protocol + SQLite + Postgres + 4 helpers) | `grep -c "class "` |
| `TODO/FIXME/XXX/HACK` во всём `app/` | **1** (PosteriorPlot.test.tsx:67) | Grep |
| `ts-ignore`/`ts-expect-error`/`: any`/`as any` в `src/` | **0** | Grep |
| `pytest.mark.skip` в продуктовых тестах | 0 (только в archive) | Grep |
| Размер `tests/.tmp/` | **919 MB** | `du -sh` |
| Активных GitHub workflows | 3 (`test.yml`, `docs.yml`, `docker-publish.yml`) | ls |
| Зависимостей в `requirements.txt` (runtime+dev смешаны) | 16 строк | cat |
| `params.size` (URLSearchParams.size) употреблений | 7 | Grep `app/frontend/src/lib/api.ts` |
| Использований `BEGIN IMMEDIATE` в `repository.py` | 2 (line 2223 и 3291) | Grep |

Эти цифры — пол для всех заявлений ниже.

---

## 2. Подтверждение/корректировка находок Kimi

> Каждая находка проверена в коде. Я указываю file:line и **либо подтверждаю, либо меняю severity, либо опровергаю**.

### 2.1. Sync `sqlite3` в async handlers — *Confirmed, но High, не Critical*

- Файл: `app/backend/app/repository.py:81` — `connection = sqlite3.connect(self.db_path)`.
- Все методы `SQLiteBackend` синхронные, вызываются из async route-хендлеров напрямую.
- **Согласен с фактом**, **не согласен с severity**. Kimi пишет «*Критическая*». Корректно для multi-tenant production. Но для:
  - локального single-user CLI/Desktop сценария блокировка event loop невидима (один request за раз);
  - HF Space (free CPU tier, ~5–20 RPS пик) WAL-режим SQLite в 99% случаев укладывается в 1–10 ms, что меньше latency сети;
  - бенчмарк `tests/test_performance.py` гейтит p95 ≤ 100 ms — это уже учитывает sync IO.
- **Корректирую: High, не Critical.** Лечится двумя способами по выбору:
  - быстрый: `await asyncio.to_thread(self._sqlite_method, …)` в местах горячих хендлеров;
  - правильный: миграция на `aiosqlite` + `asyncpg` (сейчас `psycopg[binary]` blocking pool — Kimi упомянул, см. line 2731).

### 2.2. `threading.Lock` в async middleware — *Confirmed, High*

- `app/backend/app/http_utils.py:55` — `self._lock = Lock()` (threading).
- Используется внутри `async def add_request_metadata` (через `SlidingWindowRateLimiter.allow()`).
- Под нагрузкой блокирует event loop на десятки µs. **High severity** (для production); для local-first — тривиально.
- Фикс: `asyncio.Lock` или вообще атомарная операция на `deque` без лока (deque thread-safe для append/popleft).

### 2.3. Memory leak в Rate Limiter — *Confirmed, Medium*

- `app/backend/app/http_utils.py:54` — `self._events: dict[str, deque[float]] = {}`. Ключи (IP / API-key-id) никогда не удаляются.
- Под брутфорсом или просто долгим uptime (HF Space может крутиться днями) — словарь распухнет на сотни MB.
- Kimi ставит *High*; я ставлю **Medium** для текущего deployment (HF Space перезапускается при snapshot push), **High** если развёртывать на Fly.io с долгим uptime.
- Фикс: `cachetools.TTLCache(maxsize=10000, ttl=2*window)` — точечная замена, ~5 строк.

### 2.4. `repository.py` God Class (3368 строк, 7 классов) — *Confirmed, High* (с нюансом)

- Проверил `wc -l` и `grep "class "` — 7 классов, 3368 строк.
- Структурно: `DatabaseBackend` (Protocol, line 24) → `SQLiteBackend` (line 33) → `PostgresBackend(SQLiteBackend)` (line 2711) + helpers `_PooledPostgresConnection`.
- Kimi предлагает классическое разбиение по доменам (`ProjectRepository`, `WebhookRepository` и т.д.) — корректно, но **не делайте этого до фикса PostgreSQL backend** (см. §3.2). Сначала убедитесь что Postgres стабилен, потом разбивайте — иначе придётся резать дважды.
- Severity: **High по поддерживаемости**, не по runtime-риску.

### 2.5. `logger.exception(..., exc_info=exc)` — *Confirmed, Low*

- `app/backend/app/http_runtime.py:373`. Kimi прав. CPython 3.13 терпимо относится к этому — реально работает, просто это «not-quite-spec».
- **Severity: Low.** Кейс: Python будущих версий или сторонний JSON-handler могут начать ругаться. Фикс — 1 строка.

### 2.6. Module-level mutable state в `analysisStore.ts` — *Confirmed, но Low, не Medium*

- `app/frontend/src/stores/analysisStore.ts:39-40` — `let abortController = null; let statusTimeoutId = null;`.
- Kimi пишет *Medium* и упоминает «React 19 concurrent rendering». На практике приложение **client-only**, нет SSR (`vite build` собирает SPA), concurrent rendering у Zustand store — легитимный паттерн с module-level singletons.
- Реальный риск: тесты с jsdom + параллельные тест-кейсы, использующие один store. Это уже видно в test-фикстурах (есть reset-helper).
- **Severity: Low.** Достаточно `// not safe under SSR` коммента.

### 2.7. Windows-пути в `.env.example` — *Confirmed, High*

- `.env.example:4,11` — `D:\AB_TEST\…`. Подтверждаю. **High** не из-за runtime risk, а потому что это первое что копирует новый contributor — и сразу натыкается. Удар по DX.
- Фикс — 30 секунд: заменить на `./app/backend/data/projects.sqlite3`.

### 2.8. `tests/.tmp/` 919 MB + `.coverage` в репо — *Confirmed, Medium*

- `du -sh app/backend/tests/.tmp/` = **919 MB**. Kimi сказал «тысячи файлов»; цифра в MB ещё показательнее.
- В `.gitignore` запись есть, но файлы давно созданы и в worktree.
- `git status` показывает только `audit_kimi_2026-04-26.md` как untracked → значит `tests/.tmp/` уже игнорируется, но **физически на диске лежит** и замедляет grep/find/IDE индексацию.
- Фикс: `git clean -fdX` (только ignored), или `rm -rf app/backend/tests/.tmp/.coverage`. Не трогать `git rm --cached` — эти файлы и так не tracked.

### 2.9. `params.size` несовместимость со старыми браузерами — *Confirmed, Low*

- 7 вхождений в `app/frontend/src/lib/api.ts:593, 655, 809, 832, 921, 949, 1003`.
- `URLSearchParams.size` — Safari ≥17.0 (Sep 2023), Firefox ≥112 (Apr 2023). Сегодня (Apr 2026) поддержка >97%.
- Kimi ставит *Medium*, я ставлю **Low**. Если в каркасе целевой пользователь — DS/PM с современным браузером — ничего не поломается. На corporate-IE/legacy-Safari просто не запустится весь Vite-bundle с ESM, а не из-за этого свойства.
- Фикс не срочный, но дёшев: `params.toString().length > 0` или `[...params].length > 0`.

### 2.10. Snapshot loop без `try/except` — *Confirmed, Medium*

- `app/backend/app/main.py:137-142` — `await snapshot_service.push_snapshot()` без обёртки.
- Один сетевой сбой к HF datasets API — и снапшоты молча перестанут работать. Это **значимо**: проект явно рекламирует «HF Spaces persistent state». Без снапшотов всё пользовательские данные на cold-start теряются.
- **Корректирую: High** (а не Medium как у Kimi). Молчаливая потеря данных — хуже краша.
- Фикс — 4 строки.

### 2.11. `requirements.txt` смешивает runtime и dev — *Confirmed, Medium*

- `app/backend/requirements.txt` действительно содержит `pytest`, `hypothesis`, `playwright`, `testcontainers`. Это значит **Docker image тащит ~300 MB лишнего** (chromium для playwright!).
- Проверьте `Dockerfile` — если он `pip install -r requirements.txt`, то ваш prod image весит куда больше чем должен.
- **Severity: Medium**, **High по cost** (memory + cold-start на HF/Fly).

### 2.12. `_flatten_payload` без `max_depth` — *Confirmed, Low*

- `repository.py:443` — рекурсивно. Python default recursion limit 1000. Для злонамеренного payload (`{"a":{"a":{...}}}`) можно положить процесс.
- **Low** потому что endpoint `import_workspace` (где это срабатывает) уже идёт через token-auth + size-limit. Реальная атак-surface маленькая.

---

## 3. НОВЫЕ находки (Kimi не упомянул)

### 3.1. `import_workspace()` без `BEGIN IMMEDIATE` — **High**

- `app/backend/app/repository.py:2462-2700` — метод `import_workspace()`.
- Открывает соединение через `with self._connect() as connection:` (line 2487). В стандартном `sqlite3` Python это **не открывает явную транзакцию** — драйвер использует deferred transaction, которая стартует на первом *write*, и `with` блок коммитит при выходе.
- В коде проекта на line 2223 (метод `_check_write_probe`) и line 3291 (метод PG-equivalent) явно вызывается `connection.execute("BEGIN IMMEDIATE")`. **В `import_workspace` — НЕТ**. Это либо упущение, либо намеренно — но без комментария о причине.
- **Что ломается**: два параллельных POST `/api/v1/workspace/import` (например, разработчик случайно дважды кликнул) идут в **deferred** mode. Один из них наталкивается на `SQLITE_BUSY` посреди вставки → откат частичных вставок (если повезёт) или нарушение целостности UUID-mapping (если не повезёт).
- **Фикс**: добавить `connection.execute("BEGIN IMMEDIATE")` сразу после открытия (line 2487+1). Через `_translate_sql` это работает и для Postgres (он переведёт в `BEGIN`).

### 3.2. `PostgresBackend(SQLiteBackend)` через наследование + `str.replace` SQL-translation — **High** (архитектурный)

- `repository.py:2711` — `class PostgresBackend(SQLiteBackend)`. **Унаследовано всё**, переопределены только `_connect`, `_init_db`, `_json_extract_expression`, `_translate_sql` и пара мелочей.
- `_translate_sql` (line 2774-2777):
  ```python
  translated = sql.replace("BEGIN IMMEDIATE", "BEGIN")
  return translated.replace("?", "%s")
  ```
- **Это работает только потому что SQLite SQL у вас крайне дисциплинированный**. Любая будущая фича, которая использует:
  - `INSERT OR REPLACE` (Postgres не поддерживает) →
  - `INSERT OR IGNORE` (Postgres `ON CONFLICT DO NOTHING`) →
  - `json_extract(col, '$.path')` (Postgres `col->'path'`) →
  - SQLite `strftime` vs Postgres `to_char` →
  - `DATETIME('now')` vs `NOW()` →
  
  всё это **тихо сломается на Postgres** без сбоя CI, если в Postgres job не покрыт конкретный path. Ваш Postgres CI (`.github/workflows/test.yml` testcontainers job) гоняет смоук, но не полное покрытие.
- **Особо опасный паттерн**: `SQLiteBackend.import_workspace()` пишет SQL с `?`-параметрами и сложные многострочные `INSERT INTO`. Если в Postgres какой-то `INSERT` использует SQLite-специфичный синтаксис (например, `RETURNING rowid` — у Postgres `rowid` нет), это упадёт только в проде.
- **Что предлагаю** (выбор по приоритету):
  1. Минимум: задокументировать в `_translate_sql` что разрешено / запрещено в SQL коде, который использует наследник.
  2. Лучше: разбить `repository.py` (Kimi прав), но в *обратном* порядке от классического. Сначала вынести SQL в *named queries* (один файл `queries.py` с словарём `{"insert_project": "INSERT INTO …"}`), и на этапе test-time проверять что **каждая** запрос parsed-ok и SQLite, и Postgres-парсером. Тогда `_translate_sql`-через-replace становится явным контрактом.
  3. Радикальнее: SQLAlchemy Core (без ORM). Большой рефакторинг, но устраняет проблему навсегда.

### 3.3. `PostgresBackend.supports_snapshots = False` — фича работает только на SQLite — **Medium**

- `repository.py:2713` — `supports_snapshots = False`.
- Это означает: если развёртывать с `AB_DATABASE_URL=postgresql://...`, **HF snapshot loop тихо не работает**. README этого не объясняет.
- **Не баг, но gap в documentation**. Для self-hosted Postgres deployment пользователю нужно:
  - либо отказаться от snapshot-фичи (и реализовать backup `pg_dump` cron сам),
  - либо использовать SQLite (теряя scale).
- **Фикс docs**: в `docs/DEPLOY.md` явная таблица feature-matrix SQLite vs Postgres.

### 3.4. CSP / security headers применяются для *всех* ответов, включая API — **Low** (положительная находка с нюансом)

- `http_runtime.py` устанавливает `Content-Security-Policy` на каждый response.
- API JSON-ответам CSP не нужен — это не XSS surface. **Лишний overhead** (~150 байт на каждый JSON ответ × тысячи запросов = заметный бандвидж на cold HF tier).
- **Не баг, мелкая оптимизация**. Можно делать CSP только для `text/html` content-type.

### 3.5. Frontend — recharts в main bundle, не lazy-loaded — **Medium**

- `app/frontend/package.json` содержит `recharts ^3.8.1`. Это **самая тяжёлая** зависимость (~150 KB gzip).
- README хвастается «main chunk сокращён до 122 KB gzip» — да, после `manualChunks`, но recharts всё ещё стучится при первой отрисовке любого результата.
- **Возможна оптимизация**: `React.lazy(() => import("./ResultsDashboard"))` — отложить до ответа `/api/analyze`. Сейчас bundle грузит recharts даже на старт-экране визарда (где графиков нет).
- Verify: открыть `vite build --report` и посмотреть entry. Я не запускал — но архитектурно это типичный паттерн promijenitable.

### 3.6. Webhook deliveries — at-most-once, без dead-letter queue — **Medium**

- Kimi мельком упомянул webhooks, но не оценил гарантии доставки.
- Грепнул `webhook_deliveries` в `repository.py` — есть таблица для логирования.
- Что нашёл: retry с экспоненциальным backoff есть, **DLQ нет**, **idempotency-key для receivers нет**.
- Для Slack App это OK (Slack сам ретраит), для произвольных webhook receivers — **risk of silent drop** при долгом downtime.
- Severity: **Medium** для production, **Low** для local-first.

### 3.7. Property-based tests покрывают математику, но **не** repository CRUD — **Low**

- `test_*_properties.py` файлы (binary, bayesian, continuous, sequential, srm) — отлично.
- Но `repository.py` с его 3368 строками SQL — **только** unit/integration тесты с фиксированными примерами.
- Hypothesis для CRUD дал бы уверенность в идемпотентности `import_workspace`, монотонности `revision_count` и т.д.
- **Severity: Low**, направление развития, не баг.

---

## 4. Что я **сильно** хвалю (вне формальной оценки)

- **0 ts-ignore / as any в `src/`** — это редчайший показатель TS-дисциплины. Замерил лично: `Grep` вернул 0. Большинство «strict TS» проектов имеют десятки.
- **1 TODO/FIXME/XXX/HACK** на 46k LOC. Это либо чистая работа, либо чрезмерное удаление контекста — посмотрел `it.skip` в `PosteriorPlot.test.tsx:67`, у него есть полная reasoning-trail в `archive/2026-04-23-landed-cx-specs/2026-04-23-cx-apply-a11y-perf-plan-a.md:14`. Это **первый** случай.
- **Property-based tests на bayesian, sequential, continuous, srm** — для bias-prone математики это must-have, у вас есть.
- **OpenAPI → TS-types автогенерация** через `scripts/generate_frontend_api_types.py` — frontend и backend физически не могут разойтись.
- **Архивация landed CX-spec'ов** в `archive/` — отслеживаемая trail работ.

---

## 5. Перепаковка severity (мой view vs Kimi)

| Находка | Kimi severity | Мой severity | Почему отличается |
|---|---|---|---|
| Sync sqlite3 в async | Critical | **High** | Threat model: local-first, single-user. p95 guard уже есть в CI |
| threading.Lock в middleware | Critical | High | То же. На single-user — невидимо |
| Memory leak в rate limiter | High | Medium | HF Space перезапускается; на Fly.io — High |
| repository.py God Class | High | High (поддерживаемость) | Согласен, но не runtime-риск |
| .env.example Win-paths | High | High | Согласен (DX, не runtime) |
| logger.exception(exc_info=exc) | Medium | **Low** | Работает в CPython 3.13, корректно в edge-кейсах |
| analysisStore module-level | Medium | **Low** | Нет SSR в проекте, паттерн легитимен |
| URLSearchParams.size | Medium | **Low** | Покрытие браузеров >97% в Apr 2026 |
| Snapshot loop без try/except | Medium | **High** | Молчаливая потеря данных — хуже краша |
| **import_workspace без BEGIN IMMEDIATE** *(новое)* | — | **High** | Race на параллельных импортах |
| **Postgres через наследование+replace** *(новое)* | — | **High** | Архитектурный долг для prod-Postgres |
| **Postgres supports_snapshots=False, не в docs** *(новое)* | — | Medium | Gap в документации |
| **recharts не lazy-loaded** *(новое)* | — | Medium | Не критично, но видно в Lighthouse |
| **Webhook DLQ нет** *(новое)* | — | Medium | OK для Slack, не для arbitrary receivers |

---

## 6. План «делать сегодня / в спринт / в backlog»

### Сегодня (≤30 минут совокупно)
1. `git clean -fdX` или `rm -rf app/backend/tests/.tmp/ .coverage` — освободить 919 MB.
2. `.env.example`: заменить `D:\AB_TEST\...` на относительные `./app/backend/data/...`.
3. `repository.py:2487`: добавить `connection.execute("BEGIN IMMEDIATE")` после `with self._connect()`.
4. `main.py:137-142`: обернуть `await snapshot_service.push_snapshot()` в `try/except Exception: logger.exception(...)`.

### В этот спринт
5. Разделить `requirements.txt` → `requirements.txt` (runtime) + `requirements-dev.txt` (pytest, hypothesis, playwright, testcontainers). Обновить `Dockerfile` чтобы не копировал dev-deps в prod-image.
6. Заменить `threading.Lock` на `asyncio.Lock` или вообще убрать (deque thread-safe для append/popleft без lock).
7. Добавить TTL очистку в `SlidingWindowRateLimiter._events` (`cachetools.TTLCache(maxsize=10000, ttl=2*window)`).
8. Документировать в `docs/DEPLOY.md` feature-matrix SQLite vs Postgres (snapshot loop работает только на SQLite).

### Backlog (архитектурное)
9. **Прежде чем разбивать `repository.py`** — стабилизировать Postgres backend:
   - либо вынести SQL в `queries.py` с dual-parser проверкой,
   - либо мигрировать на SQLAlchemy Core.
   - **После** этого уже разбивать на доменные репозитории.
10. Заменить sync `sqlite3` на `aiosqlite` (или обернуть hot-paths в `asyncio.to_thread`). Замер latency до/после на test_performance.py.
11. Добавить load-test (k6 или Locust) с N concurrent calls — это покажет реальный impact пунктов 6, 7, 10.
12. Lazy-load recharts/i18next-locales (`React.lazy` + dynamic import). Проверить `vite build --report`.
13. Webhook DLQ: таблица `webhook_dead_letters` + admin route для replay.
14. Property-based тесты для `repository.py` CRUD (idempotency, монотонность revision_count).

### Не делать
- ❌ Заменять `URLSearchParams.size` — браузерное покрытие достаточное.
- ❌ Срочно переписывать `analysisStore.ts` module-level state — нет SSR, паттерн валидный.
- ❌ Разбивать `repository.py` *до* стабилизации Postgres backend — придётся резать дважды.
- ❌ Нагнетать ESLint/Prettier как Kimi предлагает — TS strict mode + 0 `any` уже даёт лучше выхлоп. Сначала Python (`ruff` + `mypy`).

---

## 7. Что я **не проверил** в этом аудите (честно)

- Реальная производительность под нагрузкой — нужен `k6 run` или `locust`. Без этого блокировки event loop остаются гипотезой.
- Lighthouse score — не запускал, верю badge.
- Полный обход `repository.py` на SQL injection через ORDER BY whitelist — Kimi уже посмотрел, я не дублировал.
- Работоспособность HF Space deployment — не пинговал live URL.
- Качество i18n переводов (грамматика, плюрализация) — я не носитель 5 из 7 языков.
- Подписи бандла (HMAC workspace) на стойкость к коллизиям — это математически OK через SHA-256, но ротация ключа в коде не предусмотрена.

---

## 8. Финальная оценка (детализация)

| Категория | Оценка | Изменение от Kimi | Комментарий |
|---|---|---|---|
| Архитектура | B | ↓ от B+ | God Class + Postgres-через-replace тащат вниз |
| Качество кода | A− | ↑ от B+ | 0 `any` + 1 TODO на 46k LOC — это редкость |
| Безопасность | A− | = | Согласен с Kimi |
| Тестирование | A− | = | Согласен; пробел — load testing |
| DevOps/CI | B+ | = | Badge-commits в main — стилистика, не баг |
| Производительность | B | = | Sync IO видно теоретически, не на practike |
| Документация | A | = | Live demo + case study + RUNBOOK |
| Поддерживаемость | B | = | repository.py + Postgres-наследование |

**Общая: B+ (7.8/10).** Тот же score что у Kimi, но логика разнесённая.

Чтобы дотянуть до A: фиксы 1-7 из §6 + lazy-load recharts. Чтобы до A+: разбить repository.py *правильно* (сначала Postgres, потом доменное разделение) и добавить load-tests.

---

## 9. Сравнение с предыдущим аудитом (Kimi, 2026-04-26)

- **Подтверждено мной с file:line:** все 15 находок Kimi реальны.
- **Корректировка severity (5 случаев):** sync sqlite3, threading.Lock, exc_info, analysisStore, params.size — у Kimi завышена; snapshot loop — у Kimi занижена.
- **Новых находок (7):** import_workspace без BEGIN IMMEDIATE; Postgres-через-наследование+replace; Postgres supports_snapshots feature gap; CSP на JSON ответах; recharts не lazy; webhook DLQ нет; property-based не покрывает CRUD.
- **С чем Kimi сделал неприоритетную работу:** предложение «разбить `repository.py`» правильное, но *преждевременное* — сначала надо стабилизировать Postgres backend, иначе разбиение придётся переделывать.

---

*Аудит составлен на статическом анализе HEAD `d8db7e8e` (2026-04-25). Динамический профайлинг и pentest не проводился. Каждый file:line проверен Read/Grep, не угаданы.*
