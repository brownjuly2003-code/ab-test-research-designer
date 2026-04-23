# Statistics methods

The product combines fixed-horizon sizing, optional Bayesian precision planning, and operational safeguards that help teams decide whether an experiment is feasible before launch.

## Method summary

| Method | Where it appears | What it does |
| --- | --- | --- |
| Binary fixed-horizon sizing | `POST /api/v1/calculate` for binary metrics | Uses a two-sided normal approximation for difference in proportions and returns per-variant sample size, total sample, and duration. |
| Continuous fixed-horizon sizing | `POST /api/v1/calculate` for continuous metrics | Uses a two-sample mean comparison with equal-sized variants and relative MDE over the baseline mean. |
| Bonferroni correction | Multi-variant plans | Adjusts alpha across treatment-vs-control comparisons so larger variant sets do not silently understate required sample size. |
| Bayesian precision sizing | `analysis_mode=bayesian` with `desired_precision` | Estimates per-variant sample size needed to hit a target credible-interval half-width. |
| Group sequential boundaries | `n_looks > 1` | Adds O'Brien-Fleming style boundaries and a sample-size inflation factor for planned interim looks. |
| SRM check | `POST /api/v1/srm-check` and design warnings | Uses a chi-square imbalance check to flag suspicious traffic allocation. |
| CUPED adjustment | Continuous metrics with pre-experiment covariates | Reduces the effective standard deviation based on pre-period correlation and shows the resulting sample-size and duration savings. |

## Practical interpretation

- Frequentist sizing answers "How much traffic do we need to detect the planned effect?"
- Bayesian sizing answers "How much traffic do we need for a precise posterior estimate?"
- Sequential planning answers "What changes if we plan interim looks before the end?"
- SRM and warning rules answer "Is the setup trustworthy enough to launch or read out?"

## Notes on implementation

- Binary and continuous sizing both treat MDE as a relative uplift over the baseline.
- Multi-variant plans apply a conservative Bonferroni adjustment rather than a looser multiple-testing correction.
- SRM is flagged when the chi-square p-value drops below `0.001`.
- CUPED is surfaced as an alternative planning scenario, not as a hidden override of the main result.
