# Task 3.1: Multi-metric experiments — guardrail metrics

**Phase:** 3 — Product features  
**Priority:** High  
**Depends on:** Phase 0.2 (routes), Phase 0.3 (types.ts, payload.ts)  
**Effort:** ~5h

---

## Context

Read these files before starting:
- `app/backend/app/schemas/api.py` — `ExperimentInput`, `AnalyzeRequest`, `DesignResponse`
- `app/backend/app/services/calculations_service.py`
- `app/backend/app/services/design_service.py`
- `app/frontend/src/components/WizardDraftStep.tsx` — step 4 (Metrics)
- `app/frontend/src/lib/types.ts` (from Phase 0.3, or `experiment.ts`)
- `app/frontend/src/components/ResultsPanel.tsx`

Current limitation: Only one metric per experiment. In reality, analysts track a primary metric + 2–3 guardrail metrics that should not degrade during the experiment.

---

## Goal

1. Add `guardrail_metrics` field to the experiment payload (backend + frontend)
2. Add UI in step 4 (Metrics) to define up to 3 guardrail metrics
3. Include guardrail metrics in the design report as a separate section
4. Show guardrail section in ResultsPanel

---

## Steps

### Step 1: Backend — add guardrail metrics to schemas

In `app/backend/app/schemas/api.py`, add `GuardrailMetricInput` and update `ExperimentInput`:

```python
class GuardrailMetricInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    name: str = Field(min_length=1, max_length=100)
    metric_type: Literal["binary", "continuous"]
    baseline_rate: float | None = None   # binary: 0–100 (%)
    baseline_mean: float | None = None  # continuous
    std_dev: float | None = None        # continuous
    # No MDE field — guardrail is monitored, not sized for
    
    @model_validator(mode="after")
    def check_type_fields(self) -> "GuardrailMetricInput":
        if self.metric_type == "binary" and self.baseline_rate is None:
            raise ValueError("binary guardrail requires baseline_rate")
        if self.metric_type == "continuous" and (self.baseline_mean is None or self.std_dev is None):
            raise ValueError("continuous guardrail requires baseline_mean and std_dev")
        return self
```

Add to `ExperimentInput` (and `AnalyzeRequest` if separate):
```python
guardrail_metrics: list[GuardrailMetricInput] = Field(default_factory=list, max_length=5)
```

### Step 2: Backend — add guardrail section to design service

In `app/backend/app/services/design_service.py`, add guardrail metrics section to the report:

```python
def build_guardrail_section(guardrail_metrics: list[GuardrailMetricInput], primary_n: int) -> dict:
    """
    For each guardrail metric, calculate the minimum MDE detectable at 80% power
    given the primary sample size N.
    """
    guardrail_results = []
    for g in guardrail_metrics:
        if g.metric_type == "binary":
            detectable_mde = calculate_detectable_mde_binary(
                n=primary_n,
                baseline_rate=g.baseline_rate / 100,
                alpha=0.05,
                power=0.8,
            )
            guardrail_results.append({
                "name": g.name,
                "metric_type": "binary",
                "baseline": g.baseline_rate,
                "detectable_mde_pp": round(detectable_mde * 100, 3),
                "note": f"With N={primary_n:,} per variant, can detect ≥{detectable_mde*100:.2f} pp change at 80% power",
            })
        else:
            detectable_mde = calculate_detectable_mde_continuous(
                n=primary_n,
                std_dev=g.std_dev,
                alpha=0.05,
                power=0.8,
            )
            guardrail_results.append({
                "name": g.name,
                "metric_type": "continuous",
                "baseline": g.baseline_mean,
                "detectable_mde_absolute": round(detectable_mde, 4),
                "note": f"With N={primary_n:,} per variant, can detect ≥{detectable_mde:.4f} change at 80% power",
            })
    return {"guardrail_metrics": guardrail_results}
```

**Implement helper functions** `calculate_detectable_mde_binary` and `calculate_detectable_mde_continuous` in `app/backend/app/stats/`:
- These are the inverse of sample size calculation: given N, find MDE
- For binary: solve for delta in the z-test formula
- For continuous: solve for delta = z_power * std_dev * sqrt(2/n) + z_alpha * std_dev * sqrt(2/n)

Add the guardrail section to the `DesignResponse` schema:
```python
class DesignResponse(BaseModel):
    ...
    guardrail_metrics: list[dict] = Field(default_factory=list)
```

### Step 3: Backend tests

Add to `app/backend/tests/test_api_routes.py`:

```python
def test_analyze_with_guardrail_metrics():
    resp = client.post("/api/v1/analyze", json={
        "experiment": {
            "metric_type": "binary",
            "baseline_rate": 3.5,
            "mde": 0.5,
            "variants": 2,
            "alpha": 0.05,
            "power": 0.8,
            "daily_traffic": 10000,
            "guardrail_metrics": [
                {"name": "Bounce rate", "metric_type": "binary", "baseline_rate": 40.0}
            ]
        }
    })
    assert resp.status_code == 200
    report = resp.json().get("design") or resp.json()
    assert "guardrail_metrics" in report
    assert len(report["guardrail_metrics"]) == 1
    assert "detectable_mde_pp" in report["guardrail_metrics"][0]

def test_guardrail_validation_missing_fields():
    resp = client.post("/api/v1/analyze", json={
        "experiment": {
            "metric_type": "binary",
            "baseline_rate": 3.5,
            "mde": 0.5,
            "guardrail_metrics": [
                {"name": "Revenue", "metric_type": "continuous"}  # missing baseline_mean and std_dev
            ]
        }
    })
    assert resp.status_code == 422
```

