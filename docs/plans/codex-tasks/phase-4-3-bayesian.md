# Task 4.3: Bayesian power analysis mode

**Phase:** 4 — Advanced statistics  
**Priority:** Low  
**Depends on:** Phase 0.2 (routes), Phase 0.3 (types)  
**Effort:** ~5h

---

## Context

Read these files before starting:
- `app/backend/app/stats/binary.py`, `continuous.py` — frequentist implementations
- `app/backend/app/schemas/api.py` — `ExperimentInput`, `CalculationResponse`
- `app/backend/app/services/calculations_service.py`
- `app/frontend/src/components/WizardDraftStep.tsx` — step 5 (Constraints)

**Background:** The current tool uses frequentist (NHST) power analysis. A growing share of tech companies use Bayesian approaches that target "precision" instead of "power".

**Bayesian approach for planning:**
- Target: find N such that the 95% credible interval width is ≤ desired precision δ
- For normal approximation (valid when N > 30): `width ≈ 2 × z_{0.975} × pooled_se`
- Binary: `pooled_se ≈ sqrt(2 × p̂(1-p̂)/N)`, so `N = 2 × (z_{0.975} × δ/2)^{-2} × 2p̂(1-p̂)`
- This is mathematically equivalent to the frequentist formula with `power → precision` framing

**Why normal approximation is acceptable:** For experiment planning (not posterior inference), the normal approximation is accurate for N > 30 and provides comparable results (within ±15% of exact MCMC). No MCMC needed.

---

## Goal

1. Add `analysis_mode: 'frequentist' | 'bayesian'` parameter to experiment input
2. Implement Bayesian sample size estimation using normal approximation
3. Switch wizard step 5 UI: frequentist shows alpha/power, Bayesian shows desired_precision
4. Show Bayesian N alongside frequentist N in results for comparison

---

## Steps

### Step 1: Implement Bayesian calculator

Create `app/backend/app/stats/bayesian.py`:

```python
"""
Bayesian sample size estimation via normal approximation.

Targets: find N such that the 95% credible interval width ≤ desired precision.
Uses conjugate normal approximation — no MCMC required.

Reference: Kruschke (2013), "Bayesian estimation supersedes the t test"
"""
import math
from .binary import normal_ppf


def bayesian_sample_size_binary(
    baseline_rate: float,       # proportion (0-1)
    desired_precision: float,   # half-width of 95% CI in pp (0-1), e.g. 0.005 for 0.5pp
    credibility: float = 0.95,  # target credibility level
) -> int:
    """
    Find N such that P(|effect| captured in credibility CI) is high.
    
    For binary outcomes with Beta-Binomial conjugate model:
    Uses normal approximation valid for N > 30.
    
    desired_precision is the HALF-width of the credible interval.
    Example: precision=0.005 means CI will be ±0.5pp wide.
    """
    if not 0 < baseline_rate < 1:
        raise ValueError(f"baseline_rate must be in (0,1), got {baseline_rate}")
    if desired_precision <= 0:
        raise ValueError(f"desired_precision must be > 0, got {desired_precision}")
    
    z = normal_ppf(1 - (1 - credibility) / 2)
    
    # For two-sample test: pooled SE ≈ sqrt(2 * p*(1-p) / N)
    # CI half-width = z * SE = z * sqrt(2*p*(1-p)/N)
    # Solve for N: N = 2 * p*(1-p) * (z/desired_precision)^2
    
    n = 2 * baseline_rate * (1 - baseline_rate) * (z / desired_precision) ** 2
    return math.ceil(n)


def bayesian_sample_size_continuous(
    std_dev: float,             # standard deviation of outcome
    desired_precision: float,  # half-width of 95% CI in same units as metric
    credibility: float = 0.95,
) -> int:
    """
    Find N such that the credible interval half-width ≤ desired_precision.
    
    For normal outcomes with normal-inverse-gamma conjugate model:
    Uses normal approximation.
    """
    if std_dev <= 0:
        raise ValueError(f"std_dev must be > 0, got {std_dev}")
    if desired_precision <= 0:
        raise ValueError(f"desired_precision must be > 0, got {desired_precision}")
    
    z = normal_ppf(1 - (1 - credibility) / 2)
    
    # CI half-width = z * sqrt(2 * sigma^2 / N)
    # Solve: N = 2 * sigma^2 * (z / desired_precision)^2
    
    n = 2 * std_dev ** 2 * (z / desired_precision) ** 2
    return math.ceil(n)


def precision_to_mde_equivalent(
    desired_precision: float,
    baseline_rate: float = None,
    std_dev: float = None,
    metric_type: str = "binary",
) -> float:
    """
    Convert Bayesian precision target to equivalent frequentist MDE.
    
    The precision (CI half-width) is conceptually similar to MDE/2 at high power.
    This is informational for users transitioning between frameworks.
    """
    # precision ≈ MDE / 2 (at 80% power, they're numerically close)
    return desired_precision * 2
```

