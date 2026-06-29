# API

This file is generated from FastAPI OpenAPI metadata via `python scripts/generate_api_docs.py`.

Base URL:

```text
http://127.0.0.1:8008
```

## Health

### `GET /health`

Health

```bash
curl http://127.0.0.1:8008/health
```

## Readiness

### `GET /readyz`

Readyz

```bash
curl http://127.0.0.1:8008/readyz
```

## Diagnostics

### `GET /api/v1/diagnostics`

Diagnostics

```bash
curl http://127.0.0.1:8008/api/v1/diagnostics
```

## Audit

### `GET /api/v1/audit`

Get Audit Log

```bash
curl "http://127.0.0.1:8008/api/v1/audit?action=api_key_used" ^
  -H "X-API-Key: YOUR_READ_OR_WRITE_KEY"
```

### `GET /api/v1/audit/export`

Export Audit Log

```bash
curl "http://127.0.0.1:8008/api/v1/audit/export?action=api_key_created" ^
  -H "X-API-Key: YOUR_WRITE_KEY"
```

## Deterministic analysis

### `POST /api/v1/analyze`

Analyze

```bash
curl -X POST http://127.0.0.1:8008/api/v1/analyze ^
  -H "Content-Type: application/json" ^
  -d @docs/demo/sample-project.json
```

### `POST /api/v1/calculate`

Calculate

```bash
curl -X POST http://127.0.0.1:8008/api/v1/calculate ^
  -H "Content-Type: application/json" ^
  -d "{\"metric_type\":\"binary\",\"baseline_value\":0.042,\"mde_pct\":5,\"alpha\":0.05,\"power\":0.8,\"expected_daily_traffic\":12000,\"audience_share_in_test\":0.6,\"traffic_split\":[50,50],\"variants_count\":2}"
```

### `POST /api/v1/design`

Design

### `POST /api/v1/llm/advice`

Llm Advice

## Keys

### `GET /api/v1/keys`

List Api Keys

```bash
curl http://127.0.0.1:8008/api/v1/keys ^
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

### `POST /api/v1/keys`

Create Api Key

```bash
curl -X POST http://127.0.0.1:8008/api/v1/keys ^
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Partner read key\",\"scope\":\"read\",\"rate_limit_requests\":60,\"rate_limit_window_seconds\":60}"
```

### `DELETE /api/v1/keys/{api_key_id}`

Delete Api Key

```bash
curl -X DELETE http://127.0.0.1:8008/api/v1/keys/KEY_ID ^
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

### `POST /api/v1/keys/{api_key_id}/revoke`

Revoke Api Key

```bash
curl -X POST http://127.0.0.1:8008/api/v1/keys/KEY_ID/revoke ^
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

## Project storage

### `GET /api/v1/projects`

List Projects

```bash
curl http://127.0.0.1:8008/api/v1/projects
```

### `POST /api/v1/projects`

Create Project

```bash
curl http://127.0.0.1:8008/api/v1/projects
```

### `DELETE /api/v1/projects/{project_id}`

Delete Project

### `GET /api/v1/projects/{project_id}`

Get Project

### `PUT /api/v1/projects/{project_id}`

Update Project

## Project activity

### `POST /api/v1/projects/{project_id}/analysis`

Record Project Analysis

### `POST /api/v1/projects/{project_id}/exports`

Record Project Export

### `GET /api/v1/projects/{project_id}/history`

Get Project History

```bash
curl "http://127.0.0.1:8008/api/v1/projects/PROJECT_ID/history?analysis_limit=5&export_limit=5"
```

### `POST /api/v1/projects/{project_id}/restore`

Restore Project

```bash
curl -X POST http://127.0.0.1:8008/api/v1/projects/PROJECT_ID/restore
```

### `GET /api/v1/projects/{project_id}/revisions`

Get Project Revisions

```bash
curl "http://127.0.0.1:8008/api/v1/projects/PROJECT_ID/revisions?limit=5"
```

## Comparison

### `GET /api/v1/projects/compare`

Compare Projects

```bash
curl "http://127.0.0.1:8008/api/v1/projects/compare?base_id=BASE&candidate_id=CANDIDATE"
```

### `POST /api/v1/projects/compare`

Compare Multiple Projects

```bash
curl "http://127.0.0.1:8008/api/v1/projects/compare?base_id=BASE&candidate_id=CANDIDATE"
```

## Workspace

### `GET /api/v1/workspace/export`

Export Workspace

```bash
curl http://127.0.0.1:8008/api/v1/workspace/export
```

### `POST /api/v1/workspace/import`

Import Workspace

```bash
curl -X POST http://127.0.0.1:8008/api/v1/workspace/import ^
  -H "Content-Type: application/json" ^
  -d @workspace-backup.json
