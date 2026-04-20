# Task 3.2: SRM Detection — Sample Ratio Mismatch checker

**Phase:** 3 — Product features  
**Priority:** High  
**Depends on:** Phase 0.2 (routes/analysis.py)  
**Effort:** ~4h

---

## Context

Read these files before starting:
- `app/backend/app/rules/catalog.py` — existing warning codes
- `app/backend/app/rules/engine.py` — warning rule logic
- `app/backend/app/schemas/api.py`
- `app/frontend/src/components/ResultsPanel.tsx` — where to add the SRM checker UI
- `app/frontend/src/lib/api.ts`

**Background:** Sample Ratio Mismatch (SRM) is when the actual traffic split in an experiment differs significantly from the intended split. For example, you designed a 50/50 split, but actual data shows 4800/5200. This indicates a randomization or tracking bug and invalidates experiment results.

SRM is detected via chi-square test: compare observed counts against expected proportions.
A p-value < 0.001 is the industry standard threshold for SRM alert.

**Why this matters:** No mainstream open-source A/B calculator checks for SRM. This is a genuine differentiating feature.

---

## Goal

1. Add `POST /api/v1/srm-check` backend endpoint
2. Add SRM warning rule that fires during planning (when actual_counts are provided)
3. Add SRM checker UI widget in ResultsPanel (post-analysis data entry)

---

## Steps

### Step 1: Implement chi-square SRM test in stats layer

Create `app/backend/app/stats/srm.py`:

```python
"""
Sample Ratio Mismatch detection via chi-square goodness-of-fit test.
No external dependencies — uses Python stdlib math.
"""
import math


def chi_square_srm(
    observed_counts: list[int],
    expected_fractions: list[float],
) -> tuple[float, float, bool]:
    """
    Detect SRM via chi-square test.
    
    Args:
        observed_counts: actual user counts per variant, e.g. [4800, 5200]
        expected_fractions: planned fractions per variant, e.g. [0.5, 0.5]
        
    Returns:
        (chi_square_statistic, p_value, is_srm_detected)
        SRM detected when p_value < 0.001
    
    Raises:
        ValueError: if lengths don't match, or total is 0
    """
    if len(observed_counts) != len(expected_fractions):
        raise ValueError("observed_counts and expected_fractions must have same length")
    
    total = sum(observed_counts)
    if total == 0:
        raise ValueError("Total observed count must be > 0")
    
    expected_counts = [f * total for f in expected_fractions]
    
    chi_sq = sum(
        (o - e) ** 2 / e
        for o, e in zip(observed_counts, expected_counts)
        if e > 0
    )
    
    df = len(observed_counts) - 1
    p_value = 1 - chi_square_cdf(chi_sq, df)
    
    return chi_sq, p_value, p_value < 0.001


def chi_square_cdf(x: float, df: int) -> float:
    """
    CDF of chi-square distribution using regularized incomplete gamma function.
    Implemented via series expansion — accurate to 6 decimal places for df ≤ 20, x ≤ 50.
    """
    if x <= 0:
        return 0.0
    return regularized_gamma_p(df / 2, x / 2)


def regularized_gamma_p(a: float, x: float) -> float:
    """Lower regularized incomplete gamma function P(a, x) via series expansion."""
    if x == 0:
        return 0.0
    
    # Use series expansion for small x, continued fraction for large x
    if x < a + 1:
        return _gamma_series(a, x)
    else:
        return 1.0 - _gamma_continued_fraction(a, x)


def _gamma_series(a: float, x: float) -> float:
    """Series expansion of P(a,x)."""
    ap = a
    delta = 1.0 / a
    total = delta
    for _ in range(200):
        ap += 1
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * 1e-10:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_continued_fraction(a: float, x: float) -> float:
    """Continued fraction expansion of Q(a,x) = 1 - P(a,x)."""
    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d
    for i in range(1, 201):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30: d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30: c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-10:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
```

### Step 2: Add SRM schemas

In `app/backend/app/schemas/api.py`:

```python
class SrmCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    observed_counts: list[int] = Field(min_length=2, max_length=10)
    expected_fractions: list[float] = Field(min_length=2, max_length=10)
    
    @model_validator(mode="after")
    def validate_lengths_and_fractions(self) -> "SrmCheckRequest":
        if len(self.observed_counts) != len(self.expected_fractions):
            raise ValueError("observed_counts and expected_fractions must have same length")
        if any(c < 0 for c in self.observed_counts):
            raise ValueError("observed_counts must be non-negative")
        total_frac = sum(self.expected_fractions)
        if abs(total_frac - 1.0) > 0.01:
            raise ValueError(f"expected_fractions must sum to 1.0, got {total_frac:.4f}")
        return self

class SrmCheckResponse(BaseModel):
    chi_square: float
    p_value: float
    is_srm: bool
    verdict: str  # "No SRM detected" or "SRM detected — check randomization"
    observed_counts: list[int]
    expected_counts: list[float]
```

### Step 3: Add `/api/v1/srm-check` endpoint

In `app/backend/app/routes/analysis.py`:

```python
@router.post("/api/v1/srm-check", response_model=SrmCheckResponse)
async def check_srm(request: SrmCheckRequest, ...):
    chi_sq, p_value, is_srm = chi_square_srm(
        observed_counts=request.observed_counts,
        expected_fractions=request.expected_fractions,
    )
    total = sum(request.observed_counts)
    expected = [f * total for f in request.expected_fractions]
    
    return SrmCheckResponse(
        chi_square=round(chi_sq, 4),
        p_value=round(p_value, 6),
        is_srm=is_srm,
        verdict="SRM detected — check your randomization or tracking implementation" if is_srm else "No SRM detected",
        observed_counts=request.observed_counts,
        expected_counts=[round(e, 1) for e in expected],
    )
```

### Step 4: Backend tests for SRM

Create `app/backend/tests/test_srm.py`:

```python
def test_no_srm_equal_split():
    resp = client.post("/api/v1/srm-check", json={
        "observed_counts": [5000, 5000],
        "expected_fractions": [0.5, 0.5],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_srm"] is False
    assert data["p_value"] > 0.001

def test_srm_detected_skewed():
    resp = client.post("/api/v1/srm-check", json={
        "observed_counts": [4800, 5200],
        "expected_fractions": [0.5, 0.5],
    })
    assert resp.status_code == 200
    data = resp.json()
    # 4800/5200 on 10000 total: chi-sq = (200^2/5000)*2 = 16, p ≈ 0.000063
    assert data["is_srm"] is True
    assert data["p_value"] < 0.001

def test_srm_three_variants():
    resp = client.post("/api/v1/srm-check", json={
        "observed_counts": [3300, 3300, 3400],
        "expected_fractions": [0.333, 0.333, 0.334],
    })
    assert resp.status_code == 200
    assert resp.json()["is_srm"] is False

def test_srm_fractions_must_sum_to_one():
    resp = client.post("/api/v1/srm-check", json={
        "observed_counts": [5000, 5000],
        "expected_fractions": [0.6, 0.6],  # sums to 1.2
    })
    assert resp.status_code == 422

def test_srm_mismatched_lengths():
    resp = client.post("/api/v1/srm-check", json={
        "observed_counts": [5000, 5000, 5000],
        "expected_fractions": [0.5, 0.5],
    })
    assert resp.status_code == 422
```

### Step 5: Frontend — SRM checker widget in ResultsPanel

In `ResultsPanel.tsx`, add a collapsible "SRM Check" section at the bottom of the results:

```tsx
<Accordion title="SRM Check — did your experiment run as planned?">
  <p className="field-hint">
    Enter actual user counts per variant from your analytics to check for Sample Ratio Mismatch.
    SRM means your randomization or tracking may be broken.
  </p>
  
  <div className="srm-inputs">
    {variantNames.map((name, i) => (
      <div key={i} className="srm-input-group">
        <label>{name}</label>
        <input
          type="number"
          placeholder="Actual users"
          value={srmCounts[i] ?? ''}
          onChange={e => updateSrmCount(i, parseInt(e.target.value))}
        />
      </div>
    ))}
  </div>
  
  <button
    className="btn-secondary"
    onClick={runSrmCheck}
    disabled={!canRunSrm}
  >
    Check for SRM
  </button>
  
  {srmResult && (
    <div className={`srm-result ${srmResult.is_srm ? 'srm-alert' : 'srm-ok'}`}>
      <strong>{srmResult.is_srm ? '⚠ SRM Detected' : '✓ No SRM'}</strong>
      <p>{srmResult.verdict}</p>
      <p>χ² = {srmResult.chi_square}, p = {srmResult.p_value.toFixed(6)}</p>
      {srmResult.is_srm && (
        <p className="srm-guidance">
          Expected: [{srmResult.expected_counts.map(c => Math.round(c)).join(', ')}] — 
          Observed: [{srmResult.observed_counts.join(', ')}]
        </p>
      )}
    </div>
  )}
</Accordion>
```

Add to `api.ts`:
```typescript
srmCheck: (payload: SrmCheckRequest): Promise<SrmCheckResponse> =>
  post('/api/v1/srm-check', payload),
```

---

## Verify

- [ ] `cd app/backend && python -m pytest tests/test_srm.py -v` — all 5 tests pass
- [ ] `python -m pytest tests/ -x -q` — all tests pass
- [ ] `npm run build` exits 0
- [ ] `npm test` passes
- [ ] In browser: enter [4800, 5200] for 50/50 split → red alert "SRM Detected"
- [ ] Enter [5000, 5000] for 50/50 split → green "No SRM"
- [ ] `curl -X POST http://localhost:8008/api/v1/srm-check -H "Content-Type: application/json" -d '{"observed_counts":[4800,5200],"expected_fractions":[0.5,0.5]}'` → `"is_srm": true`

---

## Constraints

- Do NOT use scipy or any external statistics library — implement chi-square CDF from scratch (see `srm.py` above)
- The SRM checker is POST-experiment: it appears in ResultsPanel, not during wizard setup
- p-value threshold is 0.001 (industry standard, more conservative than the 0.05 experiment alpha)
- The chi-square implementation must be accurate to at least 4 decimal places — validate against known values:
  - chi_sq=16, df=1 → p ≈ 0.0000633
  - chi_sq=3.841, df=1 → p ≈ 0.05
