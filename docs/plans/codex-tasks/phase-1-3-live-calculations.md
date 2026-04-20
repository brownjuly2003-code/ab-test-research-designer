# Task 1.3: Live calculation preview + MDE/Power sliders

**Phase:** 1 — UX transformation  
**Priority:** High  
**Depends on:** Phase 0.3 (payload.ts), Phase 0.1 (CSS tokens)  
**Effort:** ~5h

---

## Context

Read these files before starting:
- `app/frontend/src/components/WizardDraftStep.tsx` (wizard form)
- `app/frontend/src/lib/api.ts` — check `POST /api/v1/calculate` call signature
- `app/frontend/src/lib/payload.ts` (from Phase 0.3, or equivalent in `experiment.ts`)
- `app/backend/app/schemas/api.py` — `CalculateRequest` schema (understand required vs optional fields)

Current problem: User fills 6 wizard steps, then clicks "Run analysis", waits for a response.
Competitors (Statsig, Evan Miller) show instant recalculation when any parameter changes.
This is a **table-stakes feature** for an experiment planning tool.

---

## Goal

1. Add a live preview panel on wizard steps 3 (Setup) and 4 (Metrics) showing:
   - Required sample size per variant
   - Estimated duration in days
2. Replace the `mde` number input with a dual-control (slider + number input)
3. Replace the `power` number input with a dual-control (slider + number input)
4. Debounce preview calls at 300ms to avoid hammering the API

---

## Steps

### Step 1: Create `useCalculationPreview` hook

Create `app/frontend/src/hooks/useCalculationPreview.ts`:

```typescript
import { useState, useEffect, useRef, useCallback } from 'react';
import { ExperimentDraft, CalculationResult } from '../lib/types';
import { buildCalculatePayload } from '../lib/payload';
import { api } from '../lib/api';

interface PreviewState {
  result: CalculationResult | null;
  isLoading: boolean;
  error: string | null;
}

export function useCalculationPreview(draft: ExperimentDraft, enabled: boolean) {
  const [state, setState] = useState<PreviewState>({ result: null, isLoading: false, error: null });
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const compute = useCallback(async () => {
    // Don't call if required fields aren't filled
    if (!canCompute(draft)) return;

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setState(s => ({ ...s, isLoading: true, error: null }));

    try {
      const payload = buildCalculatePayload(draft);
      const result = await api.calculate(payload, { signal: abortRef.current.signal });
      setState({ result, isLoading: false, error: null });
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return;
      setState(s => ({ ...s, isLoading: false, error: 'Preview unavailable' }));
    }
  }, [draft]);

  useEffect(() => {
    if (!enabled) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(compute, 300);
    return () => { timerRef.current && clearTimeout(timerRef.current); };
  }, [compute, enabled]);

  return state;
}

function canCompute(draft: ExperimentDraft): boolean {
  // Require minimum fields to make a valid calculate request
  const m = draft.metrics;
  if (!m) return false;
  if (m.metric_type === 'binary') {
    return !!m.baseline_rate && !!m.mde && !!draft.setup?.daily_traffic;
  }
  if (m.metric_type === 'continuous') {
    return !!m.baseline_mean && !!m.mde_absolute && !!m.std_dev && !!draft.setup?.daily_traffic;
  }
  return false;
}
```

### Step 2: Create `LivePreviewPanel` component

Create `app/frontend/src/components/LivePreviewPanel.tsx`:

```tsx
interface LivePreviewPanelProps {
  result: CalculationResult | null;
  isLoading: boolean;
  error: string | null;
}
```

Display:
- If `isLoading`: show small spinner or pulsing skeleton
- If `error`: show "Preview unavailable" in muted text (non-intrusive)
- If `result`: show 2 metric cards side by side:
  - **Sample size per variant**: `{result.sample_size_per_variant.toLocaleString()}` users
  - **Estimated duration**: `{result.duration_days} days` (or "< 1 day" if very short)
  - If `result.bonferroni_note`: show small badge "Bonferroni correction applied"

