# Глубокий аудит проекта AB_TEST (AB Test Research Designer)

**Дата аудита:** 2026-04-26  
**Версия проекта:** 1.1.0  
**Аудитор:** Kimi Code CLI  
**Область аудита:** Полный стек (Backend, Frontend, DevOps, Безопасность, Тестирование, Документация)

---

## 1. Общая информация о проекте

AB Test Research Designer — это local-first инструмент для планирования A/B и мультивариантных тестов.  
**Технологический стек:**
- **Backend:** Python 3.13, FastAPI 0.128.0, Pydantic 2.12.5, Uvicorn 0.40.0
- **Frontend:** React 19.1.0, TypeScript 5.8.3, Vite 7.1.2, Zustand 5.0.12, i18next, Recharts, Lucide React
- **База данных:** SQLite (основной) / PostgreSQL (опциональный backend через `AB_DATABASE_URL`)
- **Тестирование:** pytest + Hypothesis (property-based), Vitest + jsdom + axe (a11y), Playwright (E2E)
- **Инфраструктура:** Docker, Docker Compose, GitHub Actions, Fly.io, Hugging Face Spaces
- **Документация:** MkDocs Material, OpenAPI (Swagger/Redoc)

**Ключевые возможности:**
- Детерминированный расчёт размера выборки для бинарных и непрерывных метрик
- Bayesian и group-sequential (O'Brien-Fleming) расчёты
- CUPED-варианты для непрерывных метрик
- Локальное хранилище проектов с историей ревизий
- Мультиязычность (7 языков, включая RTL для арабского)
- Экспорт отчётов (PDF, CSV, XLSX, Markdown, HTML)
- API-ключи с rate limiting, webhook-уведомления, Slack App интеграция
- Workspace backup/restore с SHA-256 и опциональной HMAC-подписью

---

## 2. Сильные стороны проекта

### 2.1. Архитектура и качество кода
- **Чёткое разделение ответственности:** deterministic calculator ↔ rules engine ↔ report composer ↔ LLM adapter. Это архитектурно верное решение, которое изолирует математику от эвристик и AI.
- **Протокол DatabaseBackend** (`repository.py`) с реализациями SQLiteBackend и PostgresBackend — хороший паттерн для абстракции хранилища.
- **Property-based тестирование** через Hypothesis (`test_binary_properties.py`, `test_bayesian_properties.py`, `test_continuous_properties.py`, `test_sequential_properties.py`, `test_srm_properties.py`) — редкий и высоко ценимый подход для математических модулей.
- **Accessibility-first подход:** 12+ dedicated a11y-тестов с axe-core, которые гейтят CI при критических/серьёзных нарушениях WCAG 2.1 AA.
- **TypeScript strict mode** включён, API-контракты генерируются из OpenAPI (`scripts/generate_frontend_api_types.py`) — снижает риск рассинхронизации backend/frontend.
- **Схемная миграция SQLite** через `PRAGMA user_version` + `ALTER TABLE ADD COLUMN` — прагматичный подход для embedded БД.

### 2.2. Безопасность
- **Rate limiting** с Sliding Window на уровне middleware (`SlidingWindowRateLimiter`).
- **Auth-failure throttling** с `Retry-After` — защита от брутфорса токенов.
- **hmac.compare_digest** для сравнения токенов — защита от timing-атак.
- **API-ключи** хранятся только в виде SHA-256 хешей, plaintext отображается один раз при создании.
- **Request body size guards** — раздельные лимиты для обычных запросов и workspace bundles.
- **Security headers** (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy) применяются ко всем ответам.
- **Workspace signing** через HMAC-SHA256 с настраиваемым ключом.
- **LLM-токены** передаются через заголовки браузерной сессии (`X-AB-LLM-Token`), не сохраняются на backend.

### 2.3. DevOps и CI/CD
- **Матричный CI** (Ubuntu + Windows) с разными уровнями верификации.
- **Отдельный job для Postgres** — проверяет cross-backend совместимость.
- **Docker compose verification** с secure token flow в CI.
- **Lighthouse CI** с жёсткими порогами (accessibility ≥ 0.90 как error).
- **Dynamic badges** — автоматическое обновление метрик тестов, покрытия и Lighthouse через GitHub Actions.
- **Multi-arch Docker image** (linux/amd64, linux/arm64) публикуется в GHCR.
- **Benchmark guard** для backend (p95 latency ≤ 100ms для binary calculation).

### 2.4. Тестирование
- **233+ backend тестов** + property-based покрытие.
- **200+ frontend unit тестов** + a11y regression tests.
- **Playwright E2E smoke flow** — сквозной сценарий от wizard до экспорта.
- **Workspace backup roundtrip tests** — проверка целостности и подписи.

### 2.5. Документация
- **Обширная документация:** ARCHITECTURE.md, API.md, RUNBOOK.md, RULES.md, RELEASE_CHECKLIST.md, CHANGELOG.md.
- **MkDocs Material site** с поиском и локализацией.
- **Case study** (checkout redesign) с реальными цифрами и воспроизводимым скриптом.
- **Live demo** на Hugging Face Spaces с seeded данными.

---

## 3. Критические и высокие проблемы

### 3.1. Backend — Блокировка event loop (Критическая)

**Проблема:** `repository.py` использует синхронный `sqlite3` напрямую внутри async FastAPI приложения. Каждый вызов `_connect()` и SQL-запрос блокирует основной event loop uvicorn.

```python
# repository.py
connection = sqlite3.connect(self.db_path)  # синхронный blocking IO
```

**Почему это критично:**
- При одновременных запросах все остальные coroutines "замирают" на время выполнения SQL.
- SQLite с WAL режимом быстрый, но при сложных запросах (например, `list_projects` с 5+ коррелированными подзапросами) latency одного запроса может достигать 10-50ms.
- С `max_supported_variants=10` и property-based тестами нагрузка может быть неочевидной.

**Рекомендация:**
- Перейти на `aiosqlite` для SQLite backend.
- Для Postgres backend (`psycopg_pool.ConnectionPool`) уже используется пул, но вызовы `pool.connection()` также блокируют — нужен `psycopg[binary,pool]` в async режиме или `asyncpg`.
- Альтернатива: оборачивать синхронные вызовы в `asyncio.to_thread()` или `loop.run_in_executor()`.

### 3.2. Backend — Threading Lock в async контексте (Критическая)

**Проблема:** `SlidingWindowRateLimiter` в `http_utils.py` использует `threading.Lock()`:

```python
class SlidingWindowRateLimiter:
    def __init__(self, ...):
        self._lock = Lock()  # threading.Lock
```

Этот lock вызывается внутри `async def add_request_metadata` middleware:

```python
with self._lock:  # блокирует event loop!
    ...
```

**Рекомендация:** Заменить на `asyncio.Lock` или использовать thread-safe структуры без явного лока (например, `collections.deque` с атомарными операциями + `asyncio.Lock` при необходимости).

### 3.3. Backend — Memory leak в Rate Limiter (Высокая)

**Проблема:** `SlidingWindowRateLimiter._events` — dict с ключами по client identifier. Старые ключи (IP-адреса или API key IDs) никогда не удаляются:

```python
self._events: dict[str, deque[float]] = {}
```

При долгой работе (особенно с `auth_failure_limiter`, где ключи — все неудачные IP) словарь будет бесконечно расти.

**Рекомендация:**
- Добавить периодическую очистку (background task) или TTL-механизм.
- Использовать `cachetools.TTLCache` или аналогичную структуру.
- Альтернатива: Redis-backed rate limiter для production.

### 3.4. Backend — Repository.py God Class (Высокая)

**Проблема:** `repository.py` содержит **3368 строк**. Класс `SQLiteBackend` совмещает:
- DDL и schema migrations
- CRUD проектов
- History management (analysis_runs, export_events, project_revisions)
- Audit log
- API key management
- Webhook subscriptions и deliveries
- Slack installations
- Template management
- Workspace export/import/validation
- Payload diff engine
- Backfill migrations

**Последствия:**
- Нарушение Single Responsibility Principle.
- Сложность unit-тестирования (слишком много состояния).
- Риск merge-конфликтов при параллельной разработке.
- Низкая читаемость для новых разработчиков.

**Рекомендация:** Разделить на отдельные модули/классы:
- `ProjectRepository`
- `HistoryRepository` (analysis_runs, export_events, revisions)
- `AuditRepository`
- `ApiKeyRepository`
- `WebhookRepository`
- `TemplateRepository`
- `WorkspaceRepository`

### 3.5. Backend — Некорректное использование exc_info (Средняя)

**Проблема:** `http_runtime.py` строка 373:

```python
logger.exception("Unhandled exception while serving %s %s", request.method, request.url.path, exc_info=exc)
```

`logger.exception()` уже автоматически подставляет `exc_info=True`. Передача `exc_info=exc` (где `exc` — экземпляр исключения, а не bool/tuple) работает в некоторых версиях Python/logging, но является неопределённым поведением и может привести к:
- TypeError в некоторых handler'ах.
- Некорректному форматированию в JSON-логгере.

**Рекомендация:** Заменить на `logger.exception("...", request.method, request.url.path)` без `exc_info=exc`.

### 3.6. Frontend — Module-level mutable state (Средняя)

**Проблема:** `analysisStore.ts` содержит module-level переменные:

```typescript
let abortController: AbortController | null = null;
let statusTimeoutId: number | null = null;
```

Это создаёт:
- Глобальное состояние между разными "сессиями" анализа (хотя store сам по себе глобален).
- Потенциальные проблемы при SSR или concurrent rendering в React 19.
- `statusTimeoutId` имеет тип `number`, но в Node.js `setTimeout` возвращает `Timeout` object — может быть проблема при SSR или тестировании в node environment.

**Рекомендация:** Перенести `abortController` и `statusTimeoutId` внутрь store state (или использовать refs через хук/стор с поддержкой cleanup).

### 3.7. DevOps — Жёстко закодированные Windows-пути в .env.example (Высокая)

**Проблема:** `.env.example` содержит:

```
AB_DB_PATH=D:\AB_TEST\app\backend\data\projects.sqlite3
AB_FRONTEND_DIST_PATH=D:\AB_TEST\app\frontend\dist
```

Это ломает переносимость между ОС. Новые разработчики на macOS/Linux скопируют файл и получат невалидные пути.

**Рекомендация:** Использовать относительные пути или placeholder'ы:
```
AB_DB_PATH=./app/backend/data/projects.sqlite3
AB_FRONTEND_DIST_PATH=./app/frontend/dist
```

### 3.8. DevOps — Засорение репозитория временными файлами (Средняя)

**Проблемы:**
1. `app/backend/tests/.tmp/` содержит **тысячи** SQLite-файлов от прогонов тестов (вижу >500 в листинге, вероятно, гораздо больше). Эти файлы:
   - Не игнорируются `.gitignore` (в `.gitignore` есть `app/backend/tests/.tmp/`, но файлы уже в индексе/рабочей директории).
   - Занимают место и замедляют `git status`, `git grep`.
2. `node_modules/` в корне проекта — явный мусор (не относится к `app/frontend/node_modules`).
3. `.coverage` в корне — артефакт прогона, не должен быть в репозитории.
4. `archive/verify-workspace-backup/` содержит десятки backup snapshot'ов от CI — архивная директория раздута.
5. `.hypothesis/` кэширует примеры Hypothesis — корректно игнорируется `.gitignore`.

**Рекомендация:**
- Добавить `app/backend/tests/.tmp/` в `.gitignore` и удалить из рабочей директории (`git rm -r --cached app/backend/tests/.tmp/`).
- Удалить корневой `node_modules/` и `.coverage`.
- Настроить `archive/verify-workspace-backup/*` в `.gitignore` с сохранением `.gitkeep`.
- Добавить pre-commit hook или CI step для проверки отсутствия артефактов.

### 3.9. DevOps — Runtime и dev зависимости смешаны (Средняя)

**Проблема:** `app/backend/requirements.txt` содержит:

```
pytest==8.4.2
pytest-cov==5.0.0
hypothesis==6.152.1
testcontainers==4.5.0
playwright==1.58.0
```

Это dev/test зависимости, которые увеличивают размер Docker image и поверхность атаки в production.

**Рекомендация:** Разделить на:
- `requirements.txt` — только runtime
- `requirements-dev.txt` — pytest, coverage, hypothesis, testcontainers, playwright
- Обновить `Dockerfile` для установки только `requirements.txt`
- Обновить CI для установки dev-зависимостей отдельно

### 3.10. Frontend — Совместимость URLSearchParams.size (Средняя)

**Проблема:** `api.ts` использует `params.size` для `URLSearchParams`:

```typescript
const path = params.size > 0 ? `/api/v1/projects?${params.toString()}` : "/api/v1/projects";
```

Свойство `URLSearchParams.prototype.size` было добавлено в спецификацию относительно недавно (ES2024/2023) и **не поддерживается** в Safari < 17, Firefox < 112, а также в некоторых embedded браузерах. При `target: ES2020` в `tsconfig.json` TypeScript не полифилит это.

**Рекомендация:** Заменить на `params.toString().length > 0` или `Array.from(params.keys()).length > 0`.

### 3.11. Backend — Snapshot background task без глобального exception handler (Средняя)

**Проблема:** `main.py` lifespan:

```python
async def run_snapshot_loop() -> None:
    while True:
        await asyncio.sleep(snapshot_interval_seconds)
        await snapshot_service.push_snapshot()  # если упадёт — весь таск упадёт
```

Если `push_snapshot()` выбросит исключение (сетевой сбой HuggingFace, диск full, corrupted DB), background task завершится и периодические snapshots перестанут работать.

**Рекомендация:**
```python
async def run_snapshot_loop() -> None:
    while True:
        await asyncio.sleep(snapshot_interval_seconds)
        try:
            await snapshot_service.push_snapshot()
        except Exception:
            logger.exception("snapshot loop iteration failed")
```

### 3.12. Backend — Отсутствие линтеров и форматтеров (Средняя)

**Проблема:** В проекте нет:
- `ruff`, `black`, `mypy` или `pyright` для Python.
- `eslint`, `prettier` для TypeScript/JavaScript.
- `pre-commit` hooks.

**Последствия:**
- Несогласованный стиль кода (особенно в `repository.py` с 3368 строками).
- Отсутствие статического анализа типов в Python (крому Pydantic runtime validation).
- Сложнее поддерживать единообразие в команде.

**Рекомендация:**
- Добавить `ruff` (lint + format) и `mypy`/`pyright` в CI.
- Добавить `eslint` + `prettier` для frontend в CI (сейчас только `tsc --noEmit`).

### 3.13. Backend — Payload diff recursion без ограничения глубины (Низкая)

**Проблема:** `repository.py`:

```python
@staticmethod
def _flatten_payload(value: Any, *, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        ...
        flattened.update(SQLiteBackend._flatten_payload(value[key], prefix=child_prefix))
```

При deeply nested payload (malicious или случайной) возможен `RecursionError`.

**Рекомендация:** Добавить `max_depth` параметр с дефолтом ~10-20 уровней.

### 3.14. Frontend — Playwright E2E тесты вне tsconfig scope (Низкая)

**Проблема:** `tsconfig.json`:

```json
"exclude": ["src/test/e2e-smoke.spec.ts"]
```

E2E спеки исключены из TypeScript проверки. Это означает, что типовые ошибки в E2E тестах не ловятся на этапе `tsc --noEmit`.

**Рекомендация:** Создать отдельный `tsconfig.e2e.json`, который включает E2E файлы и расширяет базовый конфиг, или включить их в основной `tsconfig`.

### 3.15. DevOps — Badge commit'ы в main ветку (Низкая)

**Проблема:** Job `update-metrics-badges` в `.github/workflows/test.yml` коммитит badge JSON файлы напрямую в `main` после каждого push:

```yaml
- name: Commit badge payloads
  run: |
    git commit -m "chore: update badge metrics [skip ci]"
    git push
```

**Риски:**
- Засорение истории git "мусорными" коммитами.
- Race condition при параллельных push'ах (хотя `[skip ci]` предотвращает рекурсию).
- Невозможность защитить main ветку от direct pushes, если badges требуют write access.

**Рекомендация:**
- Генерировать badges динамически через GitHub Actions artifacts + shields.io endpoint (badge already uses raw githubusercontent URL, но файлы всё равно коммитятся).
- Альтернатива: использовать GitHub Gist или внешний сервис для badge data.

---

## 4. Архитектурные и дизайн-замечания

### 4.1. Config — lru_cache для настроек

```python
@lru_cache(maxsize=1)
def get_settings() -> Settings:
```

Settings кэшируются навсегда. При изменении env variables во время работы процесса (например, в Docker сигнал или hot reload) настройки не обновятся. Для большинства случаев это приемлемо, но стоит документировать.

### 4.2. CORS — Динамическое добавление заголовков

В `main.py` CORS-заголовки модифицируются runtime на основе наличия токенов:

```python
if settings.api_token or settings.readonly_api_token ...:
    for header_name in ("Authorization", "X-API-Key"):
        if header_name not in cors_headers:
            cors_headers.append(header_name)
```

Это корректно, но создаёт неявную зависимость: изменение auth-схемы требует синхронного изменения CORS-логики.

### 4.3. Frontend — Хранение sensitive данных в sessionStorage

`api.ts` хранит API токены и LLM токены в `sessionStorage`:

```typescript
const apiSessionTokenStorageKey = "ab-test-research-designer:api-token:v1";
```

`sessionStorage` доступен любому JS-коду на странице (XSS-уязвимость). Хотя приложение local-first и CSP строгий, при XSS injection токены украдены. Для данного threat model (local-first, single-user) это приемлемый компромисс, но стоит документировать.

### 4.4. Repository — SQL-injection защита

Хотя `query_projects` динамически конструирует SQL через f-string:

```python
order_sql = f"ORDER BY {order_column} {normalized_sort_dir}, projects.updated_at DESC"
```

`order_column` и `normalized_sort_dir` валидируются через whitelist — это безопасно. Но `where_sql` также конструируется динамически, хотя значения параметризованы. **Рекомендация:** добавить явный audit или unit-тест на SQLi для `query_projects`.

### 4.5. Healthcheck в Docker

```dockerfile
HEALTHCHECK ... CMD python -c "import os, urllib.request; ... urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3)"
```

Использование `urllib.request` в HEALTHCHECK — рабочее, но `127.0.0.1` внутри контейнера может не совпадать с `AB_HOST=0.0.0.0` при некоторых сетевых конфигурациях Docker (rootless, custom networks). Более надёжно проверять `localhost` или сам `AB_HOST`.

---

## 5. Производительность

### 5.1. Frontend bundle

- `vite.config.ts` использует `manualChunks` для разделения vendor-библиотек — хорошо.
- Размер main chunk сокращён с 247 KB до 122 KB gzip (по README) — отличный результат.
- `chunkSizeWarningLimit: 500` — корректно поднят.

### 5.2. Backend latency

- Есть `test_performance.py` с p95 guard ≤ 100ms — хорошо.
- Однако блокировка event loop SQLite и threading.Lock (см. 3.1, 3.2) делают эти бенчмарки нерепрезентативными под нагрузкой >1 concurrent request.

### 5.3. Database queries

`list_projects` и `query_projects` содержат коррелированные подзапросы для каждой строки:

```sql
SELECT ...,
    (SELECT COUNT(*) FROM project_revisions WHERE project_revisions.project_id = projects.id) AS revision_count,
    (SELECT MAX(created_at) FROM project_revisions WHERE project_revisions.project_id = projects.id) AS last_revision_at,
    ...
```

При 1000+ проектов это N+1 на уровне SQL. Рекомендуется:
- Денормализовать `revision_count` и `last_revision_at` в таблицу `projects`.
- Или использовать `LATERAL` join (Postgres) / `GROUP BY` с `LEFT JOIN` (SQLite 3.39+).

---

## 6. Тестирование — пробелы

### 6.1. Недостаточное покрытие
- Нет нагрузочных тестов (load/stress) для concurrent requests.
- Нет тестов на thread-safety / race conditions в `SlidingWindowRateLimiter`.
- Нет тестов на corruption/recovery SQLite (power loss simulation).
- Нет тестов на CORS preflight с разными origin'ами.
- Нет property-based тестов для `repository.py` CRUD операций.

### 6.2. Frontend тесты
- E2E smoke flow охватывает happy path, но нет тестов на:
  - Offline режим / network failure
  - Rate limiting (429) UI behavior
  - Large workspace import (>8MB)
  - XSS через project name / payload fields

---

## 7. Документация — замечания

- **README** перегружен (436 строк). Рекомендуется вынести секции "Public API access", "Languages", "Docker" в отдельные файлы docs/.
- **ARCHITECTURE.md** хорош, но не описывает data flow при workspace import/export и snapshot service.
- **RUNBOOK.md** (упоминается) — не проверялся, но судя по README содержит инструкции по добавлению локали.
- **API.md** — проверить актуальность при каждом релизе (сейчас есть `scripts/generate_api_docs.py --check` в CI — хорошо).

---

## 8. Итоговая оценка

| Категория | Оценка | Комментарий |
|-----------|--------|-------------|
| **Архитектура** | B+ | Чёткое разделение доменов, но God Class в repository и sync IO в async app снижают оценку. |
| **Качество кода** | B+ | Хорошая типизация, генерация контрактов, но отсутствие линтеров и 3K+ строк в одном файле. |
| **Безопасность** | A- | Отличная защита на уровне middleware, CSP, rate limiting, HMAC. Минус за XSS-риск sessionStorage. |
| **Тестирование** | A- | Property-based, a11y, E2E, benchmark guards. Минус за отсутствие нагрузочных и race-condition тестов. |
| **DevOps/CI** | B+ | Матрица OS, Postgres job, Docker verify, Lighthouse. Минус за badge-commits в main, смешение зависимостей. |
| **Производительность** | B | Быстрые расчёты, оптимизированный bundle, но критические блокировки event loop. |
| **Документация** | A | Обширная, структурированная, с live demo и case study. |
| **Поддерживаемость** | B | Хорошая модульность frontend, но backend repository требует рефакторинга. |

**Общая оценка: B+**

Проект демонстрирует высокий уровень инженерной культуры: property-based тесты, a11y-first подход, мультиязычность, развёрнутая документация и продуманная безопасность. Основные риски сосредоточены в backend around async/await паттернов (blocking SQLite, threading.Lock) и раздутом `repository.py`. Устранение этих проблем выведет проект на уровень A.

---

## 9. Приоритизированный план исправлений

### Немедленно (Critical / High)
1. [ ] Заменить синхронный `sqlite3` на `aiosqlite` или оборачивать в `asyncio.to_thread()`.
2. [ ] Заменить `threading.Lock` на `asyncio.Lock` в `SlidingWindowRateLimiter`.
3. [ ] Добавить TTL-очистку или `cachetools.TTLCache` в rate limiter для предотвращения memory leak.
4. [ ] Разделить `repository.py` на отдельные модули (рефакторинг God Class).
5. [ ] Исправить `.env.example` — убрать абсолютные Windows-пути.
6. [ ] Очистить репозиторий от временных файлов (`tests/.tmp/`, корневой `node_modules/`, `.coverage`).
7. [ ] Разделить `requirements.txt` и `requirements-dev.txt`.

### В ближайшем спринте (Medium)
8. [ ] Исправить `logger.exception(..., exc_info=exc)` на корректное использование.
9. [ ] Добавить `try/except` в `run_snapshot_loop` background task.
10. [ ] Заменить `params.size` на кросс-браузерную альтернативу во frontend API layer.
11. [ ] Добавить `max_depth` в `_flatten_payload` для защиты от RecursionError.
12. [ ] Настроить `ruff` + `mypy` для backend и `eslint` + `prettier` для frontend в CI.
13. [ ] Создать отдельный `tsconfig.e2e.json` для Playwright спек.

### Технический долг (Low / Architectural)
14. [ ] Денормализовать `revision_count`/`last_revision_at` или оптимизировать `list_projects` query.
15. [ ] Пересмотреть стратегию badge-commits (возможно, перейти на динамические endpoints).
16. [ ] Добавить нагрузочные тесты (locust/k6) для concurrent API calls.
17. [ ] Рассмотреть использование Redis для rate limiting в production.
18. [ ] Документировать threat model для sessionStorage token storage.

---

*Аудит выполнен автоматически на основе статического анализа кода, конфигураций и архитектурной документации. Рекомендуется провести дополнительный динамический аудит (runtime profiling, security pentest) для production deployment.*
