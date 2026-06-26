# Live-read SQL performance at scale (2026-06-26)

Workstream (1) of Юля's chosen next steps (handoff #20): the live-read rollups degraded badly at
scale — CUPED ran ~9s on 3000 covariate users, and the demo had to be seeded ≤2000/arm to stay
responsive. Goal: make the live-read path fast and **linear**, touching the verified dual-backend
stats-SQL as little as possible (indexes before restructuring).

## Measured baseline (SQLite, best-of-3, N=3000 users, K=3 covariates)

| function | baseline | after |
|---|---|---|
| `get_experiment_analysis_aggregates` | 679 ms | **28 ms** |
| `get_stratified_aggregates` | 2157 ms | **19 ms** |
| `get_event_timing_summary` | 2766 ms | **22 ms** |
| `get_ratio_aggregates` | 6926 ms | **19 ms** |
| `get_cuped_aggregates` | 8744 ms | **162 ms** |

`get_experiment_analysis_aggregates` was additionally **O(N²)** (128 → 445 → 2401 ms at
N = 1500 → 3000 → 6000); it is now **linear** (11 → 25 → 48 → 106 ms at N = 1500 → 3000 → 6000 → 12000).

Reproduced with throwaway benchmark scripts (not committed; live in the session scratchpad), and the
query plans inspected with `EXPLAIN QUERY PLAN`.

## Root causes and fixes

### 1. Missing per-user conversion index (the big, safe win)

The heavy rollups (stratified / CUPED / ratio / event-timing / holdout) join each exposed user onto
their conversions with `experiment_id = ? AND user_id = e.user_id AND metric = ?`. The only
conversions index was `(experiment_id, metric)`, so that correlated join degraded to a per-user scan.

**Fix:** add a composite index `idx_conversions_experiment_user_metric (experiment_id, user_id,
metric)` to **both** backends (`_create_execution_tables` for SQLite, `_init_db` for Postgres). The
existing `(experiment_id, metric)` index is kept — it still serves the metric-only filter in
`get_experiment_analysis_aggregates`. `CREATE INDEX IF NOT EXISTS` runs on every startup on both
backends, so existing DBs pick it up idempotently — **no schema-version bump, no separate migration.**

This one index fixed four of the five functions (57×–412×).

### 2. Quadratic primary rollup (`get_experiment_analysis_aggregates`)

This function resolves conversions through `identity_map` first (the `conv_resolved` CTE, one row per
event) and joins the arms to that **materialized, un-indexed** CTE by canonical id — a per-event scan
per arm user, i.e. O(users × conversions). The two `NOT EXISTS` filters (`spike`, `excluded`) were
also re-evaluated per arm row as correlated scalar subqueries, and `spike` re-aggregated every time.

**Fix (structure-only, behavior identical):**
- Pre-aggregate `conv_resolved` to **one row per canonical user** in a new `conv_per_user` CTE
  (`SUM(value) AS user_value, COUNT(*) AS n_events`) *before* joining to the arms, so the planner
  hash-joins one-row-per-user tables instead of scanning per event.
- Fold the rate-spike test into `n_events` (`n_events <= threshold`), removing the separate `spike`
  aggregation entirely.
- Remove deny-list users with a `LEFT JOIN excluded ... WHERE ex.cuser IS NULL` anti-join
  (materialized once), and `SELECT DISTINCT` in `excluded` so the anti-join can't duplicate rows.
- `converted` is now "user has a `conv_per_user` row" and `user_value` is `COALESCE(cpu.user_value,
  0)` — identical semantics to the old `MAX(... cr.id IS NOT NULL ...)` / `COALESCE(SUM(cr.value),0)`.

CUPED's "covered CTE computed 3×" is **no longer a problem** — with the index each pass is cheap
(162 ms), so no restructuring of the verified CUPED SQL was needed.

## Verification

- **Behavior unchanged:** full backend suite **719 passed / 17 skipped** (same as baseline). The
  changed paths are covered by the identity-resolution (P4.3) and bot/fraud-filter (P4.4) tests in
  `test_execution_ingestion_repository.py` plus `test_execution_live_stats.py` /
  `test_decision_service.py` / `test_results_service.py` (128 of those run targeted, all green).
- **Regression guard:** new `test_performance.py::test_live_read_rollups_stay_well_under_a_second_at_scale`
  seeds 2000 users and asserts the primary and CUPED rollups stay < 2.0 s (≈0.1 s optimized, multi-second
  if the index/structure regresses).
- Gate (serial, Windows): ruff ✓ · mypy `--strict` 67 ✓ · backend 719/17 ✓.
- **Dual-backend:** the index + restructured query are validated on real Postgres by CI
  `verify-postgres` (no Docker on Windows). Both fixes are standard portable SQL; placeholder count
  unchanged (5 `?`).

## Scope

Backend-only: `app/backend/app/repository.py` (index ×2 backends + primary-rollup restructure) and
`app/backend/tests/test_performance.py` (guard). No schema / API / contract / frontend / locale change.
