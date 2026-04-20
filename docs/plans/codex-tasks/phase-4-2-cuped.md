# Task 4.2: CUPED variance reduction estimator

**Phase:** 4 — Advanced statistics  
**Priority:** Medium  
**Depends on:** Phase 0.2 (routes), Phase 0.3 (types)  
**Effort:** ~4h

---

## Context

### Files to read (understand before touching)
- `app/backend/app/stats/continuous.py` — existing variance and sample size formulas
- `app/backend/app/schemas/api.py` — `ExperimentInput`, `CalculationResponse`
- `app/backend/app/services/calculations_service.py`
- `app/frontend/src/components/WizardDraftStep.tsx` — step 4 (Metrics)
- `app/frontend/src/components/ResultsPanel.tsx`

### Files you MUST also modify to make the feature end-to-end

These were omitted from the read list but are required for a working implementation:
- `app/backend/app/routes/analysis.py` — register the updated request schema and pass `cuped_*` fields through to the service
- `app/frontend/src/lib/payload.ts` — include `cuped_pre_experiment_std`, `cuped_correlation` in `buildCalculatePayload()` and `buildAnalyzePayload()` when set
- `app/frontend/src/lib/types.ts` — add `cuped_pre_experiment_std?: number`, `cuped_correlation?: number`, `cuped_enabled?: boolean` to `ExperimentDraft` metrics section
- `app/frontend/src/hooks/useCalculationPreview.ts` — `canCompute()` and `buildCalculatePayload()` must pass CUPED fields so live preview reflects CUPED savings in real time
- `app/backend/tests/test_calculations.py` — add CUPED test cases (listed in Steps below)

**Scope rule:** modify any file needed for a working, tested feature. Do not limit yourself to the read list.

**Background:** CUPED (Controlled-experiment Using Pre-Experiment Data) reduces variance of the outcome metric by removing the component explained by pre-experiment behavior. This can significantly reduce required sample size.

**Math:** If Y is the outcome metric and X is the pre-experiment covariate with correlation ρ:
- `Var(Y_cuped) = Var(Y) * (1 - ρ²)`
- Sample size reduction: `N_cuped = N_naive * (1 - ρ²)`
- Example: ρ = 0.5 → 25% sample size reduction

CUPED applies only to **continuous metrics** (where variance is meaningful).
For binary metrics, CUPED-equivalent techniques exist but are less standard — skip for now.

---

## Goal

1. Add optional CUPED fields to continuous metric input: `pre_experiment_std` and `correlation_with_outcome`
2. When these fields are provided, compute CUPED-adjusted sample size alongside naive
3. Show CUPED savings in the results
4. Add UI toggle in step 4 for CUPED inputs

---

## Steps

### Step 1: Add CUPED formula to `continuous.py`

In `app/backend/app/stats/continuous.py`, add:

```python
def calculate_cuped_variance_reduction(
    outcome_std: float,
    pre_experiment_std: float,
    correlation: float,
) -> tuple[float, float]:
    """
    CUPED variance reduction.
    
    Args:
        outcome_std: standard deviation of the outcome metric
        pre_experiment_std: standard deviation of the pre-experiment covariate
        correlation: Pearson correlation between pre-experiment covariate and outcome (ρ)
    
    Returns:
        (cuped_std, variance_reduction_fraction)
        cuped_std = std * sqrt(1 - ρ²)
        variance_reduction_fraction = 1 - (1 - ρ²) = ρ²
    
    Raises:
        ValueError: if |correlation| >= 1.0 (degenerate case)
    """
    if abs(correlation) >= 1.0:
        raise ValueError(f"Correlation must be in (-1, 1), got {correlation}")
    if correlation == 0:
        return outcome_std, 0.0
    
    variance_reduction = correlation ** 2
    cuped_std = outcome_std * math.sqrt(1 - variance_reduction)
    
    return cuped_std, variance_reduction
```

### Step 2: Update schemas

In `app/backend/app/schemas/api.py`, update continuous metric section of `ExperimentInput`:

