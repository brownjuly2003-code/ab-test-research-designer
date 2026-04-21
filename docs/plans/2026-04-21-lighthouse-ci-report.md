# Lighthouse CI Report

## Run

- Date: 2026-04-21
- Command: `npm --prefix app/frontend run build && python scripts/run_lighthouse_ci.py`
- Runtime: backend-served frontend on `http://127.0.0.1:4174/`

## First Run Scores

- performance: `0.89`
- accessibility: `1.00`
- best-practices: `0.93`
- seo: `0.82`

## Median Scores Across 3 Runs

- performance: `0.99`
- accessibility: `1.00`
- best-practices: `0.93`
- seo: `0.82`

## Outcome

`python scripts/run_lighthouse_ci.py` completed with `exit 0`.
No threshold regressions were observed, so no app-code fixes were required.
Accessibility stayed above the strict `0.90` error gate on the first run and on the median result.