### Step 4: Frontend — update types

In `app/frontend/src/lib/types.ts`, add:
```typescript
export interface GuardrailMetricInput {
  name: string;
  metric_type: 'binary' | 'continuous';
  baseline_rate?: number;
  baseline_mean?: number;
  std_dev?: number;
}

// Update ExperimentDraft
export interface ExperimentDraft {
  ...
  guardrail_metrics?: GuardrailMetricInput[];
}
```

### Step 5: Frontend — add guardrail UI in step 4

In `WizardDraftStep.tsx`, in the step 4 (Metrics) section, add a "Guardrail metrics" subsection below the primary metric:

```tsx
<fieldset className="guardrail-section">
  <legend>Guardrail metrics <span className="optional-badge">optional, up to 3</span></legend>
  <p className="field-hint">
    Metrics to monitor but not size for. The tool will show what changes are detectable at your experiment's sample size.
  </p>
  {(draft.guardrail_metrics ?? []).map((g, i) => (
    <div key={i} className="guardrail-item">
      <input
        placeholder="Metric name (e.g. Bounce rate)"
        value={g.name}
        onChange={e => updateGuardrail(i, 'name', e.target.value)}
      />
      <select value={g.metric_type} onChange={e => updateGuardrail(i, 'metric_type', e.target.value)}>
        <option value="binary">Binary (%)</option>
        <option value="continuous">Continuous (mean)</option>
      </select>
      {g.metric_type === 'binary' && (
        <input type="number" placeholder="Baseline %" value={g.baseline_rate ?? ''}
          onChange={e => updateGuardrail(i, 'baseline_rate', parseFloat(e.target.value))} />
      )}
      {g.metric_type === 'continuous' && (
        <>
          <input type="number" placeholder="Baseline mean" value={g.baseline_mean ?? ''}
            onChange={e => updateGuardrail(i, 'baseline_mean', parseFloat(e.target.value))} />
          <input type="number" placeholder="Std dev" value={g.std_dev ?? ''}
            onChange={e => updateGuardrail(i, 'std_dev', parseFloat(e.target.value))} />
        </>
      )}
      <button type="button" onClick={() => removeGuardrail(i)} aria-label="Remove guardrail">✕</button>
    </div>
  ))}
  {(draft.guardrail_metrics?.length ?? 0) < 3 && (
    <button type="button" className="btn-secondary" onClick={addGuardrail}>+ Add guardrail metric</button>
  )}
</fieldset>
```

### Step 6: Frontend — show guardrail results in ResultsPanel

In `ResultsPanel.tsx`, add a "Guardrail metrics" section after the main results:

```tsx
{design?.guardrail_metrics?.length > 0 && (
  <section className="guardrail-results-section">
    <h3>Guardrail metrics</h3>
    <p className="section-hint">These metrics are monitored but don't affect sample sizing.</p>
    <table className="guardrail-table">
      <thead>
        <tr><th>Metric</th><th>Baseline</th><th>Detectable change</th><th>Note</th></tr>
      </thead>
      <tbody>
        {design.guardrail_metrics.map((g, i) => (
          <tr key={i}>
            <td>{g.name}</td>
            <td>{g.baseline}{g.metric_type === 'binary' ? '%' : ''}</td>
            <td className="detectable-mde">
              {g.metric_type === 'binary'
                ? `≥ ${g.detectable_mde_pp} pp`
                : `≥ ${g.detectable_mde_absolute}`}
            </td>
            <td className="guardrail-note">{g.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </section>
)}
```

---

## Verify

- [ ] `cd app/backend && python -m pytest tests/ -x -q` — all tests pass including new guardrail tests
- [ ] `npm run build` exits 0
- [ ] `npm test` passes
- [ ] `npx tsc --noEmit` exits 0
- [ ] Adding 1 guardrail metric (binary, "Bounce rate", 40%) → shows in Review step
- [ ] Running analysis with guardrail → ResultsPanel shows guardrail section with detectable MDE
- [ ] Sending 4 guardrails → backend returns 422 (max 3 enforced by `max_length=3`)
- [ ] Guardrail without required fields → backend returns 422
- [ ] "Add guardrail metric" button disappears when 3 guardrails are added

---

## Constraints

- Sample size calculation is based on PRIMARY metric only — guardrails don't affect N
- The `guardrail_metrics` field must be fully optional (default empty list) — existing experiments without it must work
- The `extra="forbid"` rule on `GuardrailMetricInput` must be enforced
- Do NOT use external statistical libraries — implement MDE inversion using the same math as existing binary/continuous calculators
