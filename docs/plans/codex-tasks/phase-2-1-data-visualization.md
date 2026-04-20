# Task 2.1: Data visualization — power curve + sensitivity table + new API endpoint

**Phase:** 2 — Visual transformation  
**Priority:** High  
**Depends on:** Phase 0.2 (routes/analysis.py), Phase 0.1 (CSS tokens)  
**Effort:** ~6h

---

## Context

Read these files before starting:
- `app/frontend/src/components/ResultsPanel.tsx` (638 lines)
- `app/backend/app/routes/analysis.py` (from Phase 0.2, or `main.py` if not done)
- `app/backend/app/services/calculations_service.py`
- `app/backend/app/schemas/api.py` — existing request/response models
- `app/backend/app/stats/binary.py`, `app/backend/app/stats/continuous.py`
- `app/frontend/src/lib/generated/api-contract.ts` — regenerate after adding new endpoint

Current problem: All analysis results are shown as text and numbers. No charts, no visual storytelling. Users see "146 642 users / variant" but can't understand trade-offs visually.

---

## Goal

1. Add `GET /api/v1/sensitivity` backend endpoint returning a matrix of {mde, power, sample_size, duration_days}
2. Add **Power Curve** chart (Recharts) in ResultsPanel
3. Add **Sensitivity Table** (MDE vs Duration matrix) in ResultsPanel
4. Add **Sample Size Breakdown Bar** (horizontal stacked bar) showing group sizes

---

## Steps

### Step 1: Install Recharts

```bash
cd app/frontend && npm install recharts
```

Verify: `recharts` added to `package.json`.

### Step 2: Backend — add `SensitivityRequest` and `SensitivityResponse` schemas

In `app/backend/app/schemas/api.py`, add:

```python
class SensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    metric_type: Literal["binary", "continuous"]
    baseline_rate: float | None = None        # binary
    baseline_mean: float | None = None        # continuous
    std_dev: float | None = None              # continuous
    variants: int = 2
    alpha: float = 0.05
    daily_traffic: float = 1000.0
    audience_share: float = 1.0
    traffic_split: list[float] | None = None
    
    # Range for the matrix
    mde_values: list[float] = Field(default=[0.1, 0.5, 1.0, 2.0, 5.0])   # % or absolute
    power_values: list[float] = Field(default=[0.7, 0.8, 0.9, 0.95])

class SensitivityCell(BaseModel):
    mde: float
    power: float
    sample_size_per_variant: int
    duration_days: float

class SensitivityResponse(BaseModel):
    cells: list[SensitivityCell]
    current_mde: float | None = None
    current_power: float | None = None
```

### Step 3: Backend — add `/api/v1/sensitivity` endpoint

In `app/backend/app/routes/analysis.py` (or `main.py`):

```python
@router.post("/api/v1/sensitivity", response_model=SensitivityResponse)
async def compute_sensitivity(request: SensitivityRequest, ...):
    cells = []
    for mde in request.mde_values:
        for power in request.power_values:
            if request.metric_type == "binary":
                n = calculate_binary_sample_size(
                    baseline_rate=request.baseline_rate / 100,
                    mde=mde / 100,
                    alpha=request.alpha,
                    power=power,
                    variants=request.variants,
                )
            else:
                n = calculate_continuous_sample_size(
                    baseline_mean=request.baseline_mean,
                    std_dev=request.std_dev,
                    mde=mde,
                    alpha=request.alpha,
                    power=power,
                    variants=request.variants,
                )
            duration = estimate_duration(n, request.daily_traffic, ...)
            cells.append(SensitivityCell(mde=mde, power=power, sample_size_per_variant=n, duration_days=duration))
    return SensitivityResponse(cells=cells)
```

Add a backend test in `app/backend/tests/test_api_routes.py`:
```python
def test_sensitivity_binary():
    resp = client.post("/api/v1/sensitivity", json={
        "metric_type": "binary",
        "baseline_rate": 3.5,
        "mde_values": [0.5, 1.0],
        "power_values": [0.8, 0.9],
        "daily_traffic": 10000,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["cells"]) == 4  # 2 mde × 2 power
    assert all("sample_size_per_variant" in c for c in data["cells"])
```

### Step 4: Add `sensitivity` to frontend API client

In `app/frontend/src/lib/api.ts`, add:
```typescript
sensitivity: (payload: SensitivityRequest): Promise<SensitivityResponse> =>
  post('/api/v1/sensitivity', payload),
```

Regenerate `api-contract.ts` if the generate script exists:
```bash
cd app/backend && python -m app.main  # (or the generate script)
python ../../scripts/generate_api_docs.py
```

### Step 5: Create `PowerCurveChart` component

Create `app/frontend/src/components/PowerCurveChart.tsx`:

```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';

interface PowerCurveChartProps {
  cells: SensitivityCell[];        // from sensitivity endpoint
  currentMde: number;
  currentPower: number;
}
```

Chart spec:
- X axis: MDE values (sorted)
- Y axis: Power (0 to 1, formatted as "80%")
- One line per `power_value` (4 lines: 70%, 80%, 90%, 95%)
- Highlight current configuration: `<ReferenceLine x={currentMde} stroke="var(--color-primary)" strokeDasharray="4 4" />`
- Target line at 80%: `<ReferenceLine y={0.8} stroke="var(--color-warning)" strokeDasharray="4 4" />`
- Tooltip: "MDE: 1.0% → 50 000 users / variant"

