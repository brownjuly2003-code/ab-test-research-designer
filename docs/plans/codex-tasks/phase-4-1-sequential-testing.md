# Task 4.1: Sequential testing — O'Brien-Fleming alpha spending

**Phase:** 4 — Advanced statistics  
**Priority:** Medium  
**Depends on:** Phase 0.2 (routes), Phase 0.3 (types)  
**Effort:** ~6h

---

## Context

Read these files before starting:
- `app/backend/app/stats/binary.py` — z-test, normal_ppf
- `app/backend/app/stats/continuous.py`
- `app/backend/app/services/calculations_service.py`
- `app/backend/app/schemas/api.py` — `ExperimentInput`, `CalculationResponse`
- `app/backend/app/rules/catalog.py` — warning codes
- `app/backend/app/rules/engine.py` — warning logic
- `app/frontend/src/components/WizardDraftStep.tsx` — step 5 (Constraints)
- `app/frontend/src/components/ResultsPanel.tsx`

**Background:** Fixed-horizon testing requires committing to a sample size before the experiment runs. Sequential testing (group sequential design) allows early stopping while controlling Type I error.

The O'Brien-Fleming spending function is the most widely-used approach in clinical trials and increasingly in tech experimentation. It "spends" alpha conservatively at early looks and more liberally at later ones.

**Reference formulas:**
- O'Brien-Fleming boundary at look k of K: `z_k = z_α/2 * sqrt(K/k)` (approximation)
- Exact approach: use Lan-DeMets spending function `α*(t) = 2 * (1 - Φ(z_α/2 / sqrt(t)))` where `t = k/K`
- Sample size inflation for group sequential design (approximate): multiply by inflation factor from Wang-Tsiatis family

---

## Goal

1. Add `n_looks` parameter to experiment input (number of interim analyses including final)
2. Implement O'Brien-Fleming alpha spending in the stats layer
3. Return per-look alpha boundaries in the calculation response
4. Add warning rule `INTERIM_LOOKS_INCREASE_SAMPLE`
5. Add UI for `n_looks` in step 5, show boundaries table in results

---

## Steps

### Step 1: Implement O'Brien-Fleming in stats layer

Create `app/backend/app/stats/sequential.py`:

```python
"""
Group sequential design using O'Brien-Fleming alpha spending function.
Reference: Lan & DeMets (1983), O'Brien & Fleming (1979).

All implementations use pure Python math — no external dependencies.
"""
import math
from .binary import normal_ppf, standard_normal_cdf


def obrien_fleming_boundaries(
    n_looks: int,
    alpha: float = 0.05,
) -> list[dict]:
    """
    Compute O'Brien-Fleming boundaries for a group sequential design.
    
    Uses the Lan-DeMets spending function approach:
    alpha_spent(t) = 2 * (1 - Φ(z_{α/2} / sqrt(t)))
    
    Args:
        n_looks: total number of analyses (including final), 1 ≤ n_looks ≤ 10
        alpha: overall two-sided Type I error rate
        
    Returns:
        List of dicts: [{look: k, info_fraction: t, alpha_spent: a, z_boundary: z, p_boundary: p}, ...]
    
    Example:
        n_looks=3, alpha=0.05 →
        [
          {look: 1, info_fraction: 0.333, alpha_spent: 0.000052, z_boundary: 3.47, p_boundary: 0.000052},
          {look: 2, info_fraction: 0.667, alpha_spent: 0.009, z_boundary: 2.45, p_boundary: 0.014},
          {look: 3, info_fraction: 1.0,  alpha_spent: 0.05,  z_boundary: 1.97, p_boundary: 0.05},
        ]
    """
    if not 1 <= n_looks <= 10:
        raise ValueError(f"n_looks must be between 1 and 10, got {n_looks}")
    
    z_half_alpha = normal_ppf(1 - alpha / 2)
    boundaries = []
    cumulative_alpha_spent = 0.0
    
    for k in range(1, n_looks + 1):
        t = k / n_looks  # information fraction
        
        # Lan-DeMets O'Brien-Fleming spending function
        # alpha*(t) = 2*(1 - Phi(z_{alpha/2} / sqrt(t)))
        cumulative_spent = 2 * (1 - standard_normal_cdf(z_half_alpha / math.sqrt(t)))
        incremental_alpha = cumulative_spent - cumulative_alpha_spent
        cumulative_alpha_spent = cumulative_spent
        
        # Two-sided boundary: z_k such that P(|Z| > z_k) = incremental_alpha
        z_boundary = normal_ppf(1 - incremental_alpha / 2)
        
        boundaries.append({
            "look": k,
            "info_fraction": round(t, 4),
            "cumulative_alpha_spent": round(cumulative_spent, 6),
            "incremental_alpha": round(incremental_alpha, 6),
            "z_boundary": round(z_boundary, 4),
            "p_boundary": round(incremental_alpha, 6),
            "is_final": k == n_looks,
        })
    
    return boundaries


def sequential_sample_size_inflation(n_looks: int, alpha: float = 0.05, power: float = 0.8) -> float:
    """
    Approximate inflation factor for fixed-horizon sample size when using
    O'Brien-Fleming group sequential design.
    
    Uses the Wang-Tsiatis (1987) approximation for the O'Brien-Fleming family.
    
    Returns:
        Inflation factor > 1.0 (e.g., 1.08 = 8% more samples required)
    """
    if n_looks == 1:
        return 1.0
    
    # Empirical inflation factors for O'Brien-Fleming (from simulation tables)
    # These are well-established in the literature
    INFLATION = {
        2: 1.013,
        3: 1.020,
        4: 1.025,
        5: 1.028,
        6: 1.030,
        7: 1.032,
        8: 1.033,
        9: 1.034,
        10: 1.035,
    }
    return INFLATION.get(n_looks, 1.035)
```