```python
# Add to ExperimentInput (continuous metric fields):
cuped_pre_experiment_std: float | None = Field(default=None, gt=0)
cuped_correlation: float | None = Field(default=None, gt=-1.0, lt=1.0)
```

Add to `CalculationResponse`:
```python
cuped_std: float | None = None
cuped_sample_size_per_variant: int | None = None
cuped_variance_reduction_pct: float | None = None
cuped_duration_days: float | None = None
```

### Step 3: Wire CUPED into calculations service

In `calculations_service.py`, after computing the naive continuous sample size:

```python
if (request.metric_type == "continuous"
    and request.cuped_correlation is not None
    and request.cuped_pre_experiment_std is not None):
    
    from ..stats.continuous import calculate_cuped_variance_reduction
    
    cuped_std, variance_reduction = calculate_cuped_variance_reduction(
        outcome_std=request.std_dev,
        pre_experiment_std=request.cuped_pre_experiment_std,
        correlation=request.cuped_correlation,
    )
    cuped_n = calculate_continuous_sample_size(
        baseline_mean=request.baseline_mean,
        std_dev=cuped_std,
        mde=request.mde,
        alpha=request.alpha,
        power=request.power,
        variants=request.variants,
    )
    cuped_duration = estimate_duration(cuped_n, request.daily_traffic, ...)
    
    result.cuped_std = round(cuped_std, 4)
    result.cuped_sample_size_per_variant = cuped_n
    result.cuped_variance_reduction_pct = round(variance_reduction * 100, 1)
    result.cuped_duration_days = round(cuped_duration, 1)
```

### Step 4: Backend tests

Add to `app/backend/tests/test_calculations.py`:

```python
def test_cuped_reduces_sample_size():
    resp = client.post("/api/v1/calculate", json={
        "metric_type": "continuous",
        "baseline_mean": 45.0,
        "std_dev": 12.0,
        "mde": 2.0,
        "variants": 2,
        "alpha": 0.05,
        "power": 0.8,
        "daily_traffic": 10000,
        "cuped_pre_experiment_std": 12.0,
        "cuped_correlation": 0.5,
    })
    assert resp.status_code == 200
    d = resp.json()
    assert d["cuped_sample_size_per_variant"] is not None
    # ρ=0.5 → 25% reduction → cuped_n ≈ 0.75 * naive_n
    assert d["cuped_sample_size_per_variant"] < d["sample_size_per_variant"]
    assert abs(d["cuped_variance_reduction_pct"] - 25.0) < 0.5  # ρ²=0.25

def test_cuped_zero_correlation():
    resp = client.post("/api/v1/calculate", json={
        "metric_type": "continuous",
        "baseline_mean": 45.0,
        "std_dev": 12.0,
        "mde": 2.0,
        "variants": 2,
        "alpha": 0.05,
        "power": 0.8,
        "daily_traffic": 10000,
        "cuped_pre_experiment_std": 12.0,
        "cuped_correlation": 0.0,
    })
    d = resp.json()
    # Zero correlation = no reduction
    assert d["cuped_sample_size_per_variant"] == d["sample_size_per_variant"]

def test_cuped_not_applied_to_binary():
    # CUPED fields should be ignored for binary metric (or return 422)
    resp = client.post("/api/v1/calculate", json={
        "metric_type": "binary",
        "baseline_rate": 3.5,
        "mde": 0.5,
        "cuped_correlation": 0.5,  # should be ignored silently
    })
    assert resp.status_code == 200
    assert resp.json()["cuped_sample_size_per_variant"] is None
```

### Step 5: Frontend — CUPED toggle in step 4

In `WizardDraftStep.tsx`, step 4 (Metrics), below the continuous metric fields:

