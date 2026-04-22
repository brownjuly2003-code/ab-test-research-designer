# Deploy

## Build

Build the release image from the repository root:

```bash
docker build -t ab-test-research-designer:1.0.0 -t ab-test-research-designer:latest .
docker inspect ab-test-research-designer:1.0.0 --format '{{.Size}}'
```

### Pulling from GHCR

```bash
docker pull ghcr.io/brownjuly2003-code/ab-test-research-designer:latest
docker run --rm -p 8008:8008 ghcr.io/brownjuly2003-code/ab-test-research-designer:latest
```

### Automated publish via GitHub Actions

`.github/workflows/docker-publish.yml` publishes the multi-arch image (`linux/amd64`, `linux/arm64`) to `ghcr.io/brownjuly2003-code/ab-test-research-designer` on every pushed tag matching `v*`. The same workflow also supports manual `workflow_dispatch`: provide a specific tag or leave the input empty to republish the latest `v*` tag already present in git.

First GHCR release checklist:

1. Push a release tag such as `v1.1.0`.
2. Wait for the `Publish Docker image` workflow to finish successfully.
3. Open https://github.com/brownjuly2003-code/ab-test-research-designer/pkgs/container/ab-test-research-designer, go to `Settings`, and switch package visibility to **Public**.
4. Verify anonymous pull from a clean machine:

```bash
docker pull ghcr.io/brownjuly2003-code/ab-test-research-designer:v1.1.0
```

Notes:

- GHCR creates the package as private on the first push even when it is linked to the repository, so the visibility switch is a one-time manual step.
- The workflow authenticates with the repository `GITHUB_TOKEN`; no personal access token is required.
- Build cache uses `type=gha`; GitHub may evict it after about 7 days of inactivity, so the first build after an idle period can be slower.

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

## Hugging Face Spaces Deploy (active hosted demo)

The current production demo lives on Hugging Face Spaces on the free CPU tier — no credit card required, Docker SDK, always-on.

**Live URL:** https://liovina-ab-test-research-designer.hf.space

Initial setup (one-time):

1. Generate a write-scoped token at https://huggingface.co/settings/tokens
2. Authenticate: `hf auth login --token <HF_TOKEN> --add-to-git-credential`
3. Create the Space via API:

```python
from huggingface_hub import create_repo
create_repo(
    repo_id="liovina/ab-test-research-designer",
    repo_type="space",
    space_sdk="docker",
    private=False,
)
```

Required README frontmatter (already landed in `README.md`):

```yaml
---
title: AB Test Research Designer
emoji: 🧪
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8008
license: mit
---
```

Note: `app_port` must match the port uvicorn listens on inside the container (`AB_PORT=8008` from `Dockerfile`). HF routes HTTPS traffic to that exact port.

Sync code (preferred — HF rejects binary PNGs >LFS-threshold on direct git push, so use API):

```python
from huggingface_hub import upload_folder
upload_folder(
    folder_path=".",
    repo_id="liovina/ab-test-research-designer",
    repo_type="space",
    ignore_patterns=[".git/**", "**/__pycache__/**", "archive/**", "docs/demo/*.png", "*.sqlite3*", "**/node_modules/**"],
    commit_message="Sync from GitHub main",
)
```

Verify after HF finishes `APP_STARTING`:

```bash
curl https://liovina-ab-test-research-designer.hf.space/health
# {"status":"ok","service":"AB Test Research Designer API","version":"1.1.0","environment":"local"}
```

Known limits of the HF free tier:

- container filesystem is ephemeral — SQLite data resets on every redeploy or container restart
- 2 vCPU + 16 GB RAM, no GPU
- docs/demo screenshots are referenced from `raw.githubusercontent.com` URLs since HF rejects large binaries without Xet storage

## Fly.io Demo Deploy (blocked — credit card required)

Open mode is recommended for a public showcase. This keeps the hosted demo anonymous and matches the default open runtime in the app.

```bash
fly apps create <fly-app-name>
fly volumes create ab_test_data --region ams --size 1
fly deploy
```

Notes:

- `fly.toml` keeps `app = "ab-test-research-designer"` as a placeholder; replace it after `fly apps create` or pass `fly deploy -a <fly-app-name>`.
- The Fly volume is mounted at `/data`, and SQLite is pointed at `/data/projects.sqlite3`.
- Demo seeding is a manual post-deploy step because Fly `release_command` Machines do not mount persistent volumes:

```bash
fly ssh console -C "python scripts/seed_demo_workspace.py --idempotent"
```

## Fly.io Deploy (Secure)

Secure mode is private by default. Once secrets are set, callers must present the configured token; if you share a readonly token, it enables safe `GET` access but it is no longer an anonymous public demo.

```bash
fly secrets set AB_API_TOKEN=... AB_READONLY_API_TOKEN=... AB_WORKSPACE_SIGNING_KEY=...
fly deploy
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

- `GET /health` -> `200` with `"status":"ok"` and `"version":"1.1.0"`.
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
