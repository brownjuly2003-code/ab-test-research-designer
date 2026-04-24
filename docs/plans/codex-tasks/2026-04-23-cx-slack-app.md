# CX Task: Slack App packaging — manifest + incoming OAuth bot

## Goal
Обернуть существующую Slack webhook интеграцию (landed в `6d2c7d3f`) в distributable Slack App с manifest.yml + OAuth install flow. Сейчас webhook — unidirectional (AB_TEST → Slack channel); после этого таска можно будет ставить App в workspace с permissions, `/ab-test` slash command и approval actions.

## Context
- **Repo.** `D:\AB_TEST\`, `main`, HEAD `906ec9ce` (или новее).
- **Existing webhook.** `app/backend/app/routes/webhooks.py` + `app/backend/app/services/webhook_service.py`. HMAC `X-AB-Signature`, admin-guarded CRUD, delivery retry + dead-letter history. Frontend `WebhookManager.tsx` в Sidebar.
- **Что добавляем:**
  - `slack/app-manifest.yml` — Slack App manifest для `slack deploy` / manual import.
  - OAuth install endpoint (`/slack/install` + `/slack/oauth/callback`).
  - Slash command `/ab-test` — `status <project_id>`, `run <project_id>` (trigger analysis), `projects` (list).
  - Interactive message components — approve / request-review buttons на analysis result Slack messages.
- **Existing AB_SLACK_WEBHOOK_URL** env var — остаётся для simple one-way, new App — для two-way.

## Deliverables

1. **Slack App manifest.**
   - `slack/app-manifest.yml`:
     ```yaml
     display_information:
       name: AB Test Research Designer
       description: Design and review A/B tests from Slack
       background_color: "#0f172a"
     features:
       bot_user:
         display_name: AB Test Bot
         always_online: true
       slash_commands:
         - command: /ab-test
           url: https://{DEPLOY_HOST}/slack/commands
           description: Interact with AB Test Research Designer
           usage_hint: status|run|projects <project_id>
     oauth_config:
       redirect_urls:
         - https://{DEPLOY_HOST}/slack/oauth/callback
       scopes:
         bot:
           - commands
           - chat:write
           - chat:write.public
           - users:read
     settings:
       interactivity:
         is_enabled: true
         request_url: https://{DEPLOY_HOST}/slack/interactive
       event_subscriptions:
         request_url: https://{DEPLOY_HOST}/slack/events
         bot_events: []  # пока нет subscription'ов
     ```
   - `slack/README.md` — how to install (via `slack deploy` или Slack UI "Create from manifest"), set env vars.

2. **Backend endpoints.**
   - `app/backend/app/routes/slack.py`:
     - `GET /slack/install` — redirect на `https://slack.com/oauth/v2/authorize?client_id=...&scope=...` с state param для CSRF.
     - `GET /slack/oauth/callback?code=...` — exchange code на tokens, store в DB (table `slack_installations` — team_id, bot_token, user_token nullable, installed_at).
     - `POST /slack/commands` — slash command webhook. Verify signature via `X-Slack-Signature` + `X-Slack-Request-Timestamp` (5 min freshness).
     - `POST /slack/interactive` — interactive message (buttons/modals). Same signature verify.
     - `POST /slack/events` — Event Subscriptions (пока empty handler but infra ready).
   - Signature verification util: `app/backend/app/slack/signature.py` — HMAC SHA256 per Slack docs.
   - Installation repository: `app/backend/app/services/slack_service.py` — CRUD на slack_installations + команды (`send_message`, `respond_to_command`).

3. **Slash commands.**
   - `/ab-test projects` — список projects current workspace'а (filter по installation.team_id), reply ephemeral.
   - `/ab-test status <project_id>` — краткий status + последний analysis result, blocks-format сообщение.
   - `/ab-test run <project_id>` — триггер analysis (async через background task), posts result когда готов (`response_url` callback).

4. **Interactive actions.**
   - "Approve analysis" button (admin only) → marks analysis as approved in DB.
   - "Request review" button → posts в settings-configured review channel.

5. **Env + secrets.**
   - New env vars: `AB_SLACK_CLIENT_ID`, `AB_SLACK_CLIENT_SECRET`, `AB_SLACK_SIGNING_SECRET`.
   - Docs в `docs/DEPLOY.md` — где взять creds, как их rotate.
   - `.env.example` — add stubs.

6. **Tests.**
   - `app/backend/tests/test_slack_signature.py` — signature verify happy / replay / timestamp-too-old / wrong-secret cases.
   - `app/backend/tests/test_slack_routes.py` — install flow, slash commands, signature reject, interactive callback.
   - `app/backend/tests/test_slack_service.py` — send_message idempotent, installations CRUD.
   - Mock all Slack API calls через `httpx_mock` или `respx`.

7. **Frontend.**
   - `SidebarPanel` → Integrations section → add "Slack App" tile показывающий install button / installed-status.
   - Install button → redirect на `/slack/install`.
   - После OAuth callback — visual confirmation в UI (read from settings `slackInstalled: true`).

8. **Docs.**
   - `docs-site/features/slack.md` — user-facing guide.
   - `docs/RUNBOOK.md#slack-app-deployment` — ops notes (deploy_host config, manifest updates, rotating secrets).
   - `README.md` — mention Slack в Integrations list.

9. **Коммит** (1 большой или 2-3 atomic):
   - `feat(slack): app manifest + oauth install + slash commands + interactive buttons`
   - Либо разбить на `feat(slack): oauth install flow` + `feat(slack): slash commands` + `feat(slack): interactive actions`.

10. **Report `docs/plans/2026-04-23-slack-app-report.md`:**
    - Manifest screenshot (if taken through Slack UI).
    - Tests count (should add ~15-25 new).
    - Smoke: install App в test workspace, run `/ab-test projects`, confirm blocks render correctly.

## Acceptance
- Slack manifest valid (import через Slack UI без ошибок — если недоступно в CX env, validate через `slack manifest validate` CLI или JSON schema).
- OAuth install flow end-to-end (state verify, token exchange, DB storage) — через mock Slack в тестах.
- Signature verification rejects tampered / stale requests.
- `/ab-test projects` returns correct workspace-scoped list.
- `python -m pytest -p no:schemathesis app/backend/tests/test_slack_*` → зелёный (добавленные тесты).
- `scripts\verify_all.cmd --with-e2e` = 0.
- Existing webhooks не сломаны.

## Notes
- **НЕ** required'ить Slack creds для dev / CI — если env vars отсутствуют, Slack routes возвращают 503 `{"error": "slack_not_configured"}` вместо крэша.
- **НЕ** rebuild webhooks — Slack App и webhooks сосуществуют.
- **Signing secret rotation.** Docs должны явно указать что secret надо регулярно rotate и как (delete installation row → re-install).
- **Rate limits.** Slack Tier 3 (50+/min) для chat.postMessage. Не throttle'ить явно, но в webhook delivery уже есть retry backoff — переиспользовать.
- **Blocks JSON.** Хранить как Python dict / helper builders в `slack/blocks.py`, не raw JSON strings.

## Out of scope
- Slack Enterprise Grid multi-workspace support (single workspace per install пока).
- Slack Connect / shared channels.
- Events API (пока empty handler, подписок нет).
- Webhooks → Slack App migration tooling (docs hint achterest).
- Desktop Slack app push notification details (inherits standard).
