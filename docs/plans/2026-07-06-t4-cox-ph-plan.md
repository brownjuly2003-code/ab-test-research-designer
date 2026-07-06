# T4 — Cox proportional hazards: the treatment-effect hazard ratio

Closes the last 5.4 deferral taken into scope (Cox regression), completing the "close every tail"
plan of 2026-07-06. Deliberately scoped to the A/B-relevant model: a **single binary covariate**
(the treatment indicator), making the partial likelihood one-dimensional — a scalar Newton-Raphson,
no matrix algebra — while delivering what the log-rank family cannot: an **effect size**
(``HR = h_treatment / h_control`` with a Wald CI).

## Shape

- **Stats** (`stats/cox_ph.py`, new module): Efron-ties partial likelihood, 1-D Newton-Raphson from
  β = 0 (strictly concave; ~5 iterations), Wald inference (SE = 1/√I, z, χ² = z², CI on HR).
  Divergence guard: |β| > 30 (monotone likelihood / quasi-separation — every event in one arm's risk
  experience) → ``None`` → 400, instead of returning a huge unstable estimate.
- **Schema/service:** ``cox`` joins the survival section's `test_type` selector (third branch).
  Cox is a two-arm regression, so `additional_arms` with ``cox`` is rejected at the schema (422).
  Response reuses the survival shape: `chi_square` carries the Wald z² (1 df); new nullable fields
  `hazard_ratio`, `hazard_ratio_ci_lower/upper`, `log_hazard_ratio`, `log_hazard_ratio_se` are
  populated only on this branch. The descriptive per-arm `expected` counts come from an unweighted
  log-rank pass over the same data (risk-set expectations are test-agnostic), keeping the readout
  comparable across branches; KM curves render exactly as on the log-rank branches.
- **Frontend:** third selector option; the add-arm button and FH exponent inputs disappear on the
  Cox branch; a hazard-ratio card (HR + CI) leads the results grid and the χ² card is relabeled
  "Wald χ²"; client-side guard when extra arms are present.

## Verification

- Freeze before implementation (`scratchpad/verify_cox_ph.py`): from-scratch Efron Newton-Raphson
  vs **statsmodels 0.14.6** `PHReg(ties="efron")` (≤1e-10) and **lifelines 0.30.3** `CoxPHFitter`
  (≤3e-7) — neither a runtime dependency. Frozen Freireich pins: β = −1.5721251488,
  SE = 0.4123967177, HR = 0.207604, 95% CI (0.092513, 0.465873), z = −3.812167, p = 0.0001377538
  (the classic ~5× relapse-hazard reduction of 6-MP).
- +15 backend tests (`test_cox_ph.py`: frozen pins, arm-swap HR inversion — a directed effect,
  unlike the symmetric log-rank —, degenerate/monotone/cap guards, service HR fields + test-agnostic
  expected counts, HTTP round-trip, RU localization, 422 Cox+arms, 400 monotone) and +2 frontend
  tests. All pre-existing survival tests pass unmodified.
- Live uvicorn round-trip: HR 0.2076 CI (0.0925, 0.4659), Wald χ² 14.5326, RU interpretation,
  422 on extra arms, 400 on monotone likelihood.

## Out of scope (documented in the module)

Multi-covariate Cox (adjustment / stratification), time-varying covariates, Breslow ties,
baseline-hazard estimation, proportional-hazards diagnostics (Schoenfeld residuals).