### Step 2: Add `analysis_mode` and `desired_precision` to schemas

In `app/backend/app/schemas/api.py`:

```python
from typing import Literal

# Add to ExperimentInput:
analysis_mode: Literal["frequentist", "bayesian"] = "frequentist"
desired_precision: float | None = Field(default=None, gt=0)  # for Bayesian mode
credibility: float = Field(default=0.95, gt=0.5, lt=1.0)   # Bayesian credibility level

@model_validator(mode="after")
def check_mode_fields(self) -> "ExperimentInput":
    if self.analysis_mode == "bayesian" and self.desired_precision is None:
        raise ValueError("Bayesian mode requires desired_precision")
    return self
```

Add to `CalculationResponse`:
```python
bayesian_sample_size_per_variant: int | None = None
bayesian_credibility: float | None = None
bayesian_note: str | None = None
```

### Step 3: Wire into calculations service

In `calculations_service.py`:

```python
if request.analysis_mode == "bayesian" and request.desired_precision is not None:
    from ..stats.bayesian import bayesian_sample_size_binary, bayesian_sample_size_continuous
    
    if request.metric_type == "binary":
        bayes_n = bayesian_sample_size_binary(
            baseline_rate=request.baseline_rate / 100,
            desired_precision=request.desired_precision / 100,
            credibility=request.credibility,
        )
    else:
        bayes_n = bayesian_sample_size_continuous(
            std_dev=request.std_dev,
            desired_precision=request.desired_precision,
            credibility=request.credibility,
        )
    
    result.bayesian_sample_size_per_variant = bayes_n
    result.bayesian_credibility = request.credibility
    result.bayesian_note = (
        f"Bayesian estimate: N={bayes_n:,} per variant ensures {request.credibility*100:.0f}% "
        f"credible interval width ≤ {request.desired_precision} "
        f"({'pp' if request.metric_type == 'binary' else 'units'})"
    )
```

### Step 4: Backend tests

Create `app/backend/tests/test_bayesian.py`:

```python
from app.stats.bayesian import bayesian_sample_size_binary, bayesian_sample_size_continuous
import math

def test_binary_bayesian_precision():
    # For p=0.035, precision=0.005 (±0.5pp CI at 95%):
    # N = 2 * 0.035 * 0.965 * (1.96/0.005)^2 ≈ 52,700
    n = bayesian_sample_size_binary(0.035, desired_precision=0.005)
    assert 50000 < n < 60000

def test_binary_bayesian_larger_precision_needs_fewer():
    n1 = bayesian_sample_size_binary(0.035, desired_precision=0.005)
    n2 = bayesian_sample_size_binary(0.035, desired_precision=0.01)  # less precise
    assert n2 < n1

def test_continuous_bayesian():
    n = bayesian_sample_size_continuous(std_dev=12.0, desired_precision=2.0)
    # N = 2 * 144 * (1.96/2)^2 ≈ 274
    assert 200 < n < 400

def test_bayesian_vs_frequentist_comparable():
    # For typical params, Bayesian N should be within ±20% of frequentist N
    from app.stats.binary import calculate_binary_sample_size
    freq_n = calculate_binary_sample_size(0.035, 0.005, 0.05, 0.8)
    bayes_n = bayesian_sample_size_binary(0.035, desired_precision=0.0025)  # precision ≈ MDE/2
    ratio = bayes_n / freq_n
    assert 0.7 < ratio < 1.4

def test_api_bayesian_mode():
    resp = client.post("/api/v1/calculate", json={
        "metric_type": "binary",
        "baseline_rate": 3.5,
        "desired_precision": 0.5,  # ±0.5pp
        "analysis_mode": "bayesian",
        "variants": 2,
        "daily_traffic": 10000,
    })
    assert resp.status_code == 200
    d = resp.json()
    assert d["bayesian_sample_size_per_variant"] is not None
    assert d["bayesian_note"] is not None

def test_bayesian_requires_precision():
    resp = client.post("/api/v1/calculate", json={
        "metric_type": "binary",
        "baseline_rate": 3.5,
        "analysis_mode": "bayesian",
        # missing desired_precision
    })
    assert resp.status_code == 422
```

