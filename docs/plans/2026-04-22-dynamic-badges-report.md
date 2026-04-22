# Dynamic quality-gate badges — implementation report

## Summary

Replaced the static placeholder badges in `README.md` with three dynamic
shields.io endpoint badges (`tests`, `coverage`, `lighthouse`). A new CI job
`update-metrics-badges` in `.github/workflows/test.yml` collects metrics from the
existing verify + Lighthouse runs, regenerates `badges/*.json`, and commits the
refreshed payloads back to `main` with `[skip ci]` so the shields.io endpoint
always reflects the latest green build.

## Files

- `.github/workflows/test.yml` — new `update-metrics-badges` job (`needs: [verify, lighthouse]`, `if: github.ref == 'refs/heads/main' && github.event_name == 'push'`); `verify` job parameterised through `verify_args` and uploads `.ci-artifacts/*.{xml,json}` as artifact `verify-metrics` on ubuntu.
- `scripts/collect_badge_metrics.py` — new CLI. Parses JUnit XML (pytest + vitest), pytest-cov JSON, and `.lighthouseci/manifest.json`; emits both a combined `badges/metrics.json` and per-label `badges/{tests,coverage,lighthouse}.json` shields.io endpoint payloads.
- `scripts/verify_all.py` / `scripts/verify_all.cmd` — added `--with-coverage` and `--artifacts-dir` flags; backend run writes `backend-junit.xml` and optional `coverage-backend.json`; frontend run writes `frontend-junit.xml` when `--artifacts-dir` is set.
- `app/backend/requirements.txt` — added `pytest-cov==5.0.0`.
- `badges/{metrics,tests,coverage,lighthouse}.json` — committed placeholder payloads with `message: "n/a"`, `color: "lightgrey"` so the shields.io endpoint does not 404 before the first CI refresh.
- `README.md` — three new shields.io endpoint badges next to the existing static ones.
- `.gitignore` — added `.ci-artifacts/`, `.coverage`, `/--artifacts-dir/`.
- `CHANGELOG.md` — Unreleased entry for the badge pipeline + GHCR workflow + HF seed + screenshots.
- `docs/plans/codex-tasks/2026-04-22-cx-dynamic-badges.md` — original CX brief.

## Local dry-run of `collect_badge_metrics.py`

```
python scripts/collect_badge_metrics.py \
  --coverage .ci-artifacts/coverage-backend.json \
  --test-results .ci-artifacts/backend-junit.xml \
  --test-results .ci-artifacts/frontend-junit.xml \
  --output /tmp/m.json
```

```json
{
  "tests":       {"schemaVersion": 1, "label": "tests",      "message": "236 passed", "color": "green"},
  "coverage":    {"schemaVersion": 1, "label": "coverage",   "message": "92%",        "color": "green"},
  "lighthouse":  {"schemaVersion": 1, "label": "lighthouse", "message": "n/a",        "color": "lightgrey"}
}
```

Tests count reflects the backend suite (236) only because the local
`frontend-junit.xml` sample was empty at the time of capture (see Notes).
In CI the verify job writes both junit files, and `tests_badge` sums them.

## Workflow YAML validation

```
python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"
```

Exit 0.

## Notes and caveats

- **Windows local vitest junit reporter is fragile.** During cleanup,
  `npm.cmd run test:unit -- --reporter=junit --outputFile=...` left a 0-byte
  XML on Windows git-bash sessions twice in a row (vitest 1.x). The CI path on
  ubuntu is not affected (already seen working in prior CX runs). The
  shields.io badge therefore may briefly show just backend tests if a Windows
  contributor commits without the CI run, but `main` always gets a full count
  because the update runs from the Linux GitHub runner.
- **Per-label file vs `$.tests` query.** The CX brief left the choice between a
  single `metrics.json` with `query=$.tests` and three per-label JSON files.
  The collector writes both, and the README bills them as three separate files
  — the safer path across shields.io endpoint implementations.
- **First green CI push required.** Until `main` gets a push that clears both
  `verify` and `lighthouse`, the shields.io badges render the committed
  placeholders (`n/a` / `lightgrey`). Users can force a cache refresh with
  `?cacheSeconds=0` during the first hour.
- **No coverage gate.** Coverage is reported, not enforced. Revisit later with
  a conservative threshold once the number is known to be stable.
- **Cleanup side-effect.** Three non-tracked items from an interrupted run
  were removed and added to `.gitignore`: `--artifacts-dir/` (shell-escaping
  artefact from a bad CLI quoting), `.ci-artifacts/` (CI upload staging),
  `.coverage` (pytest-cov SQLite database).

## Out of scope (documented for follow-up)

- Frontend coverage badge.
- Bundle-size / Lighthouse accessibility / Lighthouse best-practices badges.
- Coverage threshold gate.
- Security scan / licence scan badges.
- Splitting the first-run placeholder workflow away from the main test workflow.
