# 2026-04-22 Comparison Dashboard Report

## Dashboard shape

```text
+-----------------------------------------------------------+
| Comparison dashboard                                      |
| [Export Markdown] [Export PDF] [Close]                    |
+-----------------------------------------------------------+
| Project cards: name | metric | sample | duration | risk   |
+-----------------------------------------------------------+
| Power curves: multi-series line chart + legend            |
+-----------------------------------------------------------+
| Sensitivity grid: one table per project                   |
+-----------------------------------------------------------+
| Observed effects: one forest-plot row per project         |
+-----------------------------------------------------------+
| Shared / unique insights: shared lists + diff table       |
+-----------------------------------------------------------+
```

## Verification snapshot

- Backend comparison tests: `pytest app/backend/tests/test_api_routes.py -k compare_multi` -> 6 passed
- Backend export tests: `pytest app/backend/tests/test_export_api.py -k comparison` -> 2 passed
- Frontend dashboard tests: `npx vitest run src/components/ComparisonDashboard.test.tsx src/test/a11y-comparison-dashboard.test.tsx` -> 2 files passed
- Contracts/docs regen checks:
  - `python scripts/generate_frontend_api_types.py --check` -> up to date
  - `python scripts/generate_api_docs.py --check` -> up to date
- Full verify attempt: `cmd /c scripts\verify_all.cmd --with-e2e`
  - stopped in backend suite on unrelated locale tests:
    - `test_export_markdown_endpoint_localizes_content_for_german`
    - `test_export_markdown_endpoint_localizes_content_for_spanish`
    - `test_export_markdown_endpoint_falls_back_to_primary_language_for_regional_locales`

## Performance

- `POST /api/v1/projects/compare` on 5 saved projects, measured via `TestClient` over 20 timed runs:
  - min: `48.84 ms`
  - median: `77.52 ms`
  - p95: `103.49 ms`
  - max: `104.05 ms`
- Result: under the task target of `< 200 ms` for the 5-project compare endpoint

## Bundle notes

- Frontend production build: `npm run build`
- Lazy chunk for `ComparisonDashboard`: `8.37 kB` raw / `1.97 kB` gzip
- This keeps the dashboard-specific payload well below the expected `< 10 kB gzip` growth
- Current main bundle in this worktree: `171.68 kB` gzip
- Result: the dashboard chunk is within budget, but the global `main JS gzip < 145 kB` acceptance target is not met in the current worktree baseline

## Notes

- The comparison flow remains lazy-loaded through `ComparisonSection`
- Mixed metric-type selections surface the warning that direct effect comparison is not meaningful
- `scripts\verify_all.cmd --with-e2e` was attempted, but the run is currently blocked by unrelated de/es export-localization failures before frontend and e2e stages
