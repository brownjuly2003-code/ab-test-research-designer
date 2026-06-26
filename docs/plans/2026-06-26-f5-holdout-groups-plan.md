# F5 — Holdout groups (cumulative held-back effect)

**Status:** in progress · branch `feat/holdout-groups` from `main` (F4 guardrail merged, PR #30).

## Why (market gap, research-driven)

`AB_research.md` flagged **Holdout groups** (Statsig built-in) as the second in-class market gap
after guardrails (F4). A holdout is a long-lived **held-back** group that is *excluded from the
rollout*: comparing "everything we shipped" against "users who got nothing" measures the
**cumulative effect** of the rollout — separately from the per-variant primary test. This catches
the failure mode where the sum of individually stat-sig wins over-states reality (winner's curse,
interactions, novelty decay): the cumulative holdout readout is the honest aggregate.

Today `holdout_fraction` is **design-time only** (it shrinks the allocated traffic in
`calculations_service`, affecting the duration estimate). The `variation_index = -1` tail is
"not in the experiment" and is **never recorded as an exposure**; `get_experiment_analysis_aggregates`
explicitly filters `variation_index >= 0`. So there is **no analysis of the holdout effect** — F5
adds it.

## Design (vertical slice, mirrors F3b/F4 — no new statistic, no schema bump)

**Concept:** cumulative effect = **pooled treated** (the union of treatment arms, `variation_index >= 1`)
vs **holdout** (`variation_index = -1`, held back) on the **primary metric**. Reuses the existing
two-proportion / Welch test (`analyze_results`) + Bayesian `simulate_uplift_distribution` + the
anytime-valid (`_always_valid_block`) view — exactly the primary path, just over the
treated-vs-holdout split. Pooling treatment arms is a sum of sufficient statistics (pre-treatment of
nothing new) — no new test statistic.

**Why pooled treated, not control (vi=0):** control is the *baseline within the experiment window*;
the holdout is the *long-lived held-back* group that measures the rollout's standing effect over
time. The cumulative question is "treated (what we rolled out) vs held back", so control stays out
of the treated pool. Documented in the block note.

**No schema bump:** the `exposures` table already stores `variation_index INTEGER NOT NULL` (the
`ge=0` floor is only on the `ExposureIngestRequest` Pydantic schema, not the DB), so holdout
membership rides the existing exposures store with `variation_index = -1`. Holdout outcomes ride the
ordinary `POST /conversions` stream under the primary metric name. Only one new read query
(`get_holdout_aggregates`, `WHERE variation_index = -1`). schema_version stays **11**.

### Backend

1. **`schemas/api.py`**
   - `HoldoutEvent {user_id}` + `HoldoutIngestRequest {holdout: list[HoldoutEvent]}` (cap reuses the
     ingest batch limit pattern).
   - `LiveHoldoutArmStat {label, exposed_users, converted_users, conversion_rate?, mean?, std?}`
     (`label` ∈ `treated` | `holdout`).
   - `LiveHoldoutBlock {status, note, treated?, holdout?, analysis?, probability_treated_beats_holdout?,
     always_valid?, treated_users_total?, holdout_users_total?}`.
   - `LiveStatsResponse += holdout: LiveHoldoutBlock`.

2. **`repository.py`**
   - `record_holdout(exp, items)` — `INSERT INTO exposures (... variation_index=-1 ...) ON
     CONFLICT(experiment_id, user_id) DO NOTHING` (first-write-wins; a user already exposed to an arm
     stays in that arm — you cannot be both held back and treated). `{received, recorded, deduplicated}`.
   - `get_holdout_aggregates(exp, metric)` — same CTE as `get_experiment_analysis_aggregates` but
     `WHERE e.variation_index = -1`, returning one `holdout` group `{exposed_users, converted_users,
     value_sum, value_sq_sum}` (or `None` if the experiment is missing). Portable dual-SQL (`?`→`%s`).

3. **`services/live_stats_service.py`**
   - `_pool_treated_arms(arms)` — sum sufficient stats of arms[1:] (`vi >= 1`) into one treated arm.
   - `_build_holdout_block(metric_type, alpha, arms, holdout_aggregates, mixture_variance)`:
     - `unavailable` when metric is ratio, or no holdout users ingested.
     - `insufficient_data` when either pool has < 2 users / degenerate variance.
     - `ok` → reuse `analyze_results` (binary/continuous) for treated-vs-holdout cumulative effect +
       CI + p; `simulate_uplift_distribution` for P(treated > holdout) (binary); `_always_valid_block`.
   - Wire into `build_live_stats` (param `holdout_aggregates`, field `holdout`).

4. **`routes/execution.py`**
   - `POST /api/v1/experiments/{id}/holdout` → `record_holdout`.
   - `_compute_live_stats`: `holdout_aggregates = get_holdout_aggregates(exp, metric_name)`; pass to
     `build_live_stats`.

5. **Contract** regenerated (`api-contract.ts` + `docs/API.md`), `--check` green.

### decision_service — deliberately untouched

The holdout is a long-lived *cumulative* readout, not a gate on *this* experiment's ship decision
(it lives beyond the experiment window). Like CUPED and post-stratification (variance-reduction
views that also do not alter the verdict), the holdout block is informational. `decision_service`
keeps deciding on the primary comparisons + guardrail breach. If we later want a cumulative-regression
caution, that is a separate increment.

### Frontend

6. `LiveStatsSection` `HoldoutBlock` (treated vs holdout arms, cumulative effect / CI / p, status pill,
   always-valid line) + i18n ×7 (`results.liveStats.holdout*`; "holdout" not translated, as SRM/CUPED).
   `{{n}}` interpolation variable (not `{{count}}`, to avoid i18next pluralization needing ru `_few/_many`).

### Tests

7. `test_execution_live_stats` + holdout cases: unavailable (none ingested / ratio metric),
   insufficient, ok-binary, ok-continuous, **pooled-treated correctness** (two treatment arms fold
   into one treated pool), endpoint collects holdout aggregates end-to-end (create → POST /holdout +
   /exposures + /conversions → GET /live-stats → cumulative effect).
   `test_postgres_backend` + holdout round-trip (dual-SQL, verify-postgres / Mac).
   `vitest` `LiveStatsSection` holdout render.

8. Full gate: backend pytest + coverage ≥ 88, mypy --strict, ruff, tsc, full vitest, vite build < 500 kB,
   contract `--check`, locale.

## Out of scope (honest non-goals)

- Multi-experiment / global holdout across experiments — that is a platform-level concern (closer to
  the warehouse-native non-goal); F5 is the in-experiment cumulative held-back readout.
- holdout-driven ship veto — see decision_service note above.
