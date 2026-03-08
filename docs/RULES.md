# Rules

The warning layer sits on top of deterministic calculations. It does not replace the math; it adds interpretation and feasibility checks that the UI can highlight separately.

## Warning catalog

### `LONG_DURATION`

- Severity: `high`
- Trigger: estimated duration exceeds the recommended maximum duration
- Meaning: test may be too slow to be practical

### `LOW_TRAFFIC`

- Severity: `medium`
- Trigger: effective daily traffic is low
- Meaning: duration and variance risk increase

### `MISSING_VARIANCE`

- Severity: `high`
- Trigger: continuous metric without `std_dev`
- Meaning: deterministic continuous sample size is not trustworthy

### `MANY_VARIANTS_LOW_TRAFFIC`

- Severity: `high`
- Trigger: more than two variants combined with weak effective traffic
- Meaning: the design is too ambitious for available traffic

### `SEASONALITY_PRESENT`

- Severity: `medium`
- Trigger: payload flags seasonality
- Meaning: test should cover at least a full weekly cycle

### `CAMPAIGN_CONTAMINATION`

- Severity: `medium`
- Trigger: active campaigns are present
- Meaning: external acquisition effects can bias lift estimates

### `UNDERPOWERED_DESIGN`

- Severity: `medium`
- Trigger: requested power is below `0.8`
- Meaning: higher risk of false negatives

### `CONSERVATIVE_MULTIVARIANT_ALPHA`

- Severity: `medium`
- Trigger: more than two variants
- Meaning: Bonferroni alpha correction is applied and can inflate required sample size

### `LONG_TEST_NOT_POSSIBLE`

- Severity: `high`
- Trigger: estimated duration is long while the payload says a long test is not possible
- Meaning: the plan is operationally inconsistent

## Rule sources

- catalog metadata: `app/backend/app/rules/catalog.py`
- trigger logic: `app/backend/app/rules/engine.py`

## Frontend behavior

- warnings are shown in a dedicated accordion section
- severity is rendered via red / yellow / green styling
- multivariant designs also surface a dedicated Bonferroni note in the summary cards
