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

## Validation notes

- supported variant count is `2..10`
- binary baselines must be between `0` and `1`
- continuous metrics require positive `baseline_value` and `std_dev`
- `traffic_split` length must match `variants_count`
- malformed request bodies return `422`
- domain errors return structured `400`
- all API responses include `X-Request-ID` and `X-Process-Time-Ms` headers
- `GET /readyz` returns `503` when required runtime dependencies are degraded

## Contract generation

- TypeScript contracts: `python scripts/generate_frontend_api_types.py`
- API docs markdown: `python scripts/generate_api_docs.py`