```tsx
{metricType === 'continuous' && (
  <div className="cuped-section">
    <label className="toggle-label">
      <input
        type="checkbox"
        checked={draft.metrics.cuped_enabled ?? false}
        onChange={e => updateField('metrics.cuped_enabled', e.target.checked)}
      />
      <span>Enable CUPED variance reduction</span>
      <Tooltip content="If you have pre-experiment data correlated with your metric (e.g., prior week's revenue), CUPED can reduce required sample size by ρ² × 100%.">
        <span className="field-info-icon" tabIndex={0}>ⓘ</span>
      </Tooltip>
    </label>
    
    {draft.metrics.cuped_enabled && (
      <div className="cuped-fields form-row">
        <div className="form-group">
          <label htmlFor="cuped_pre_experiment_std">Pre-experiment std dev</label>
          <input
            id="cuped_pre_experiment_std"
            type="number" step="0.01" min="0"
            placeholder="e.g. 11.8"
            value={draft.metrics.cuped_pre_experiment_std ?? ''}
            onChange={e => updateField('metrics.cuped_pre_experiment_std', parseFloat(e.target.value))}
          />
        </div>
        <div className="form-group">
          <label htmlFor="cuped_correlation">
            Correlation with outcome (ρ)
            <Tooltip content="Pearson correlation between pre-experiment metric and outcome metric. Higher = more variance reduction. Typical values: 0.3–0.7.">
              <span className="field-info-icon" tabIndex={0}>ⓘ</span>
            </Tooltip>
          </label>
          <input
            id="cuped_correlation"
            type="number" step="0.01" min="-0.99" max="0.99"
            placeholder="e.g. 0.5"
            value={draft.metrics.cuped_correlation ?? ''}
            onChange={e => updateField('metrics.cuped_correlation', parseFloat(e.target.value))}
          />
        </div>
      </div>
    )}
  </div>
)}
```

### Step 6: Frontend — show CUPED savings in ResultsPanel

When `calculationResult.cuped_sample_size_per_variant` exists:

```tsx
{calc.cuped_sample_size_per_variant && (
  <div className="cuped-results">
    <h4>CUPED-adjusted estimate</h4>
    <div className="cuped-comparison">
      <div className="cuped-card naive">
        <span className="cuped-label">Without CUPED</span>
        <span className="cuped-value">{calc.sample_size_per_variant.toLocaleString()}</span>
        <span className="cuped-unit">users / variant</span>
      </div>
      <div className="cuped-arrow">→</div>
      <div className="cuped-card adjusted">
        <span className="cuped-label">With CUPED (ρ²={calc.cuped_variance_reduction_pct}%)</span>
        <span className="cuped-value cuped-savings">{calc.cuped_sample_size_per_variant.toLocaleString()}</span>
        <span className="cuped-unit">users / variant</span>
      </div>
      <div className="cuped-savings-badge">
        -{calc.cuped_variance_reduction_pct}% sample size
      </div>
    </div>
  </div>
)}
```

---

## Verify

- [ ] `python -m pytest tests/test_calculations.py -v` — all tests pass (including new CUPED tests)
- [ ] `python -m pytest tests/ -x -q` — full suite passes
- [ ] `npm run build` exits 0; `npm test` passes
- [ ] Enabling CUPED with ρ=0.5 → `cuped_sample_size_per_variant ≈ 0.75 × sample_size_per_variant`
- [ ] Disabling CUPED → no CUPED fields in calculation response
- [ ] CUPED fields only appear in wizard when metric_type = 'continuous'
- [ ] Live preview (Phase 1.3) updates when CUPED correlation changes
- [ ] `cuped_variance_reduction_pct` for ρ=0.5 is exactly 25.0

---

## Constraints

- CUPED applies ONLY to continuous metrics — for binary, ignore cuped fields silently (return null)
- Validate: `|cuped_correlation| < 1.0` — reject values ≥ 1.0 or ≤ -1.0 with 422
- The CUPED fields are OPTIONAL — if not provided, response returns null for cuped fields
- Do NOT replace the naive sample size calculation — show CUPED as an additive comparison
- The `cuped_enabled` flag in the draft is a UI-only field — not sent to backend; the backend detects CUPED from non-null `cuped_correlation`
