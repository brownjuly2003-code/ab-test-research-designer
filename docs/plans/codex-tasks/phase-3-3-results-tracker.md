# Task 3.3: Post-experiment results tracker

**Phase:** 3 — Product features  
**Priority:** Medium  
**Depends on:** Phase 0.2 (routes), Phase 3.1 (multi-metric types)  
**Effort:** ~6h

---

## Context

Read these files before starting:
- `app/backend/app/schemas/api.py`
- `app/backend/app/stats/binary.py` — z-test implementation
- `app/backend/app/stats/continuous.py` — t-test implementation
- `app/backend/app/repository.py` — projects table structure
- `app/frontend/src/components/ResultsPanel.tsx`
- `app/frontend/src/lib/types.ts`

**Background:** Currently the tool helps design an experiment (planning phase) but has no way to close the loop by recording and analyzing actual experiment results. Users leave the tool after launch and return to spreadsheets/Optimizely for result analysis. This is a major lifecycle gap.

---

## Goal

1. Add `POST /api/v1/results` backend endpoint — compute significance from actual observed data
2. Add ability to save observed results to a project
3. Add "Results" section in the frontend (separate from the design phase)
4. Show: observed effect, confidence interval, p-value, significance verdict, forest plot (text-based for now)

---

## Steps

### Step 1: Backend schemas for observed results

In `app/backend/app/schemas/api.py`:

```python
class ObservedResultsBinary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    control_conversions: int = Field(ge=0)
    control_users: int = Field(ge=1)
    treatment_conversions: int = Field(ge=0)
    treatment_users: int = Field(ge=1)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)

class ObservedResultsContinuous(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    control_mean: float
    control_std: float = Field(gt=0)
    control_n: int = Field(ge=1)
    treatment_mean: float
    treatment_std: float = Field(gt=0)
    treatment_n: int = Field(ge=1)
    alpha: float = Field(default=0.05, ge=0.001, le=0.1)

class ResultsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    metric_type: Literal["binary", "continuous"]
    binary: ObservedResultsBinary | None = None
    continuous: ObservedResultsContinuous | None = None
    
    @model_validator(mode="after")
    def check_type(self) -> "ResultsRequest":
        if self.metric_type == "binary" and self.binary is None:
            raise ValueError("binary metric_type requires binary data")
        if self.metric_type == "continuous" and self.continuous is None:
            raise ValueError("continuous metric_type requires continuous data")
        return self

class ResultsResponse(BaseModel):
    metric_type: str
    observed_effect: float          # absolute difference (pp for binary, units for continuous)
    observed_effect_relative: float # relative change %
    control_rate: float | None = None
    treatment_rate: float | None = None
    ci_lower: float
    ci_upper: float
    ci_level: float                 # e.g. 0.95
    p_value: float
    test_statistic: float           # z or t
    is_significant: bool
    power_achieved: float           # post-hoc power (informational)
    verdict: str                    # human-readable conclusion
    interpretation: str             # fuller explanation
```

### Step 2: Backend — implement results calculation

Create `app/backend/app/services/results_service.py`:

