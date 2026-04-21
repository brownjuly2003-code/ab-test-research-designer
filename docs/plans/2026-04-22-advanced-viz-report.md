# Advanced Viz Report

## Summary
- Added `PosteriorPlot` and `SequentialBoundaryChart` as lazy-loaded Recharts chunks in results flows.
- Added `BayesianSection` and wired the sequential chart into `SequentialDesignSection`.
- Added 8 new tests:
  - `PosteriorPlot.test.tsx`: 3
  - `SequentialBoundaryChart.test.tsx`: 3
  - `a11y-bayesian-sequential.test.tsx`: 2

## Bundle Sizes
- Main JS: `index-CMOwwYOH.js` - 422.56 kB raw, 121.81 kB gzip
- Posterior chunk: `PosteriorPlot-HSvvBNYq.js` - 15.86 kB raw, 5.80 kB gzip
- Sequential chunk: `SequentialBoundaryChart-D-70Cle9.js` - 2.08 kB raw, 0.91 kB gzip
- Existing Recharts support chunks still split out:
  - `CartesianChart-p8mC2DmH.js` - 353.03 kB raw, 105.43 kB gzip
  - `LineChart-L_foBXTA.js` - 4.62 kB raw, 1.94 kB gzip

## Verification
- `python scripts\generate_frontend_api_types.py --check` -> pass
- `npm.cmd run test:unit -- src/components/PosteriorPlot.test.tsx src/components/SequentialBoundaryChart.test.tsx src/test/a11y-bayesian-sequential.test.tsx` -> pass
- `npm.cmd run test:unit` -> fails on pre-existing `src/i18n.test.tsx` because `src/i18n/index.ts` does not expose an i18next instance with `changeLanguage`
- `npm.cmd run build` -> pass
- `scripts\verify_all.cmd --with-e2e` -> blocked before frontend verification by pre-existing backend/runtime issues:
  - default DB path: `sqlite3.OperationalError: no such column: key_id`
  - fresh temp DB path: `TypeError: register_http_runtime() got an unexpected keyword argument 'repository'`

## Chart Snapshots
- Posterior plot:
  - Smooth posterior bell curve with a light filled area under the full density.
  - Darker shaded band across the credibility interval centered around the posterior mean.
  - Optional dashed prior line when prior inputs are supplied.
- Sequential boundary chart:
  - Two mirrored red boundary curves descending from high early-look z thresholds toward the final look.
  - Gray dashed reference lines at `z = 1.96` and `z = -1.96`.
  - Optional vertical dashed marker for the current look.

## Notes
- Full `git status --short` cannot be empty after this task because the repo already had many unrelated modified and untracked files before implementation.