```tsx
<ResponsiveContainer width="100%" height={220}>
  <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
    <XAxis dataKey="mde" tickFormatter={v => `${v}%`} />
    <YAxis tickFormatter={v => `${(v * 100).toFixed(0)}%`} domain={[0.5, 1]} />
    <Tooltip formatter={(v: number) => `${(v * 100).toFixed(0)}%`} />
    <ReferenceLine y={0.8} strokeDasharray="4 4" stroke="var(--color-warning)" label="80% target" />
    {powerLevels.map(p => (
      <Line key={p} dataKey={`power_${p}`} stroke={colorForPower(p)} dot={false} strokeWidth={2} />
    ))}
    <ReferenceLine x={currentMde} stroke="var(--color-primary)" strokeDasharray="4 4" />
  </LineChart>
</ResponsiveContainer>
```

### Step 6: Create `SensitivityTable` component

Create `app/frontend/src/components/SensitivityTable.tsx`:

```tsx
interface SensitivityTableProps {
  cells: SensitivityCell[];
  currentMde: number;
  currentPower: number;
}
```

Renders a matrix table:
- Rows: MDE values
- Columns: Power levels (70%, 80%, 90%, 95%)
- Cells: duration in days
- Current config highlighted: `background: var(--color-primary-light); font-weight: 700;`
- Color scale: short duration → green, long duration → amber → red

```tsx
<table className="sensitivity-table">
  <thead>
    <tr>
      <th>MDE</th>
      {powerLevels.map(p => <th key={p}>{(p * 100).toFixed(0)}% power</th>)}
    </tr>
  </thead>
  <tbody>
    {mdeValues.map(mde => (
      <tr key={mde}>
        <td className="sensitivity-mde">{mde}%</td>
        {powerLevels.map(p => {
          const cell = findCell(cells, mde, p);
          const isCurrent = mde === currentMde && p === currentPower;
          return (
            <td key={p} className={`sensitivity-cell ${isCurrent ? 'current' : ''} ${durationClass(cell?.duration_days)}`}>
              {cell ? `${Math.ceil(cell.duration_days)}d` : '—'}
            </td>
          );
        })}
      </tr>
    ))}
  </tbody>
</table>
```

### Step 7: Create `SampleSizeBar` component

Create `app/frontend/src/components/SampleSizeBar.tsx`:

A horizontal stacked bar showing sample size per variant as colored segments.

```tsx
interface SampleSizeBarProps {
  sampleSizePerVariant: number;
  variants: number;
  variantNames?: string[];  // e.g., ["Control", "Treatment A", "Treatment B"]
  trafficSplit?: number[];  // percentages
}
```

Simple pure-CSS implementation (no Recharts needed):
```tsx
<div className="sample-size-bar-container">
  <div className="sample-size-bar">
    {variants.map((v, i) => (
      <div
        key={i}
        className="sample-size-segment"
        style={{ flex: trafficSplit?.[i] ?? 1, background: VARIANT_COLORS[i] }}
        title={`${v.name}: ${v.size.toLocaleString()} users`}
      />
    ))}
  </div>
  <div className="sample-size-labels">
    {variants.map((v, i) => (
      <div key={i} className="sample-size-label">
        <span className="label-swatch" style={{ background: VARIANT_COLORS[i] }} />
        <span>{v.name}: {v.size.toLocaleString()}</span>
      </div>
    ))}
  </div>
</div>
```

### Step 8: Wire charts into ResultsPanel

In `ResultsPanel.tsx`, after showing the metric cards:
1. Add section "Sensitivity analysis" with `<PowerCurveChart>` + `<SensitivityTable>`
2. Add section "Sample size breakdown" with `<SampleSizeBar>`
3. Fetch sensitivity data when analysis result is available:
   ```typescript
   useEffect(() => {
     if (analysisResult) fetchSensitivity(buildSensitivityPayload(draft, analysisResult));
   }, [analysisResult]);
   ```

---

## Verify

- [ ] `cd app/backend && python -m pytest tests/ -x -q` — all tests pass including new sensitivity test
- [ ] `npm run build` exits 0
- [ ] `npm test` passes
- [ ] `npx tsc --noEmit` exits 0
- [ ] After running analysis: power curve chart renders with 4 lines
- [ ] Current MDE shown as dashed vertical line
- [ ] Sensitivity table shows 20 cells (5 MDE × 4 power), current config highlighted
- [ ] Sample size bar shows colored segments for each variant
- [ ] Charts are responsive (resize browser window)
- [ ] Bundle size increase: run `npm run build` and check gzip output — should be < 130KB total JS

---

## Constraints

- Import only needed Recharts components (tree-shaking): `LineChart`, `Line`, `XAxis`, `YAxis`, etc.
- Do NOT import the entire recharts library
- `SensitivityTable` must be readable without JavaScript (no canvas) — pure HTML table
- Charts must work in dark mode (use CSS variables for colors, not hardcoded hex)
- The sensitivity endpoint is OPTIONAL — if it fails, ResultsPanel shows charts as "unavailable" without crashing
