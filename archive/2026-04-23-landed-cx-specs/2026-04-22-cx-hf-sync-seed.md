# CX Task: Sync Hugging Face Space with seed workspace hook

## Goal

Sync the live Hugging Face Space
`https://liovina-ab-test-research-designer.hf.space` with the GitHub `main`
branch so that the public demo boots with the seeded workspace from commit
`2f6f3bac` instead of an empty `{"projects":[],"total":0}` response.

The backend code that seeds the workspace is already on `main` (module
`app/backend/app/startup_seed.py` + wiring in `app/backend/app/main.py` and
relevant tests). The HF Space currently runs an older image without this
module because HF Spaces **do not auto-sync from GitHub** — syncs happen via
`huggingface_hub.HfApi().upload_folder()` against the
`liovina/ab-test-research-designer` Space repo.

## Context

- **Repo.** `D:\AB_TEST\`, `main`, HEAD `cb31cc28` (or newer). Do not rebase or
  touch history.
- **HF Space.** `liovina/ab-test-research-designer`, Docker SDK, Space repo
  visible at `https://huggingface.co/spaces/liovina/ab-test-research-designer`.
  Homepage / live URL:
  `https://liovina-ab-test-research-designer.hf.space`.
- **Local HF token.** Stored at `C:\Users\uedom\.cache\huggingface\token` —
  the same token used for previous HF syncs. No need to prompt the user.
- **Staging dir convention from prior syncs.**
  `C:\Users\uedom\AppData\Local\Temp\hf-push`. Create fresh, clean after use.
- **Binary-file policy.** HF rejects large binaries outside LFS. Prior sync
  removed `docs/demo/*.png` from the HF push and rewrote README image refs to
  `raw.githubusercontent.com` URLs. Follow the same pattern (README in the HF
  staging dir should have image refs pointing at raw GitHub, not at
  `docs/demo/*.png`).
- **What's new in this sync (vs the previous HF push).**
  - `app/backend/app/startup_seed.py` — new module.
  - Changes in `app/backend/app/main.py` wiring the startup hook (see
    `git diff 14259fff..cb31cc28 -- app/backend`).
  - Updated `README.md` (contains the 3 shields.io badges + case-study
    section + regenerated screenshot refs). README needs the same image-path
    rewrite as before.
  - Updated `CHANGELOG.md`, `docs/DEPLOY.md`, `docs/RUNBOOK.md` (optional for
    HF; README is the main public-facing page).
  - `Dockerfile` — unchanged in HEALTHCHECK (still respects `PORT`), safe.
  - Frontend build bits (`app/frontend/dist/**`) should come from a fresh
    `npm run build` on the local machine before staging, so HF gets the
    latest UI with comparison dashboard + webhook manager + 4 locales.

## Deliverables

1. **Stage the HF push.**
   - Create clean `C:\Users\uedom\AppData\Local\Temp\hf-push` directory.
   - Copy the `main` working tree into staging, excluding:
     - `.git/`, `.github/`, `.ci-artifacts/`, `.coverage`, `docs/plans/`,
       `docs/demo/`, `archive/`, `exports/`, `badges/`, `node_modules/`, any
       `*.sqlite3` / `*.db` files, `.env*`.
   - Rewrite README image refs:
     - From `docs/demo/*.png` to
       `https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/docs/demo/<file>.png`.
   - Run `npm --prefix app/frontend run build` at the repo root first, then
     copy the produced `app/frontend/dist/` into staging. HF Docker build uses
     this folder (check `Dockerfile` COPY lines to confirm expected path).
   - Confirm `app/backend/app/startup_seed.py` is present in staging.

2. **Upload via `huggingface_hub`.**
   ```python
   from huggingface_hub import HfApi
   api = HfApi()
   api.upload_folder(
       repo_id="liovina/ab-test-research-designer",
       repo_type="space",
       folder_path=r"C:\Users\uedom\AppData\Local\Temp\hf-push",
       commit_message="sync main@cb31cc28 — seed workspace on startup + case-study README",
   )
   ```
   The token is read automatically from `~/.cache/huggingface/token`.

3. **Verify.**
   - HF Space should rebuild automatically after upload (typically 2-5 min).
   - Poll `https://liovina-ab-test-research-designer.hf.space/health` —
     should return 200 with `version: 1.1.0`.
   - Hit `GET /api/v1/projects` — should return non-zero `total` with seeded
     projects (verify against `startup_seed.py` contents for expected names).
   - Open the root page in a browser (or curl and inspect HTML) — README
     image refs should render via raw.githubusercontent.com.

4. **Cleanup.** Remove the staging dir after successful sync.

5. **Report `docs/plans/2026-04-22-hf-sync-seed-report.md`.**
   - Commit hash synced.
   - HF Space build status after push.
   - `curl` output of `/health` and `/api/v1/projects` (first 200 chars each).
   - Count of seeded projects observed on the live demo.
   - Staging dir file count (sanity check).

## Acceptance

- `curl https://liovina-ab-test-research-designer.hf.space/api/v1/projects`
  returns `total > 0`.
- `/health` still returns 200, `version: 1.1.0`.
- Report file exists and is committed (single commit, title:
  `docs: sync HF Space with seeded workspace from main@cb31cc28`).
- No LFS / binary push rejections in the HF upload log.
- Staging dir removed after success.

## Notes

- **Do not** push the HF sync commit via `git push` — this task only touches
  the HF Space repo, not the GitHub repo (except for the report file).
- **Do not** upload `docs/demo/*.png` — images live on GitHub raw URLs.
- **Do not** upload `badges/*.json` — those are README-only metadata, HF
  README uses raw GitHub links for them already.
- If the HF upload fails with a binary-file rejection, print the rejected
  path and exclude it from the next attempt.
- If `npm run build` is slow or fails, check `node_modules/` is installed
  first (`npm --prefix app/frontend ci` then build).
- The HF Space front-end is served by the backend container (FastAPI mounts
  `app/frontend/dist/` as static files). That is why the build step matters.

## Out of scope

- Any change to `main` branch source code.
- Upgrading HF Space hardware tier.
- Setting up GitHub → HF auto-sync webhook (separate follow-up).
- Adding new features to `startup_seed.py`.
