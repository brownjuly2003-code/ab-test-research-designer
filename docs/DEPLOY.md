# Deploy

## Build

Build the release image from the repository root:

```bash
docker build -t ab-test-research-designer:1.0.0 -t ab-test-research-designer:latest .
docker inspect ab-test-research-designer:1.0.0 --format '{{.Size}}'
```

## Tag For Registry

Set `<REGISTRY>` explicitly for your target registry namespace, for example `ghcr.io/<owner>` or `docker.io/<user>`.

```bash
docker tag ab-test-research-designer:1.0.0 <REGISTRY>/ab-test-research-designer:1.0.0
docker tag ab-test-research-designer:latest <REGISTRY>/ab-test-research-designer:latest
```

## Push

Do not run push until registry credentials, target namespace, and image scan are ready.

```bash
docker push <REGISTRY>/ab-test-research-designer:1.0.0
docker push <REGISTRY>/ab-test-research-designer:latest
```

## Run Locally

Open mode:

```bash
docker run --rm --name ab-test-v1-open -p 8008:8008 ab-test-research-designer:1.0.0
```

Secure mode:

```bash
docker run --rm --name ab-test-v1-secure -e AB_API_TOKEN=replace-with-a-write-token -p 8008:8008 ab-test-research-designer:1.0.0
```

Dual-token mode:

```bash
docker run --rm --name ab-test-v1-dual -e AB_API_TOKEN=replace-with-a-write-token -e AB_READONLY_API_TOKEN=replace-with-a-readonly-token -p 8008:8008 ab-test-research-designer:1.0.0
```

Signed workspace backup mode:

```bash
docker run --rm --name ab-test-v1-signed -e AB_WORKSPACE_SIGNING_KEY=replace-with-a-long-random-secret -p 8008:8008 ab-test-research-designer:1.0.0
```

## Health / Verification

Open runtime:

```bash
curl http://127.0.0.1:8008/health
curl http://127.0.0.1:8008/readyz
curl http://127.0.0.1:8008/api/v1/diagnostics
curl http://127.0.0.1:8008/
```

Expected responses:

- `GET /health` -> `200` with `"status":"ok"` and `"version":"1.0.0"`.
- `GET /readyz` -> `200` with `"status":"ready"` and all readiness checks marked `ok`.
- `GET /api/v1/diagnostics` -> `200` and `storage.write_probe_ok=true`.
- `GET /` -> `200` and HTML title `AB Test Research Designer`.

Secure runtime:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/calculate -H "Content-Type: application/json" -d '{"metric_type":"binary","baseline_value":0.1,"mde_pct":5,"alpha":0.05,"power":0.8,"expected_daily_traffic":1000,"audience_share_in_test":1.0,"traffic_split":[50,50],"variants_count":2}'
curl -X POST http://127.0.0.1:8008/api/v1/calculate -H "Authorization: Bearer <WRITE_TOKEN>" -H "Content-Type: application/json" -d '{"metric_type":"binary","baseline_value":0.1,"mde_pct":5,"alpha":0.05,"power":0.8,"expected_daily_traffic":1000,"audience_share_in_test":1.0,"traffic_split":[50,50],"variants_count":2}'
```

Expected auth behavior:

- Without a write token, `POST /api/v1/calculate` returns `401`.
- With `Authorization: Bearer <WRITE_TOKEN>`, `POST /api/v1/calculate` returns `200`.
- In dual-token mode, use `<READONLY_TOKEN>` for read-only diagnostics and `<WRITE_TOKEN>` for mutating endpoints.

## Rollback

Stop the current container, pull or retag the previous release, and run the previous tag again.

```bash
docker stop ab-test-v1-open
docker run --rm --name ab-test-v1-rollback -p 8008:8008 <REGISTRY>/ab-test-research-designer:<PREVIOUS_TAG>
```

If the previous image already exists locally, retag it first:

```bash
docker tag <REGISTRY>/ab-test-research-designer:<PREVIOUS_TAG> ab-test-research-designer:rollback
docker run --rm --name ab-test-v1-rollback -p 8008:8008 ab-test-research-designer:rollback
```
