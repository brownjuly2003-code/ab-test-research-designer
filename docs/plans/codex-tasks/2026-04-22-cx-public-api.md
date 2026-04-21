# CX Task: Public API surface — Redoc UI, API key management, per-key rate limits

## Goal
Превратить FastAPI-приложение в `D:\AB_TEST\` из single-user local tool в multi-consumer public API: подключить Redoc на `/docs`, добавить API key management UI, разделить rate limits по ключам, документировать contract для внешних интеграторов.

## Context
- Репо: `D:\AB_TEST\`, `main`, HEAD после v1.0.0. Не ветка, не push.
- Текущее состояние аутентификации:
  - `AB_API_TOKEN` (single write token), `AB_READONLY_API_TOKEN` (single read token) — env-based, shared by all consumers.
  - Rate limits: global `AB_RATE_LIMIT_REQUESTS` / `AB_RATE_LIMIT_WINDOW_SECONDS` через middleware в `app/backend/app/http_runtime.py`.
  - Auth-failure throttle отдельный, `AB_AUTH_FAILURE_*`.
- FastAPI auto-генерит OpenAPI на `/openapi.json` и Swagger на `/docs` по умолчанию. Нужно заменить Swagger на Redoc (более читаемый для внешних), оставив OpenAPI доступным.
- Для multi-consumer:
  - Персонализированные API keys в БД — хеши, не plaintext.
  - UI для генерации / revoke keys (admin-only).
  - Per-key rate limiting (token-bucket в SQLite или in-memory с key-based bucket).
  - Audit log (уже есть endpoint `/api/v1/audit`) — начать писать туда key-level events.

## Deliverables
1. **Backend: API key storage + management:**
   - Новая таблица `api_keys` в `app/backend/app/repository.py`:
     - `id` (uuid)
     - `name` (user-provided label)
     - `key_hash` (sha256 of plaintext key)
     - `scope` (`Literal["read", "write", "admin"]`)
     - `created_at`, `last_used_at`, `revoked_at` (nullable)
     - `rate_limit_requests` / `rate_limit_window_seconds` (per-key override, nullable — fallback к глобальному)
   - Миграция в schema-versioner (см. существующий паттерн в `repository.py`).
   - Endpoints (admin-only, защищены `AB_ADMIN_TOKEN` через новый env):
     - `POST /api/v1/keys` — создать новый key, вернуть plaintext **один раз** в response, сохранить только hash.
     - `GET /api/v1/keys` — список keys (без plaintext, только `id/name/scope/created_at/last_used_at/revoked_at`).
     - `POST /api/v1/keys/{id}/revoke` — soft revoke.
     - `DELETE /api/v1/keys/{id}` — hard delete (после revoke).
   - Схемы в `app/backend/app/schemas/api.py`: `ApiKeyCreateRequest`, `ApiKeyCreateResponse` (с plaintext), `ApiKeyRecord` (без plaintext), `ApiKeyListResponse`.

2. **Backend: auth dependency расширить:**
   - `require_auth` / `require_write_auth` / `require_read_auth` сейчас проверяют env-token. Дополнить: если env-token не совпал, попробовать найти ключ по `key_hash = sha256(token)` в БД, проверить `scope` и `revoked_at IS NULL`, обновить `last_used_at`.
   - Сохранить обратную совместимость: env-tokens продолжают работать (shared backdoor для legacy).

3. **Backend: per-key rate limiting:**
   - В `http_runtime.py` rate-limiter middleware — ключ bucket'а сейчас `client_ip` или `auth_header`. Дополнить: если request аутентифицирован через БД-ключ, bucket key = `api_key:{id}`; override limits из БД. Иначе — default.
   - Unit-тесты: два запроса с разными ключами имеют независимые buckets.

4. **Backend: Redoc UI:**
   - В `app/backend/app/main.py`: заменить/дополнить `docs_url` на `/redoc` (уже дефолт FastAPI — убедиться что активно). Swagger доступен на `/docs` по умолчанию; перенести Redoc на `/api/docs` если хотим clean URL, либо оставить дефолты.
   - Настроить OpenAPI `info`:
     - `title = "AB Test Research Designer API"`
     - `version = settings.app_version` (динамично, `1.0.0`)
     - `description = <из README excerpt>`
     - `contact`, `license` fields.
   - В `/redoc` и `/docs` — доступ публичный (read-only страница, сам запрос к защищённым endpoints потребует auth).

5. **Frontend: API key management page:**
   - Новый компонент `app/frontend/src/components/ApiKeyManager.tsx`: доступен только если юзер ввёл `AB_ADMIN_TOKEN` в settings. Показывает список keys, кнопка «Create new», modal с scope selector (read/write/admin) + optional rate-limit override. При создании — показать plaintext **один раз** с warning и copy-button.
   - Маунт в новом табе `Sidebar` — добавить рядом с `Projects` / `System`: `API keys` (показывается только если admin-аутенфицирован).
   - Language switcher: ключи translation для новых строк (если i18n таск уже выполнен — добавить в `en.json` + `ru.json`).

6. **Audit log integration:**
   - `routes/audit.py` extend — писать event'ы на key lifecycle: `api_key_created`, `api_key_revoked`, `api_key_used`. С указанием `key_id` (не plaintext).
   - GET `/api/v1/audit?key_id=X` — filter по key.

7. **Тесты:**
   - Backend:
     - `test_api_keys.py` — create, list, revoke, delete flows.
     - `test_api_routes.py` extend — auth через БД-ключ вместо env-токена, corner cases (revoked key → 401, missing scope → 403).
     - `test_repository.py` extend — миграция таблицы `api_keys`.
     - `test_rate_limit_per_key` — два ключа, разные buckets.
   - Frontend:
     - `ApiKeyManager.test.tsx` — render, create flow, revoke flow.
     - `a11y-api-keys.test.tsx` — axe по новому таб.
   - Обновить existing audit тесты на key-level events.

8. **Regen контрактов:**
   - `python scripts/generate_frontend_api_types.py --check` = 0.
   - `python scripts/generate_api_docs.py --check` = 0 — `docs/API.md` включает новые endpoints.

9. **Documentation:**
   - `docs/API.md` — будет обновлён автоматом через regen.
   - Новая секция в `README.md`: «Public API access» с примером curl-запроса с API-key.
   - Обновить `docs/RUNBOOK.md`: «Rotating API keys» процедура.

10. **Один коммит:**
    ```
    feat: public API surface with per-key auth, rate limits, and redoc docs
    ```

11. **Отчёт `docs/plans/2026-04-22-public-api-report.md`:**
    - Список новых endpoints.
    - Пример curl-flow (создать key, использовать его на protected endpoint, revoke).
    - Screenshot Redoc / Swagger страниц (ссылка на archive если e2e гоняет).
    - Bundle budget check (новый `ApiKeyManager.tsx` lazy-loaded).

## Acceptance
- `scripts\verify_all.cmd --with-e2e` = exit 0.
- `curl http://127.0.0.1:8008/redoc` → 200 HTML с title «AB Test Research Designer API».
- `curl http://127.0.0.1:8008/openapi.json | jq .info.version` = `"1.0.0"`.
- Backend tests +15–20 new (keys CRUD, per-key rate limit, audit integration).
- Frontend tests +5–8 (ApiKeyManager component + a11y).
- Lighthouse a11y ≥ 0.9.
- Bundle main JS gzip < 140 KB (ApiKeyManager должен быть lazy).
- Commit subject уникальный, `Co-Authored-By: Codex <noreply@anthropic.com>`.
- Этот CX-файл стадж в тот же коммит.
- `git status --short` = пусто.

