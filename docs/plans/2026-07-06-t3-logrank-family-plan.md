# T3 — Log-rank test family: k-sample (>2 arms) + Fleming-Harrington weights

Un-defers two of the 5.4 deferrals on explicit request (>2-arm log-rank, weighted log-rank). One
generalization covers both axes: the **weighted k-sample log-rank** — the ``G(ρ, γ)``
Fleming-Harrington family over ``k >= 2`` arms — with the plain 2-arm Mantel-Cox as the
``ρ = γ = 0, k = 2`` special case.

## Shape

- **Stats** (`stats/survival.py`): `weighted_k_sample_log_rank_test(arms, alpha, rho, gamma)` —
  per pooled event time, weight ``w(t) = S(t−)^ρ (1−S(t−))^γ`` from the pooled left-continuous
  Kaplan-Meier (first weight is exactly 1, the lifelines/statsmodels convention); weighted O−E sums
  ``z`` over the first k−1 arms; covariance matrix with hypergeometric per-time terms; χ² = zᵀV⁻¹z on
  k−1 df. ``V`` is inverted via the existing `cuped.solve_linear_system` (singular → ``None`` → 400).
  The legacy `log_rank_test` is untouched; the k=2 unweighted reduction agrees with it to 1e-12
  (pinned).
- **Schema:** `SurvivalResultsRequest` grows backward-compatibly: `additional_arms` (≤ 8, total cap
  `MAX_SURVIVAL_ARMS = 10`), `test_type` ("log_rank" default | "fleming_harrington"), `fh_rho` /
  `fh_gamma` (0..4, consumed only on the weighted branch). `SurvivalResultsResponse` adds
  `test_type`, `fh_rho`/`fh_gamma` (null unless weighted), `arm_summaries` (all arms in request
  order) and `additional_arm_curves`; the flat `observed_*`/`n_*` fields still duplicate the first
  two arms for old clients.
- **Service:** every request now runs through the one generalized statistic. A pre-T3 two-arm
  payload keeps its exact response — same χ², same detailed two-arm interpretation (pinned by
  `test_service_legacy_two_arm_payload_unchanged` and the untouched pre-existing tests). The k>2 /
  weighted branches get a family interpretation (`results.interpretation.log_rank_family`) with a
  localized test name.
- **Frontend:** `SurvivalResultsSection` gains a test selector (ρ/γ inputs appear on the weighted
  branch), add/remove additional-arm textareas, a per-arm events table for k > 2, and curve tables
  for the extra arms. **Conscious minimalism:** the interactive Kaplan-Meier chart still draws the
  first two arms only (`SurvivalCurveChart` is a fixed two-series component; extra arms get full
  curve tables) — generalizing the chart to N series is deliberately out of scope for this slice.

## Verification

- Freeze before implementation (`scratchpad/verify_ksample_weighted_logrank.py`, lifelines 0.30.3 +
  statsmodels 0.14.6, neither a runtime dependency): reference algorithm == lifelines
  `multivariate_logrank_test` exactly across {2, 3 arms} × {unweighted, FH(1,0), FH(0,1)}, and ==
  statsmodels `survdiff(weight_type="fh")` to 5e-15 on the 2-arm G^ρ case. Frozen pins (Freireich +
  a hand-pinned third arm): 3-arm χ² = 19.389263 (df 2, p = 0.00006161), FH(1,0) = 14.457151,
  FH(0,1) = 13.048449, 3-arm FH(1,0) = 16.701169.
- +16 backend tests (stats pins, k=2 reduction, arm-order invariance, ρ=γ=0 == unweighted,
  degenerate/cap/validation guards; service legacy-payload pin; HTTP 3-arm + FH round-trips, RU
  localization, 422 above the arm cap) and +2 frontend tests (third-arm flow + summary table,
  FH exponent submission). All 19 pre-existing survival tests pass unmodified.
- Live uvicorn round-trip: 3-arm 19.3893/df 2, FH(1,0) RU 14.4572 with the localized test name,
  legacy 2-arm payload byte-identical semantics (16.7929, `test_type: "log_rank"`, null exponents).