```python
import math
from ..schemas.api import ResultsRequest, ResultsResponse
from ..stats.binary import normal_ppf


def analyze_results(request: ResultsRequest) -> ResultsResponse:
    if request.metric_type == "binary":
        return _analyze_binary(request.binary)
    return _analyze_continuous(request.continuous)


def _analyze_binary(obs) -> ResultsResponse:
    p1 = obs.control_conversions / obs.control_users
    p2 = obs.treatment_conversions / obs.treatment_users
    
    # Pooled z-test (two-proportion)
    p_pooled = (obs.control_conversions + obs.treatment_conversions) / (obs.control_users + obs.treatment_users)
    se = math.sqrt(p_pooled * (1 - p_pooled) * (1/obs.control_users + 1/obs.treatment_users))
    
    if se == 0:
        return ResultsResponse(
            metric_type="binary", observed_effect=0, observed_effect_relative=0,
            control_rate=p1, treatment_rate=p2,
            ci_lower=0, ci_upper=0, ci_level=1 - obs.alpha,
            p_value=1.0, test_statistic=0, is_significant=False,
            power_achieved=0,
            verdict="Cannot compute — zero standard error",
            interpretation="Insufficient data or degenerate inputs",
        )
    
    z = (p2 - p1) / se
    p_value = 2 * (1 - standard_normal_cdf(abs(z)))
    
    # Confidence interval (Wald, not pooled)
    se_ci = math.sqrt(p1 * (1 - p1) / obs.control_users + p2 * (1 - p2) / obs.treatment_users)
    z_crit = normal_ppf(1 - obs.alpha / 2)
    ci_lower = (p2 - p1) - z_crit * se_ci
    ci_upper = (p2 - p1) + z_crit * se_ci
    
    effect = p2 - p1
    rel_effect = (effect / p1 * 100) if p1 > 0 else 0
    is_sig = p_value < obs.alpha
    
    # Post-hoc power (non-central z approximation)
    power = standard_normal_cdf(abs(z) - z_crit)
    
    verdict = _verdict(is_sig, effect, obs.alpha)
    interp = _interpretation_binary(p1, p2, effect, p_value, is_sig, ci_lower, ci_upper)
    
    return ResultsResponse(
        metric_type="binary",
        observed_effect=round(effect * 100, 4),       # in pp
        observed_effect_relative=round(rel_effect, 2),
        control_rate=round(p1 * 100, 4),
        treatment_rate=round(p2 * 100, 4),
        ci_lower=round(ci_lower * 100, 4),
        ci_upper=round(ci_upper * 100, 4),
        ci_level=1 - obs.alpha,
        p_value=round(p_value, 6),
        test_statistic=round(z, 4),
        is_significant=is_sig,
        power_achieved=round(power, 3),
        verdict=verdict,
        interpretation=interp,
    )


def _analyze_continuous(obs) -> ResultsResponse:
    # Welch's t-test (unequal variances)
    se = math.sqrt(obs.control_std**2 / obs.control_n + obs.treatment_std**2 / obs.treatment_n)
    
    if se == 0:
        return ResultsResponse(metric_type="continuous", observed_effect=0, ...)
    
    t = (obs.treatment_mean - obs.control_mean) / se
    
    # Welch-Satterthwaite degrees of freedom
    df = _welch_df(obs)
    p_value = 2 * (1 - t_cdf(abs(t), df))
    
    z_crit = normal_ppf(1 - obs.alpha / 2)
    ci_lower = (obs.treatment_mean - obs.control_mean) - z_crit * se
    ci_upper = (obs.treatment_mean - obs.control_mean) + z_crit * se
    
    effect = obs.treatment_mean - obs.control_mean
    rel_effect = (effect / obs.control_mean * 100) if obs.control_mean != 0 else 0
    is_sig = p_value < obs.alpha
    
    return ResultsResponse(
        metric_type="continuous",
        observed_effect=round(effect, 4),
        observed_effect_relative=round(rel_effect, 2),
        ci_lower=round(ci_lower, 4),
        ci_upper=round(ci_upper, 4),
        ci_level=1 - obs.alpha,
        p_value=round(p_value, 6),
        test_statistic=round(t, 4),
        is_significant=is_sig,
        power_achieved=0.0,   # post-hoc power for t-test is complex — skip for now
        verdict=_verdict(is_sig, effect, obs.alpha),
        interpretation=f"Treatment mean {obs.treatment_mean:.4f} vs control {obs.control_mean:.4f}. "
                       f"Effect: {effect:+.4f} [{ci_lower:.4f}, {ci_upper:.4f}].",
    )
```

Add helper functions: `standard_normal_cdf`, `t_cdf`, `_welch_df`, `_verdict`, `_interpretation_binary`.
Use the same approach as existing `binary.py` / `continuous.py` — pure Python math, no scipy.

### Step 3: Add `/api/v1/results` endpoint

In `routes/analysis.py`:

```python
@router.post("/api/v1/results", response_model=ResultsResponse)
async def analyze_experiment_results(request: ResultsRequest, ...):
    return analyze_results(request)
```

### Step 4: Backend tests

Create `app/backend/tests/test_results_service.py`:

