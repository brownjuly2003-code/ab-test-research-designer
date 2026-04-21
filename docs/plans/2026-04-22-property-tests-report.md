# Property-Based Tests Report

## Scope
- Added `hypothesis==6.152.1` to `app/backend/requirements.txt`.
- Left `pytest.ini` unchanged: no Hypothesis deprecation warnings were emitted in the new suite.
- Confirmed `.hypothesis/` is already covered by `.gitignore`.

## Invariants Covered

### `app/backend/tests/test_binary_properties.py`
- Sample size stays positive and finite for valid binary inputs.
- Sample size decreases as MDE increases.
- Sample size decreases as alpha increases.
- Sample size increases as power increases.
- Fixed-horizon round-trip holds: requested binary MDE matches back-calculated detectable MDE within tolerance.
- Bonferroni correction is monotone: more variants do not reduce per-variant sample size and do not increase adjusted alpha.
- `analyze_results` is symmetric under control/treatment swap for observed effect sign and p-value.
- `analyze_results` keeps p-value and achieved power within `[0, 1]` and returns finite outputs.

### `app/backend/tests/test_continuous_properties.py`
- Sample size stays positive and finite for valid continuous inputs.
- Sample size decreases as MDE increases.
- Sample size decreases as alpha increases.
- Sample size increases as power increases.
- Fixed-horizon round-trip holds for continuous MDE within tolerance once per-variant sample size is non-trivial.
- Bonferroni correction is monotone for multi-variant designs.
- `analyze_results` is symmetric under control/treatment swap for observed effect sign and p-value.
- `analyze_results` keeps p-value bounded and CI outputs finite.
- CUPED variance reduction stays within mathematical bounds and grows with `|correlation|`.

### `app/backend/tests/test_srm_properties.py`
- Exact expected counts produce `chi_square ~= 0`, `p_value > 0.95`, `is_srm = False`.
- Single-user perturbations on large balanced allocations stay below SRM detection threshold.
- Chi-square output is finite and non-negative; p-value stays in `[0, 1]`.
- Joint permutation of observed counts and expected fractions preserves SRM results.
- Expected counts preserve total sample size.
- Larger skew increases chi-square and lowers p-value.

### `app/backend/tests/test_sequential_properties.py`
- Cumulative alpha spending is monotone and stays below nominal alpha.
- O'Brien-Fleming z-boundaries decrease across looks.
- Reported p-boundaries match two-sided z-boundaries.
- Final sequential boundary is not below fixed-horizon boundary.
- Sample size inflation is monotone in the number of looks.
- Sequentially adjusted sample size is never smaller than fixed-horizon sample size.

### `app/backend/tests/test_bayesian_properties.py`
- Binary Bayesian sample size stays positive and finite.
- Continuous Bayesian sample size stays positive and finite.
- Relaxing desired precision reduces required sample size.
- Increasing credibility increases required sample size.
- Binary Bayesian sample size is symmetric around baseline rate `0.5`.
- `precision_to_mde_equivalent` stays positive, finite, and linear in requested precision.

## Bugs / Edge Cases Found
- No target-module bugs were reproduced in `stats/binary.py`, `stats/continuous.py`, `stats/srm.py`, `stats/sequential.py`, or `stats/bayesian.py`.
- During final verification, unrelated pre-existing backend failures surfaced outside the task scope:
  - `app/backend/tests/test_api_keys.py::test_api_key_management_requires_admin_token`
  - `app/backend/tests/test_api_routes.py::*compare_multi*`
  - `app/backend/tests/test_api_routes.py::test_diagnostics_endpoint_returns_runtime_summary`
  - `app/backend/tests/test_export_api.py::*localizes_content*`
  - `app/backend/tests/test_export_api.py::*comparison*`

## Runtime
- Property suite only:
  - `python -m pytest app/backend/tests/test_binary_properties.py app/backend/tests/test_continuous_properties.py app/backend/tests/test_srm_properties.py app/backend/tests/test_sequential_properties.py app/backend/tests/test_bayesian_properties.py -q`
  - Result: `37 passed in 8.13s`
- Full backend suite:
  - `python -m pytest app/backend/tests -q`
  - Result: `220 passed, 13 failed in 133.80s`
  - The failing tests are unrelated to the added property-based coverage and block the task's original acceptance target of a fully green backend suite.
