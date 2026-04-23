# CX Task: Outbound webhooks for audit events (Slack / generic HTTP)

## Goal
Добавить в `D:\AB_TEST\` outbound webhook механизм для уже существующего audit-log: при значимых событиях (создание/revoke API key, analysis run, workspace import, project archive) отправлять POST на настраиваемые URL. Поддержать Slack incoming-webhook формат и generic JSON. Retry-with-backoff, dead-letter очередь в БД, UI для управления подписками.

## Context
- Репо: `D:\AB_TEST\`, `main`, HEAD после `4099f73c`. Не создавать ветку, не push.
- Verify зелёный: backend 177, frontend 197 unit, `scripts\verify_all.cmd --with-e2e` = 0.
- Audit log уже есть: таблица `audit_events` в `app/backend/app/repository.py`, роутер `routes/audit.py`, события пишутся в `repository._record_audit_event` — сейчас только write в SQLite, без outbound.
- Существующие event types в audit (проверь `grep -rn "record_audit_event\|audit_entries" app/backend/app/`): `project_created`, `project_updated`, `project_archived`, `project_deleted`, `analysis_run_created`, `export_created`, `workspace_imported`, `api_key_created`, `api_key_revoked` (названия уточни в коде).
- Публичный API keys уже есть (`4099f73c`): scope `read/write/admin`; webhooks — отдельная сущность, привязанная к `api_key_id` или глобально (admin-scope).

## Deliverables
1. **БД (migration step в `ProjectRepository`):**
   - Таблица `webhook_subscriptions`:
     - `id` uuid PK
     - `name` text
     - `target_url` text (HTTPS required; validate prefix)
     - `secret` text (HMAC-SHA256 signing secret, stored plaintext — юзер сам ротирует)
     - `format` text — `"generic"` | `"slack"`
     - `event_filter` text — JSON array of event_type strings; empty = all
     - `scope` text — `"global"` | `"api_key"` (+ `api_key_id` nullable)
     - `created_at`, `updated_at`, `last_delivered_at`, `last_error_at` timestamptz
     - `enabled` boolean default true
   - Таблица `webhook_deliveries` (dead-letter + история):
     - `id` uuid PK
     - `subscription_id` FK
     - `event_id` FK → `audit_events.id`
     - `status` — `"pending" | "delivered" | "failed" | "retrying"`
     - `attempt_count` int
     - `last_attempt_at`, `delivered_at` timestamptz
     - `response_code` int nullable
     - `response_body` text (truncated 2KB)
     - `error_message` text nullable
   - Schema version bump в `ProjectRepository.schema_version`.

2. **Backend delivery worker:**
   - Новый модуль `app/backend/app/services/webhook_service.py`:
     - Вызывается из `_record_audit_event` (fire-and-forget через `asyncio.create_task` в FastAPI background, либо через sync `httpx.Client` + ThreadPoolExecutor в lifespan).
     - Для каждого совпадающего `webhook_subscriptions.event_filter` + `enabled=true` — создаёт `webhook_deliveries` row со status `pending`, затем отправляет.
     - Retry policy: exponential backoff 1s/5s/30s/5min/30min (максимум 5 попыток, суммарно ~36 мин). После последней — `status=failed`.
     - HMAC signing: `X-AB-Signature: sha256=<hex(hmac(secret, body))>` — generic; для Slack используется `incoming-webhook` формат без signing (Slack не проверяет).
     - Generic body: `{ "event_type": "...", "event_id": "...", "timestamp": "...", "actor": "...", "payload": {...} }`.
     - Slack body: `{ "text": "<human-readable summary>", "blocks": [...] }` — форматер в отдельной функции.

3. **Backend endpoints (admin-guarded):**
   - `POST /api/v1/webhooks` — create subscription. Body: `{ name, target_url, secret, format, event_filter, scope }`. Response: full record + `secret` plaintext once (сразу прячем при list).
   - `GET /api/v1/webhooks` — list.
   - `GET /api/v1/webhooks/{id}` — get.
   - `PATCH /api/v1/webhooks/{id}` — partial update (enabled, event_filter, target_url).
   - `DELETE /api/v1/webhooks/{id}` — hard delete (cascades deliveries).
   - `POST /api/v1/webhooks/{id}/test` — отправить фиктивный event `webhook.test` на target_url, вернуть response code.
   - `GET /api/v1/webhooks/{id}/deliveries?limit=50&status=failed` — история.

4. **Схемы в `app/backend/app/schemas/api.py`:**
   - `WebhookSubscriptionCreateRequest`, `WebhookSubscriptionRecord`, `WebhookDeliveryRecord`, `WebhookListResponse`, `WebhookTestResponse`.
   - Все с `ConfigDict(extra="forbid")` как остальные.

5. **Frontend UI:**
   - Новый lazy-loaded компонент `app/frontend/src/components/WebhookManager.tsx`: монтируется в sidebar рядом с `ApiKeyManager` (admin-only). List, Create (modal), Test button, Delete, Deliveries drawer.
   - i18n strings в `en.json` + `ru.json` (секция `webhooks.*`).
   - A11y: диалог create/edit — `role="dialog"`, focus trap, Escape close.
   - Тест `WebhookManager.test.tsx` + `a11y-webhooks.test.tsx` (pattern как `ApiKeyManager.test.tsx`).

6. **Тесты backend:**
   - `app/backend/tests/test_webhook_service.py`:
     - create subscription → triggers on matching event → http call made (mock `httpx` via `responses` or `httpx.MockTransport`).
     - retry with backoff on 5xx.
     - max attempts → status=failed, error recorded.
     - signature verification: compute HMAC and compare.
     - Slack format: verify body structure.
   - `app/backend/tests/test_api_routes.py` extend: webhooks CRUD admin-guard (non-admin → 401/403).

7. **Regen contracts:**
   - `python scripts/generate_frontend_api_types.py --check` = 0.
   - `python scripts/generate_api_docs.py --check` = 0 — `docs/API.md` включает webhook endpoints.

8. **Docs:**
   - `README.md` — короткая секция «Webhooks» в Public API с curl-примером.
   - `docs/RUNBOOK.md` — «Webhook troubleshooting» (проверить deliveries, retry dead-letter).

9. **Один коммит:**
   ```
   feat: outbound webhooks for audit events with slack and generic formats
   ```

10. **Отчёт `docs/plans/2026-04-22-webhooks-report.md`:**
    - Схема БД (таблицы + поля).
    - Endpoints.
    - Example curl: create slack webhook + fire test event.
    - Known limitations (например, no dedup of events, no per-event ordering guarantees — single worker FIFO).

## Acceptance
- `scripts\verify_all.cmd --with-e2e` = exit 0.
- Backend tests: +15–25 новых (webhook_service unit + api_routes integration).
- Frontend tests: +5–8 (WebhookManager unit + a11y).
- Lighthouse a11y ≥ 0.9, performance ≥ 0.85 (bundle growth минимальный из-за lazy).
- `curl -X POST http://127.0.0.1:8008/api/v1/webhooks -H "Authorization: Bearer $AB_ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"name":"test","target_url":"https://httpbin.org/post","secret":"abc","format":"generic","event_filter":["api_key_created"],"scope":"global"}'` возвращает 200 с secret в body один раз.
- Commit subject уникальный, `Co-Authored-By: Codex <noreply@anthropic.com>`.
- Этот CX-файл (`2026-04-22-cx-integrations-webhooks.md`) стадж в свой коммит.
- `git status --short` = пусто.

