# Hypothesis Edge Cases Report

## Scope
- Added `app/backend/tests/test_property_edge_cases.py` with 19 new edge-case property tests.
- Added `app/backend/tests/test_regression_hypothesis_edge_cases.py` with 5 deterministic reproductions for bugs found by the new properties.

## New Properties
- Numerical edge cases: 7
- Bayesian edge cases: 2
- SRM edge cases: 3
- Sequential testing edge cases: 2
- Monte-Carlo edge cases: 5

## Bugs Uncovered
- `ObservedResultsBinary` and `ObservedResultsContinuous` accepted one-sample arms, producing degenerate result paths instead of validation errors. Fixed by requiring per-arm sample sizes `>= 2`.
- Continuous sample-size calculations accepted near-zero standard deviation and could overflow on `sys.float_info.max / 2`. Fixed by rejecting numerically zero/non-finite std values and converting overflow/infinite sample-size estimates into `ValueError`.
- SRM accepted zero-count variants when total observed count was positive. Fixed by requiring positive observed counts.
- Sequential boundaries rejected `n_looks=100`. Fixed by extending supported looks to 100 and adding bounded inflation for `n_looks > 10`.

## Runtime
- Acceptance property command: `19 passed, 292 deselected in 5.62s`.
- Full direct property module check, including existing `*_properties.py`: `61 passed in 7.34s`.

## Verification
- `python -m pytest -p no:schemathesis app/backend/tests/test_property_edge_cases.py -q` -> `19 passed in 1.05s`
- `python -m pytest -p no:schemathesis app/backend/tests/test_property_edge_cases.py app/backend/tests/test_regression_hypothesis_edge_cases.py app/backend/tests/test_binary_properties.py app/backend/tests/test_continuous_properties.py app/backend/tests/test_bayesian_properties.py app/backend/tests/test_srm_properties.py app/backend/tests/test_sequential_properties.py -q` -> `61 passed in 7.34s`
- `python -m pytest -p no:schemathesis app/backend/tests/ -k "property" -v` -> `19 passed, 292 deselected in 5.62s`
- `python -m pytest -p no:schemathesis app/backend/tests -q` -> `311 passed in 139.49s`
- `scripts\verify_all.cmd --with-e2e` -> exit code `0`

## Notes
- No posterior/prior update API exists in the current Bayesian stats module; Bayesian edge coverage was added around credible-interval precision guarantees exposed by the existing implementation.
