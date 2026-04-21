# Docker Publish Readiness Report

Execution date: 2026-04-21

## Image Build

- Command:

```bash
docker build -t ab-test-research-designer:1.0.0 -t ab-test-research-designer:latest .
```

- `docker inspect ab-test-research-designer:1.0.0 --format '{{.Size}}'` -> `115164414` bytes (`109.83 MiB`)
- `docker images ab-test-research-designer` -> tags present: `1.0.0`, `latest`, `local`
- `docker images --format "{{.Repository}}\t{{.Tag}}\t{{.Size}}" ab-test-research-designer` -> all three tags show `695MB`
- Soft size target from the task is satisfied by `.Size < 500 MB`; note that Docker CLI display size is larger than `.Size`

## Smoke Output

### Open Mode

Command:

```bash
docker run --rm -d --name ab-test-v1 -p 18008:8008 ab-test-research-designer:1.0.0
```

Output:

```json
{
  "container_name": "ab-test-v1-open-1776754471",
  "container_id": "4760b61ba43401d45622ebee77399e8f45e60fb7cb212a32a316bc1a7b7486e7",
  "health_status_code": 200,
  "health": {
    "status": "ok",
    "service": "AB Test Research Designer API",
    "version": "1.0.0",
    "environment": "local"
  },
  "readyz_status_code": 200,
  "readyz": {
    "status": "ready",
    "generated_at": "2026-04-21T06:54:36.287802+00:00",
    "checks": [
      {
        "name": "sqlite_storage",
        "ok": true,
        "detail": "Database path /app/data/projects.sqlite3"
      },
      {
        "name": "sqlite_schema_version",
        "ok": true,
        "detail": "user_version=5 expected=5"
      },
      {
        "name": "sqlite_journal_mode",
        "ok": true,
        "detail": "journal_mode=WAL expected=WAL"
      },
      {
        "name": "sqlite_write_probe",
        "ok": true,
        "detail": "BEGIN IMMEDIATE succeeded"
      },
      {
        "name": "frontend_dist",
        "ok": true,
        "detail": "Looking for /app/app/frontend/dist/index.html"
      },
      {
        "name": "llm_config",
        "ok": true,
        "detail": "3 attempt(s), timeout 60.0s"
      },
      {
        "name": "logging_config",
        "ok": true,
        "detail": "INFO / plain"
      }
    ]
  },
  "diagnostics_status_code": 200,
  "diagnostics_write_probe_ok": true,
  "diagnostics_auth_mode": "open",
  "root_status_code": 200,
  "root_title": "AB Test Research Designer",
  "logs_error_lines": [],
  "logs_line_count": 13
}
```

Note: the current backend contract returns `{"status":"ready"}` from `/readyz`. The task text expected `"ok"`, but repository code and tests use `"ready"`.

### Secure Mode

Command:

```bash
docker run --rm -d --name ab-test-v1-secure -e AB_API_TOKEN=test-write-token -p 18009:8008 ab-test-research-designer:1.0.0
```

Output:

```json
{
  "container_name": "ab-test-v1-secure-1776754471",
  "container_id": "b3dcc1c0ff224b4b004786a2bf7549eaa252bf6c79fe3e2df6da2b7deca67bec",
  "health_status_code": 200,
  "health": {
    "status": "ok",
    "service": "AB Test Research Designer API",
    "version": "1.0.0",
    "environment": "local"
  },
  "unauthorized_calculate_status_code": 401,
  "unauthorized_calculate_body": {
    "detail": "Unauthorized",
    "error_code": "unauthorized",
    "status_code": 401,
    "request_id": "930c4aaf-4153-4e22-8e69-2662668f54fa"
  },
  "authorized_calculate_status_code": 200,
  "authorized_calculate_results_excerpt": {
    "sample_size_per_variant": 57763,
    "total_sample_size": 115526,
    "estimated_duration_days": 116
  },
  "diagnostics_status_code": 200,
  "diagnostics_auth_mode": "token",
  "logs_error_lines": [],
  "logs_line_count": 13
}
```

### Optional Dual-Token And Signed Verification

Command:

```bash
python scripts/verify_docker_compose.py
```

Output:

```text
[docker-verify] docker compose secure flow passed
```

This script exits `0` only after all of the following succeed:

- readonly `/readyz` with the readonly token
- readonly `/api/v1/diagnostics` with `auth.mode=dual_token`
- readonly `POST /api/v1/calculate` rejected with `403 forbidden`
- write-token workspace create/export/validate/import flow
- signed workspace integrity with HMAC enabled

## Runtime Warnings

- `docker logs` for the final `open` smoke contained no `ERROR` and no `Exception`
- `docker logs` for the final `secure` smoke contained no `ERROR` and no `Exception`

## Publish Checklist

- Set the final registry namespace for `<REGISTRY>` before tagging or pushing
- Ensure registry credentials are available and run `docker login` separately; no login was performed in this task
- Run an image scan before push, for example Trivy, Snyk, or a registry-native scan
- After push, pull the registry tag or digest and repeat `/health`, `/readyz`, and `/api/v1/diagnostics`
- Confirm rollback target `<PREVIOUS_TAG>` is available before promoting `1.0.0`