Style: compact card, no border, muted background (`var(--color-bg-sidebar)`), sits below the active step fields.

```tsx
// Layout
<div className="live-preview-panel">
  <span className="live-preview-label">Live estimate</span>
  <div className="live-preview-cards">
    <div className="live-preview-card">
      <span className="preview-value">{formatNumber(result.sample_size_per_variant)}</span>
      <span className="preview-unit">users / variant</span>
    </div>
    <div className="live-preview-card">
      <span className="preview-value">{result.duration_days}</span>
      <span className="preview-unit">days</span>
    </div>
  </div>
  {result.bonferroni_note && <span className="preview-badge">Bonferroni applied</span>}
</div>
```

### Step 3: Create `SliderInput` component

Create `app/frontend/src/components/SliderInput.tsx`:

```tsx
interface SliderInputProps {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  unit?: string;        // display unit (%, pp, etc.)
  formatValue?: (v: number) => string;
}
```

Implementation: side-by-side `<input type="range">` and `<input type="number">` — both controlled, both update state on change.

```tsx
<div className="slider-input-group">
  <label htmlFor={id}>{label}</label>
  <div className="slider-input-controls">
    <input
      type="range"
      min={min} max={max} step={step}
      value={value}
      onChange={e => onChange(parseFloat(e.target.value))}
      aria-label={`${label} slider`}
    />
    <input
      id={id}
      type="number"
      min={min} max={max} step={step}
      value={value}
      onChange={e => onChange(parseFloat(e.target.value) || min)}
      className="slider-number-input"
    />
    {unit && <span className="slider-unit">{unit}</span>}
  </div>
</div>
```

### Step 4: Wire up in `WizardDraftStep.tsx`

In step 4 (Metrics):
- Replace `mde` plain `<input type="number">` with `<SliderInput id="mde" min={0.1} max={20} step={0.1} unit="pp" ...>`
  - For binary metrics: range 0.1–20 (percentage points)
  - For continuous metrics: range 0.1–50 (absolute units), or make it configurable

In step 5 (Constraints):
- Replace `power` plain `<input type="number">` with `<SliderInput id="power" min={0.7} max={0.99} step={0.01} ...>`
  - Show label as "Power: 80%" formatting

At the bottom of step 3 and step 4, add:
```tsx
<LivePreviewPanel
  result={previewState.result}
  isLoading={previewState.isLoading}
  error={previewState.error}
/>
```

Pass `useCalculationPreview(draft, currentStep >= 3)` to get the preview state.

### Step 5: Add CSS for new components

In `App.css` or a new module file:

```css
.live-preview-panel {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-sidebar);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}
.live-preview-label {
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}
.live-preview-cards {
  display: flex;
  gap: var(--space-4);
  margin-top: var(--space-2);
}
.preview-value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--color-primary);
}
.preview-unit {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}
.slider-input-controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.slider-number-input {
  width: 80px;
}
input[type="range"] {
  flex: 1;
  accent-color: var(--color-primary);
}
```

---

## Verify

- [ ] `npm run build` exits 0
- [ ] `npm test` passes all existing tests
- [ ] `npx tsc --noEmit` exits 0
- [ ] On step 3 or 4: changing `daily_traffic` → preview updates within 400ms
- [ ] Dragging MDE slider → number input updates in real time
- [ ] Typing in number input → slider moves to correct position
- [ ] Power slider: range 0.70–0.99, step 0.01
- [ ] Preview shows "Preview unavailable" gracefully when API is offline (no crash)
- [ ] `LivePreviewPanel` is not shown on steps 1, 2, 5 (only steps 3 and 4)
- [ ] New `useCalculationPreview.ts` hook file exists

---

## Constraints

- `canCompute()` must guard against incomplete drafts — never call the API with missing required fields
- The `AbortController` must cancel in-flight requests — no race conditions
- Do NOT remove the existing "Run analysis" button — live preview is additional, not a replacement
- `SliderInput` is uncontrolled-safe — handle NaN from empty number input (fallback to `min`)
- Do NOT change any backend code
