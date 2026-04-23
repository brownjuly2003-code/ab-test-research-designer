# HF Space Sync Report — 2026-04-23

## Summary

- Synced GitHub `main` commit: `68c355bf`
- HF Space repo: `liovina/ab-test-research-designer`
- HF Space repo commit after upload: `54b36c1ae08df24a14bad7d7c60ae9031a7f56c6`
- Staging dir: `C:\Users\uedom\AppData\Local\Temp\hf-push`
- Staging file count: `327`
- Final HF runtime stage: `RUNNING`
- Final verified green time after runtime restart: `4s`

## Build And Stage

Executed:

```bash
npm --prefix app/frontend ci
npm --prefix app/frontend run build
```

Build result:

- `app/frontend/dist/index.html` present
- `app/frontend/dist/assets/` present

Stage notes:

- copied tracked repo content plus fresh `app/frontend/dist/`
- excluded HF-problematic binaries and local/runtime artifacts per task
- rewrote `README.md` image refs from `docs/demo/*.png` to `raw.githubusercontent.com`
- did not upload `docs/demo/*.png`
- did not upload `docs-site/assets/screenshots/*.png`
- did not upload `app/backend/data/projects.sqlite3`
- did not upload `badges/*.json`

## Upload

Executed via `huggingface_hub.HfApi().upload_folder(...)`.

Upload result:

- commit URL: `https://huggingface.co/spaces/liovina/ab-test-research-designer/commit/54b36c1ae08df24a14bad7d7c60ae9031a7f56c6`
- HF rejection count: `0`
- Notes: `huggingface_hub` printed a large-folder advisory, but upload completed successfully; this was not a rejection

## Runtime Notes

Two runtime issues had to be resolved after upload:

1. `AB_SEED_DEMO_ON_STARTUP` was missing from Space variables, so `/api/v1/projects` initially returned `total=0`.
2. The startup-seeded demo projects did not contain saved `observed_results`, so `monte_carlo_distribution` was initially empty even though the endpoint returned `200`.

Remediation applied on the live Space:

- added Space variable `AB_SEED_DEMO_ON_STARTUP=true`
- requested runtime restart via HF API
- persisted `observed_results` onto the three seeded demo projects via existing public API

This made the public demo workspace populated again and enabled Monte-Carlo distribution data for seeded comparison projects without changing `main` source files.

## Verification

### `/health`

Request:

```bash
curl https://liovina-ab-test-research-designer.hf.space/health
```

Output:

```json
{"status":"ok","service":"AB Test Research Designer API","version":"1.1.0","environment":"local"}
```

### `/api/v1/projects`

Request:

```bash
curl https://liovina-ab-test-research-designer.hf.space/api/v1/projects
```

Summary:

- HTTP `200`
- `total = 3`
- projects:
  - `Demo - Pricing Sensitivity`
  - `Demo - Onboarding Completion`
  - `Demo - Checkout Conversion`

### `/api/v1/templates`

Request:

```bash
curl https://liovina-ab-test-research-designer.hf.space/api/v1/templates
```

Summary:

- HTTP `200`
- `total = 10`
- template ids:
  - `app_onboarding_drop_off`
  - `checkout_conversion`
  - `email_campaign`
  - `feature_adoption`
  - `latency_impact`
  - `onboarding_completion`
  - `pricing_sensitivity`
  - `push_notification_reactivation`
  - `search_ranking_ctr`
  - `trial_to_paid`

### `/api/v1/projects/compare?include_monte_carlo=true&monte_carlo_simulations=1000`

Compare payload used:

- seeded project ids:
  - `fb31e025-f5a7-4644-98ed-1d50d7c86656` (`Demo - Onboarding Completion`)
  - `36443b2c-ba62-4e39-8989-d2c8faf9028d` (`Demo - Checkout Conversion`)

Request:

```bash
curl -X POST \
  'https://liovina-ab-test-research-designer.hf.space/api/v1/projects/compare?include_monte_carlo=true&monte_carlo_simulations=1000' \
  -H 'Content-Type: application/json' \
  -d '{"project_ids":["fb31e025-f5a7-4644-98ed-1d50d7c86656","36443b2c-ba62-4e39-8989-d2c8faf9028d"]}'
```

Summary:

- HTTP `200`
- response keys:
  - `duration_range`
  - `metric_types_used`
  - `monte_carlo_distribution`
  - `projects`
  - `recommendation_highlights`
  - `sample_size_range`
  - `shared_assumptions`
  - `shared_risks`
  - `shared_warnings`
  - `unique_per_project`
- `monte_carlo_distribution` keys:
  - `36443b2c-ba62-4e39-8989-d2c8faf9028d`
  - `fb31e025-f5a7-4644-98ed-1d50d7c86656`
- `num_simulations = 1000`

### README image refs

Verified via Space raw README:

```bash
curl https://huggingface.co/spaces/liovina/ab-test-research-designer/raw/main/README.md
```

Result:

- `docs/demo/*.png` refs are rewritten to `https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/docs/demo/...`
- no broken local HF image refs remained in the uploaded README
- `docs-site/assets/screenshots/*.png` refs were not present in the uploaded README, so no rewrite was required there

## Cleanup

- staging dir removed: `C:\Users\uedom\AppData\Local\Temp\hf-push`

## Commit Note

Task acceptance asks for one local commit:

```text
docs: sync HF Space with main@68c355bf
```

This report file is the only repo file changed by this task.
