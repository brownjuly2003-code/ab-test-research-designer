# Contributing

## Dev setup

- Python **3.14** (CI/runtime; code keeps a 3.13 compatibility floor for local dev), Node **26**.
- Backend: `python -m pip install -r app/backend/requirements-dev.txt`
- Frontend: `npm --prefix app/frontend ci`
- Docs site (optional): `npm --prefix docs-site ci`

## Verify before you push

The single gate is the same one CI runs:

```bash
python scripts/verify_all.py            # lint, types, both test suites, build, bundle budget, smoke
python scripts/verify_all.py --skip-smoke --skip-build   # faster inner loop
```

Targeted runs while iterating:

- Backend: `python -m pytest app/backend/tests -q` (with `ruff check app/backend/app scripts` and `mypy`)
- Frontend: `npm --prefix app/frontend run test:unit`; typecheck from `app/frontend/` with `npm exec tsc -- --noEmit -p .`

### Bundle budget policy

`scripts/check_bundle_budget.py` caps the frontend bundle at its configured limit. Once
headroom drops below **5%** of the limit (i.e. total size crosses 1 092 500 bytes for the
current 1 150 000 limit), revisit chunking/dependencies first — the limit itself is only
raised by an explicit maintainer decision recorded in the PR, never as a side effect of
landing a feature.

## Updating backend dependencies

`app/backend/requirements.txt` and `requirements-dev.txt` are **compiled locks with sha256
hashes** — do not edit them by hand. Direct dependencies live in `requirements.in` /
`requirements-dev.in`; after changing those, recompile:

```bash
cd app/backend
uv pip compile requirements.in --universal --generate-hashes -o requirements.txt
uv pip compile requirements-dev.in --universal --generate-hashes -o requirements-dev.txt
```

## Generated files — never hand-edit

Some tracked files are build outputs with drift gates in CI:

- `app/frontend/src/lib/generated/api-contract.ts` — `python scripts/generate_frontend_api_types.py`
- `docs/API.md` — `python scripts/generate_api_docs.py`
- `docs-site/src/content/docs/guides/*` and friends — `npm --prefix docs-site run prebuild`
  (sync-docs + gen-routes + gen-experiments + gen-config); rerun after touching `README.md`,
  `CHANGELOG.md` or anything under `docs/`
- `app/frontend/public/help*.html` — `python scripts/build_help_pages.py`

## Pull requests

- Conventional commit style: `feat(scope): …`, `fix(scope): …`, `docs: …`, `chore: …`.
- Add a `CHANGELOG.md` entry under `Unreleased` for user-visible changes.
- New behavior needs a test that fails without the change.
- Do not commit local notes or secrets; `scripts/check_repo_hygiene.py` runs in CI and will fail
  the build if internal files become tracked.

## Security issues

See [SECURITY.md](SECURITY.md) — please use private vulnerability reporting, not public issues.
