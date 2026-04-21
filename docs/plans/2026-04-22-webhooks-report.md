# 2026-04-22 Webhooks Report

## DB schema

- `webhook_subscriptions`
  - `id`, `name`, `target_url`, `secret`, `format`, `event_filter`, `scope`, `api_key_id`
  - `created_at`, `updated_at`, `last_delivered_at`, `last_error_at`, `enabled`
- `webhook_deliveries`
  - `id`, `subscription_id`, `event_id`, `status`, `attempt_count`
  - `last_attempt_at`, `delivered_at`, `response_code`, `response_body`, `error_message`

## Endpoints

- `POST /api/v1/webhooks`
- `GET /api/v1/webhooks`
- `GET /api/v1/webhooks/{id}`
- `PATCH /api/v1/webhooks/{id}`
- `DELETE /api/v1/webhooks/{id}`
- `POST /api/v1/webhooks/{id}/test`
- `GET /api/v1/webhooks/{id}/deliveries`

## Example curl

Create a Slack webhook subscription:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/webhooks \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Slack alerts","target_url":"https://hooks.slack.com/services/XXX/YYY/ZZZ","secret":"rotate-me","format":"slack","event_filter":["api_key_created","api_key_revoked","analysis_run_created","workspace_imported","project.archive"],"scope":"global"}'
```

Fire a test event:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/webhooks/WEBHOOK_ID/test \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

## Known limitations

- no event deduplication
- no per-event ordering guarantees across subscriptions; delivery uses a small in-process worker pool
- webhook secrets are stored in plaintext in SQLite; encrypt-at-rest can be added later if required