**Validation** — add a test that checks known O'Brien-Fleming values:
- `n_looks=5, alpha=0.05` → final look boundary z ≈ 2.04 (close to standard 1.96)
- `n_looks=1, alpha=0.05` → boundary z = 1.96 exactly

### Step 2: Add `n_looks` to experiment input and calculation response

In `app/backend/app/schemas/api.py`:

```python
# Add to ExperimentInput (and AnalyzeRequest):
n_looks: int = Field(default=1, ge=1, le=10)

# Add to CalculationResponse:
sequential_boundaries: list[dict] | None = None
sequential_inflation_factor: float | None = None
sequential_adjusted_sample_size: int | None = None
```

### Step 3: Wire into calculations service

In `calculations_service.py`, after computing fixed-horizon `sample_size_per_variant`:

```python
if request.n_looks > 1:
    from ..stats.sequential import obrien_fleming_boundaries, sequential_sample_size_inflation
    
    inflation = sequential_sample_size_inflation(request.n_looks, request.alpha, request.power)
    adjusted_n = math.ceil(sample_size_per_variant * inflation)
    boundaries = obrien_fleming_boundaries(request.n_looks, request.alpha)
    
    result.sequential_boundaries = boundaries
    result.sequential_inflation_factor = round(inflation, 4)
    result.sequential_adjusted_sample_size = adjusted_n
```

### Step 4: Add warning rule `INTERIM_LOOKS_INCREASE_SAMPLE`

In `app/backend/app/rules/catalog.py`:
```python
INTERIM_LOOKS_INCREASE_SAMPLE = WarningDef(
    code="INTERIM_LOOKS_INCREASE_SAMPLE",
    severity="medium",
    message="Sequential design increases required sample size by ~{pct}%",
)
```

In `engine.py`, add rule:
```python
if hasattr(calc, 'sequential_inflation_factor') and calc.sequential_inflation_factor and calc.sequential_inflation_factor > 1.0:
    pct = round((calc.sequential_inflation_factor - 1) * 100, 1)
    warnings.append(Warning(
        code="INTERIM_LOOKS_INCREASE_SAMPLE",
        severity="medium",
        message=f"Sequential design with {n_looks} looks increases required sample size by ~{pct}%",
    ))
```

### Step 5: Backend tests

Create `app/backend/tests/test_sequential.py`:

```python
from app.stats.sequential import obrien_fleming_boundaries, sequential_sample_size_inflation

def test_single_look_is_standard_z():
    b = obrien_fleming_boundaries(1, alpha=0.05)
    assert len(b) == 1
    assert abs(b[0]["z_boundary"] - 1.96) < 0.01

def test_five_looks_final_boundary():
    b = obrien_fleming_boundaries(5, alpha=0.05)
    assert len(b) == 5
    # Final look boundary should be close to 2.04 for O'Brien-Fleming
    assert abs(b[-1]["z_boundary"] - 2.04) < 0.1

def test_boundaries_monotone_decreasing():
    b = obrien_fleming_boundaries(5, alpha=0.05)
    z_vals = [x["z_boundary"] for x in b]
    # Early boundaries are more conservative (higher z)
    assert all(z_vals[i] >= z_vals[i+1] for i in range(len(z_vals)-1))

def test_inflation_increases_with_looks():
    factors = [sequential_sample_size_inflation(k) for k in range(1, 6)]
    assert all(factors[i] <= factors[i+1] for i in range(len(factors)-1))
    assert factors[0] == 1.0  # n_looks=1 → no inflation

def test_api_sequential():
    resp = client.post("/api/v1/calculate", json={
        "metric_type": "binary",
        "baseline_rate": 3.5,
        "mde": 0.5,
        "variants": 2,
        "alpha": 0.05,
        "power": 0.8,
        "daily_traffic": 10000,
        "n_looks": 5,
    })
    assert resp.status_code == 200
    d = resp.json()
    assert d["sequential_boundaries"] is not None
    assert len(d["sequential_boundaries"]) == 5
    assert d["sequential_adjusted_sample_size"] > d["sample_size_per_variant"]
```

### Step 6: Frontend — add `n_looks` field in step 5

In `WizardDraftStep.tsx`, step 5 (Constraints), add:

```tsx
<div className="form-group">
  <label htmlFor="n_looks">
    Interim analyses
    <Tooltip content="Number of times you plan to check results during the experiment. 1 = fixed-horizon (no peeking). 2-5 = group sequential (allows early stopping via O'Brien-Fleming boundaries).">
      <span className="field-info-icon" tabIndex={0}>ⓘ</span>
    </Tooltip>
  </label>
  <select
    id="n_looks"
    value={draft.constraints.n_looks ?? 1}
    onChange={e => updateField('constraints.n_looks', parseInt(e.target.value))}
  >
    <option value={1}>1 — Fixed horizon (no interim analyses)</option>
    <option value={2}>2 — One interim + final</option>
    <option value={3}>3 — Two interims + final</option>
    <option value={4}>4 — Three interims + final</option>
    <option value={5}>5 — Four interims + final</option>
  </select>
</div>
```

### Step 7: Frontend — show sequential boundaries in ResultsPanel

When `calculationResult.sequential_boundaries` exists, add a "Sequential design" section:

```tsx
{calc.sequential_boundaries && (
  <section className="sequential-section">
    <h3>Group Sequential Design (O'Brien-Fleming)</h3>
    <p>Adjusted sample size: <strong>{calc.sequential_adjusted_sample_size?.toLocaleString()}</strong> per variant ({((calc.sequential_inflation_factor! - 1) * 100).toFixed(1)}% more than fixed-horizon)</p>
    
    <table className="boundaries-table">
      <thead>
        <tr><th>Look</th><th>Info fraction</th><th>Cum. α spent</th><th>Z boundary</th><th>Stop if |Z| ≥</th></tr>
      </thead>
      <tbody>
        {calc.sequential_boundaries.map(b => (
          <tr key={b.look} className={b.is_final ? 'final-look' : ''}>
            <td>{b.look}</td>
            <td>{(b.info_fraction * 100).toFixed(0)}%</td>
            <td>{b.cumulative_alpha_spent.toFixed(4)}</td>
            <td>{b.z_boundary}</td>
            <td><strong>{b.z_boundary}</strong></td>
          </tr>
        ))}
      </tbody>
    </table>
    <p className="field-hint">Stop early at any look if |observed Z| ≥ boundary. Otherwise, continue to next look.</p>
  </section>
)}
```

---

## Verify

- [ ] `python -m pytest tests/test_sequential.py -v` — all tests pass
- [ ] `python -m pytest tests/ -x -q` — full suite passes
- [ ] `npm run build` exits 0; `npm test` passes
- [ ] API with `n_looks=5` returns `sequential_boundaries` array of 5 items
- [ ] `n_looks=5`: first look z-boundary ≈ 3.47; last look ≈ 2.04
- [ ] `n_looks=1`: `sequential_boundaries` is null (no sequential design)
- [ ] Sequential adjusted sample size > fixed-horizon sample size
- [ ] Warning `INTERIM_LOOKS_INCREASE_SAMPLE` appears in results when `n_looks > 1`

---

## Constraints

- Implement chi-square CDF from scratch — no scipy
- The inflation factors in `INFLATION` dict are empirically established constants — do NOT derive them from scratch; the table above is sufficient for n_looks ≤ 10
- The sequential design is informational only — it does NOT change `sample_size_per_variant` (the base fixed-horizon value); instead, `sequential_adjusted_sample_size` is shown separately
- Keep `n_looks` fully optional — default 1 means fixed-horizon, all existing behavior unchanged