```

### `POST /api/v1/workspace/validate`

Validate Workspace

```bash
curl -X POST http://127.0.0.1:8008/api/v1/workspace/validate ^
  -H "Content-Type: application/json" ^
  -d @workspace-backup.json
```

## Report export

### `POST /api/v1/export/html`

Export Html

### `POST /api/v1/export/markdown`

Export Markdown

```bash
curl -X POST http://127.0.0.1:8008/api/v1/export/markdown ^
  -H "Content-Type: application/json" ^
  -d @report.json
```

## Other

### `POST /api/v1/assignment/preview`

Assignment Preview

### `POST /api/v1/experiments/{experiment_id}/assign`

Assign Experiment

### `POST /api/v1/experiments/{experiment_id}/conversions`

Ingest Conversions

### `GET /api/v1/experiments/{experiment_id}/decision`

Get Decision

Decision Readout — one synthesized ship / no-ship / keep-running verdict over the same
live-stats signals (SRM, frequentist effect/CI, Bayesian P(B>A), sequential crossing). No
new statistics; see services/decision_service.py.

### `POST /api/v1/experiments/{experiment_id}/exclusions`

Ingest Exclusions

Ingest manual deny-list exclusions for the bot / fraud filter (P4.4). First-write-wins per
user (the first reason sticks); the live-stats rollup drops excluded users — resolved to their
canonical id — from every aggregate, alongside the automatic rate-spike heuristic. The raw
events are never deleted, so an exclusion is a reversible read-time filter.

### `POST /api/v1/experiments/{experiment_id}/exposures`

Ingest Exposures

### `POST /api/v1/experiments/{experiment_id}/holdout`

Ingest Holdout

Ingest holdout members — users held back from the rollout (F5). Recorded as
``variation_index = -1`` exposures (first-write-wins per user); the live-stats read compares
the pooled treated arms against this held-back group to measure the rollout's cumulative
effect. Holdout outcomes ride the ordinary conversion stream under the primary metric name.

### `POST /api/v1/experiments/{experiment_id}/identities`

Ingest Identities

Ingest anonymous → canonical identity links (P4.3). First-write-wins per anonymous id;
the live-stats rollup folds each user's exposures and conversions onto their canonical id, so
a person exposed while anonymous and re-exposed / converting after login is counted once
instead of inflating SRM and the conversion rate. A self-link is a no-op and is skipped.

### `GET /api/v1/experiments/{experiment_id}/ingestion`

Get Ingestion Summary

### `GET /api/v1/experiments/{experiment_id}/live-stats`

Get Live Stats

Phase D — live SRM / frequentist / Bayesian / sequential read over the current
deduplicated exposures and conversions. Recomputed on demand (the dashboard polls);
there is no separate scheduler process in the local-first MVP.

### `POST /api/v1/experiments/{experiment_id}/pre-period`

Ingest Pre Period Values

Ingest per-user pre-experiment covariate values for CUPED (E5). First-write-wins
per user; the covariate enables variance reduction on the continuous live-stats.

### `POST /api/v1/experiments/{experiment_id}/strata`

Ingest Strata

Ingest one categorical stratum per user for post-stratification (F3b). First-write-wins
per user; the stratum lets the live-stats read estimate the effect within each stratum and
recombine it, reducing variance when the stratum explains outcome variation.

### `POST /api/v1/export/comparison`

Export Comparison

### `POST /api/v1/export/html-standalone`

Export Html Standalone

### `POST /api/v1/hypotheses/generate`

Generate Hypotheses

### `POST /api/v1/multiple-testing`

Multiple Testing

### `POST /api/v1/projects/{project_id}/archive`

Archive Project

### `GET /api/v1/projects/{project_id}/report/csv`

Get Project Report Csv

### `GET /api/v1/projects/{project_id}/report/pdf`

Get Project Report Pdf

### `GET /api/v1/projects/{project_id}/report/xlsx`

Get Project Report Xlsx

### `POST /api/v1/results`

Results

### `POST /api/v1/results/categorical`

Categorical Results

### `POST /api/v1/sensitivity`

Sensitivity

### `POST /api/v1/simulate/bandit`

Simulate Bandit

### `GET /api/v1/slack/status`

Slack Status

### `POST /api/v1/srm-check`

Srm Check

### `GET /api/v1/templates`

List Templates

### `POST /api/v1/templates`

Create Template

### `DELETE /api/v1/templates/{template_id}`

Delete Template

### `GET /api/v1/templates/{template_id}`

Get Template

### `POST /api/v1/templates/{template_id}/use`

Use Template

### `GET /api/v1/webhooks`

List Webhooks

### `POST /api/v1/webhooks`

Create Webhook

### `DELETE /api/v1/webhooks/{subscription_id}`

Delete Webhook

### `GET /api/v1/webhooks/{subscription_id}`

Get Webhook

### `PATCH /api/v1/webhooks/{subscription_id}`

Update Webhook

### `GET /api/v1/webhooks/{subscription_id}/deliveries`

List Webhook Deliveries

### `POST /api/v1/webhooks/{subscription_id}/test`

Test Webhook

### `POST /slack/commands`

Slack Commands

### `POST /slack/events`

Slack Events

### `GET /slack/install`

Slack Install

### `POST /slack/interactive`

Slack Interactive

### `GET /slack/oauth/callback`

Slack Oauth Callback

## Validation notes

- supported variant count is `2..10`
- binary baselines must be between `0` and `1`
- continuous metrics require positive `baseline_value` and `std_dev`
- `traffic_split` length must match `variants_count`
- malformed request bodies return `422`
- domain errors return structured `400`
- when `AB_API_TOKEN`, `AB_READONLY_API_TOKEN`, or database-backed API keys are configured, protected runtime routes still accept `Authorization: Bearer` or `X-API-Key`
- `/docs`, `/redoc`, and `/openapi.json` remain public even when auth is enabled; only protected API routes and `/readyz` require a token
- `AB_READONLY_API_TOKEN` is valid only for `GET`, `HEAD`, and `OPTIONS`; mutating routes still require `AB_API_TOKEN`
- `/api/v1/keys*` requires `AB_ADMIN_TOKEN`; without it the key-management endpoints return `401`
- database-backed API keys are stored as SHA-256 hashes, the plaintext secret is returned only once at creation time, and revoked keys are rejected
- per-key rate-limit overrides apply only to requests authenticated with a database API key; legacy shared tokens continue to use the global limiter
- all API responses include `X-Request-ID` and `X-Process-Time-Ms` headers
- error responses also include `error_code`, `status_code`, `request_id`, and `X-Error-Code`
- diagnostics expose in-memory runtime counters plus the active guardrail configuration for security headers, rate limiting, auth throttling, and request-body limits
- `GET /readyz` returns `503` when required runtime dependencies are degraded

## Contract generation

- TypeScript contracts: `python scripts/generate_frontend_api_types.py`
- API docs markdown: `python scripts/generate_api_docs.py`