```python
def test_binary_significant():
    resp = client.post("/api/v1/results", json={
        "metric_type": "binary",
        "binary": {
            "control_conversions": 1750, "control_users": 50000,
            "treatment_conversions": 2000, "treatment_users": 50000,
        }
    })
    assert resp.status_code == 200
    d = resp.json()
    assert d["is_significant"] is True
    assert d["p_value"] < 0.05
    assert d["observed_effect"] == pytest.approx(0.5, abs=0.01)  # 0.5 pp

def test_binary_not_significant():
    resp = client.post("/api/v1/results", json={
        "metric_type": "binary",
        "binary": {
            "control_conversions": 100, "control_users": 1000,
            "treatment_conversions": 105, "treatment_users": 1000,
        }
    })
    assert resp.json()["is_significant"] is False

def test_continuous_significant():
    resp = client.post("/api/v1/results", json={
        "metric_type": "continuous",
        "continuous": {
            "control_mean": 45.0, "control_std": 12.0, "control_n": 5000,
            "treatment_mean": 47.5, "treatment_std": 12.5, "treatment_n": 5000,
        }
    })
    assert resp.json()["is_significant"] is True
    assert resp.json()["observed_effect"] == pytest.approx(2.5, abs=0.01)
```

### Step 5: Frontend — Results entry UI

In `ResultsPanel.tsx`, add a new tab or section "Enter actual results":

```tsx
{analysisResult && (
  <section className="actual-results-section">
    <h3>Actual experiment results</h3>
    <p className="field-hint">
      After running the experiment, enter actual data to compute statistical significance.
    </p>
    
    {draft.metrics.metric_type === 'binary' ? (
      <div className="results-input-grid">
        <div>
          <label>Control conversions</label>
          <input type="number" value={actualResults.control_conversions ?? ''} ... />
        </div>
        <div>
          <label>Control users</label>
          <input type="number" value={actualResults.control_users ?? ''} ... />
        </div>
        <div>
          <label>Treatment conversions</label>
          <input type="number" value={actualResults.treatment_conversions ?? ''} ... />
        </div>
        <div>
          <label>Treatment users</label>
          <input type="number" value={actualResults.treatment_users ?? ''} ... />
        </div>
      </div>
    ) : (
      /* Continuous inputs: mean, std, n for each group */
    )}
    
    <button className="btn-secondary" onClick={computeResults}>Analyze results</button>
    
    {resultsAnalysis && (
      <div className={`results-verdict ${resultsAnalysis.is_significant ? 'significant' : 'not-significant'}`}>
        <h4>{resultsAnalysis.verdict}</h4>
        <div className="results-stats-grid">
          <div><span>Effect</span><strong>{resultsAnalysis.observed_effect} pp</strong></div>
          <div><span>95% CI</span><strong>[{resultsAnalysis.ci_lower}, {resultsAnalysis.ci_upper}]</strong></div>
          <div><span>p-value</span><strong>{resultsAnalysis.p_value}</strong></div>
          <div><span>Test stat</span><strong>{resultsAnalysis.test_statistic}</strong></div>
        </div>
        {/* Text-based forest plot: ---|---[  ===|=== ]---|--- */}
        <ForestPlot
          effect={resultsAnalysis.observed_effect}
          ciLower={resultsAnalysis.ci_lower}
          ciUpper={resultsAnalysis.ci_upper}
        />
        <p className="results-interpretation">{resultsAnalysis.interpretation}</p>
      </div>
    )}
  </section>
)}
```

### Step 6: Create text-based `ForestPlot` component

Create `app/frontend/src/components/ForestPlot.tsx`:

A CSS-only horizontal visualization:
- A horizontal number line (zero at center)
- A filled bar representing the confidence interval
- A diamond/dot at the point estimate
- Labels: effect value, CI bounds

```tsx
// Simple proportional CSS implementation
// Example output: ──────◆[==●==]────── 
//                  -1pp  0  +0.5pp  +2pp
```

---

## Verify

- [ ] `python -m pytest tests/test_results_service.py -v` — all tests pass
- [ ] `python -m pytest tests/ -x -q` — full suite passes
- [ ] `npm run build` exits 0; `npm test` passes
- [ ] Binary with 1750/50000 vs 2000/50000 → p < 0.05, is_significant = true
- [ ] Binary with 100/1000 vs 105/1000 → is_significant = false
- [ ] Confidence interval contains zero ↔ not significant (should always be consistent)
- [ ] Forest plot renders: CI bar visible, point estimate marker visible

---

## Constraints

- Implement t-test CDF without scipy — use a normal approximation or series expansion (Welch df is typically large so normal approximation is valid for n > 30)
- The results section must be shown only AFTER analysis is run (requires analysisResult to be present)
- p-value must be two-sided
- Do NOT store actual results in the database by default (save is optional, user-triggered)
- The `ResultsResponse` schema must NOT have `extra="forbid"` — it may evolve
