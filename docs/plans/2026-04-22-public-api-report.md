# Public API Report

## New endpoints

- `GET /api/v1/keys`
- `POST /api/v1/keys`
- `POST /api/v1/keys/{api_key_id}/revoke`
- `DELETE /api/v1/keys/{api_key_id}`

Existing endpoints extended for key-aware public API behavior:

- `GET /api/v1/audit?key_id=...&action=...`
- `GET /api/v1/audit/export?key_id=...&action=...`
- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

## Curl flow

Create a key:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/keys \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Partner read key","scope":"read","rate_limit_requests":60,"rate_limit_window_seconds":60}'
```

Use the returned plaintext key on a protected endpoint:

```bash
curl http://127.0.0.1:8008/api/v1/projects \
  -H "X-API-Key: abk_your_plaintext_key"
```

Inspect usage events for that key:

```bash
curl "http://127.0.0.1:8008/api/v1/audit?key_id=KEY_ID&action=api_key_used" \
  -H "Authorization: Bearer YOUR_WRITE_TOKEN"
```

Revoke the key:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/keys/KEY_ID/revoke \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

## Docs screenshots

- Swagger UI: `archive/public-api-docs-20260421/swagger-docs.png`
- Redoc: `archive/public-api-docs-20260421/redoc-docs.png`

## Verification

- `python scripts/generate_frontend_api_types.py --check` -> `0`
- `python scripts/generate_api_docs.py --check` -> `0`
- `python -m pytest app/backend/tests/test_api_keys.py app/backend/tests/test_repository.py app/backend/tests/test_api_routes.py -q` -> `73 passed`
- `npm --prefix app/frontend run test:unit -- ApiKeyManager.test.tsx a11y-api-keys.test.tsx` -> `4 passed`
- OpenAPI info confirmed from app metadata:
  - title: `AB Test Research Designer API`
  - version: `1.0.0`
- `curl -I http://127.0.0.1:8010/docs` -> `200 OK`
- `curl -I http://127.0.0.1:8010/redoc` -> `200 OK`

## Bundle budget

- `npm --prefix app/frontend run build` emitted a separate lazy chunk for API keys:
  - `dist/assets/ApiKeyManager-CktwvpCw.js` -> `6.46 kB`, gzip `2.08 kB`
- Main bundle is still above the requested budget:
  - `dist/assets/index-DBhDI9YG.js` -> gzip `142.76 kB`
- Result:
  - lazy-loading requirement for `ApiKeyManager` is satisfied
  - `< 140 kB` main-bundle budget is currently not met

## Remaining blockers

- `cmd /c scripts\verify_all.cmd --with-e2e` still fails in frontend typecheck outside this task's file set:
  - `app/frontend/src/components/PosteriorPlot.test.tsx`
  - `app/frontend/src/components/SequentialBoundaryChart.test.tsx`
  - `app/frontend/src/i18n/index.ts`
  - `app/frontend/src/stores/projectStore.ts`
- These errors were present in the broader dirty worktree and block the acceptance target `verify_all.cmd --with-e2e = 0`.