## How
1. Baseline: `git status --short` = пусто, `scripts\verify_all.cmd` = 0.
2. Добавить schema migration step. Bump `schema_version`. Tests `test_repository.py` расширить.
3. Написать `webhook_service.py` + unit-тесты с mocked httpx.
4. Routes + schemas + integration тесты.
5. Hook в `_record_audit_event` — fire-and-forget.
6. Frontend компонент + i18n + a11y тесты.
7. Regen.
8. Docs (README, RUNBOOK).
9. Commit + verify + report.

## Notes
- **CX-файл hygiene:** staging этого файла в коммит.
- **Commit subject hygiene:** `git log --oneline -15 | awk '{$1=""; print $0}' | sort | uniq -d` пусто.
- **БЕЗОПАСНОСТЬ:** HMAC secret — plaintext в БД (admin-only access); если юзер прижмёт на секретности — в отчёте отметить как deferred improvement (encrypt at rest).
- **БЕЗОПАСНОСТЬ:** `target_url` принимать только HTTPS (валидация при create); localhost/127.0.0.1 разрешить только если `AB_ENV=local`.
- **Thread safety:** если используется `asyncio.create_task`, убедиться что FastAPI lifespan держит loop; иначе — `httpx.Client` + `ThreadPoolExecutor(max_workers=4)`.
- **НЕ** использовать Celery / Redis / RQ — это внутренний FastAPI, встроенного background enough.
- **НЕ** добавлять новые deps кроме встроенных (httpx уже в requirements).
- **НЕ** ломать существующий audit flow — webhooks это побочный эффект, если httpx падает — audit_event всё равно записан.
- **Slack format** — поддержать только "incoming webhook" payload `{"text":"..."}` (с опциональными `blocks`); не реализовывать Slack Events API, OAuth, или bot-tokens.
- **НЕ** пушить на remote.

## Out of scope
- Discord / Teams / Telegram форматы (можно добавить позже)
- Subscriber verification endpoint (challenge-response)
- Webhook event replay UI
- Per-event priority / queue draining
- Email notifications