## How
1. Baseline: `git status --short` = пусто, `scripts\verify_all.cmd` = 0.
2. Прочитать `app/backend/app/repository.py` (schema-versioner), `http_runtime.py` (rate limiter), `main.py` (app setup).
3. Добавить таблицу `api_keys` + migration step.
4. Расширить auth middleware.
5. Добавить endpoints + тесты backend.
6. Расширить rate limiter per-key.
7. Написать Frontend компонент + монтировать + тесты.
8. Regen контрактов.
9. README / RUNBOOK.
10. Commit + verify + report.

## Notes
- **CX-файл hygiene:** staging этот файл.
- **Commit subject hygiene:** проверка на дубль.
- **БЕЗОПАСНОСТЬ:** plaintext ключа возвращать **один раз** при создании; never log его, never save anywhere кроме response-body. Hash — sha256 без salt (keys достаточно длинные).
- **БЕЗОПАСНОСТЬ:** `AB_ADMIN_TOKEN` env required для `/api/v1/keys` endpoints; если не задан — все key management endpoints возвращают 401. Это отдельный guard выше scope-based check.
- **Backward compat:** env-based `AB_API_TOKEN` / `AB_READONLY_API_TOKEN` — сохраняются, документировать как «legacy shared tokens».
- **Rate limit bucket:** использовать in-memory dict с TTL (уже паттерн в codebase), per-key. Не лепить Redis / внешние deps.
- **OpenAPI tags:** сгруппировать endpoints по категориям (`calculations`, `projects`, `templates`, `audit`, `keys`, `workspace`) — улучшит Redoc навигацию.
- **НЕ** делать OAuth / JWT — это не в scope, API keys достаточно для v1.x.
- **НЕ** writing tests для UI flow через скриншоты — axe + unit достаточно.
- Backend `test_performance` может флапнуть — перезапустить один раз.
- **НЕ** пушить на remote.

## Out of scope
- OAuth 2.0 / JWT / OIDC
- User accounts (multi-user = only API keys, no login UI)
- Billing / usage tracking
- Webhooks for audit events
- Key rotation automation
- TLS termination (обрабатывается на Fly.io / reverse proxy)