### Step 5: Frontend — mode toggle in step 5

In `WizardDraftStep.tsx`, step 5 (Constraints), add mode selector:

```tsx
<div className="form-group">
  <label>Analysis framework</label>
  <div className="radio-group">
    <label className="radio-option">
      <input type="radio" name="analysis_mode" value="frequentist"
        checked={(draft.constraints.analysis_mode ?? 'frequentist') === 'frequentist'}
        onChange={() => updateField('constraints.analysis_mode', 'frequentist')}
      />
      <div>
        <strong>Frequentist</strong>
        <p>Set alpha (significance) and power. Classic NHST approach.</p>
      </div>
    </label>
    <label className="radio-option">
      <input type="radio" name="analysis_mode" value="bayesian"
        checked={draft.constraints.analysis_mode === 'bayesian'}
        onChange={() => updateField('constraints.analysis_mode', 'bayesian')}
      />
      <div>
        <strong>Bayesian</strong>
        <p>Set desired precision (credible interval width). No alpha/power needed.</p>
      </div>
    </label>
  </div>
</div>

{/* Conditional fields */}
{mode === 'frequentist' && (
  <>
    {/* existing alpha and power fields */}
  </>
)}

{mode === 'bayesian' && (
  <>
    <div className="form-group">
      <label htmlFor="desired_precision">
        Desired precision ({metricType === 'binary' ? 'pp' : 'units'})
        <Tooltip content="Half-width of the 95% credible interval. Example: 0.5 means the CI will be ±0.5 pp wide.">
          <span className="field-info-icon" tabIndex={0}>ⓘ</span>
        </Tooltip>
      </label>
      <input id="desired_precision" type="number" step="0.01" min="0.001"
        value={draft.constraints.desired_precision ?? ''}
        onChange={e => updateField('constraints.desired_precision', parseFloat(e.target.value))}
      />
    </div>
    <div className="form-group">
      <label htmlFor="credibility">Credibility level</label>
      <SliderInput id="credibility" min={0.8} max={0.99} step={0.01}
        value={draft.constraints.credibility ?? 0.95}
        onChange={v => updateField('constraints.credibility', v)}
      />
    </div>
  </>
)}
```

### Step 6: Frontend — show Bayesian N in ResultsPanel

When `bayesian_sample_size_per_variant` is in the result:

```tsx
{calc.bayesian_sample_size_per_variant && (
  <div className="bayesian-results">
    <h4>Bayesian estimate</h4>
    <div className="bayesian-comparison">
      <span>Frequentist (α={alpha}, power={power}):</span>
      <strong>{calc.sample_size_per_variant.toLocaleString()} per variant</strong>
      <span>Bayesian ({(calc.bayesian_credibility! * 100).toFixed(0)}% CI precision):</span>
      <strong>{calc.bayesian_sample_size_per_variant.toLocaleString()} per variant</strong>
    </div>
    <p className="field-hint">{calc.bayesian_note}</p>
  </div>
)}
```

---

## Verify

- [ ] `python -m pytest tests/test_bayesian.py -v` — all tests pass
- [ ] `python -m pytest tests/ -x -q` — full suite passes
- [ ] `npm run build` exits 0; `npm test` passes
- [ ] API with `analysis_mode=bayesian, desired_precision=0.5` → returns `bayesian_sample_size_per_variant`
- [ ] API with `analysis_mode=bayesian` (no desired_precision) → 422
- [ ] Bayesian N for ρ=3.5%, precision=±0.5pp is in range 50,000–60,000
- [ ] Frequentist fields (alpha, power) are hidden when Bayesian mode selected
- [ ] Bayesian fields (precision, credibility) are hidden when Frequentist mode selected

---

## Constraints

- Normal approximation ONLY — no MCMC, no external stats packages
- The Bayesian N is shown ALONGSIDE the frequentist N (not replacing it) when both modes are computed
- `analysis_mode` defaults to `"frequentist"` — all existing behavior unchanged
- The precision input is in the SAME UNIT as the metric (pp for binary, raw units for continuous) — document this clearly in tooltips
- Do NOT implement prior elicitation or prior sensitivity — that's beyond scope
