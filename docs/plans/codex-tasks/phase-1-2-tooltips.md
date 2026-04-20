# Task 1.2: Floating UI tooltips on all numeric fields

**Phase:** 1 — UX transformation  
**Priority:** High  
**Depends on:** Phase 0.1 (CSS tokens), Phase 0.3 (field-config.ts)  
**Effort:** ~3h

---

## Context

Read these files before starting:
- `app/frontend/src/components/Tooltip.tsx` (14 lines — CSS `::after` based, broken at screen edges)
- `app/frontend/src/components/WizardDraftStep.tsx` (214 lines — the main form component)
- `app/frontend/src/lib/field-config.ts` (created in Phase 0.3, or `experiment.ts` if Phase 0.3 not done)
- `app/frontend/src/styles/tokens.css` (created in Phase 0.1, or `App.css` if not done)

Current problems:
1. `Tooltip.tsx` uses CSS `::after` pseudo-element — clips at screen edges, can't overflow sidebar
2. No tooltip text exists for the 8+ numeric fields that require statistical knowledge
3. Users see `baseline_rate`, `mde`, `std_dev` with no explanation of what to enter

---

## Goal

1. Replace CSS-based `Tooltip.tsx` with a portal-based Floating UI implementation
2. Add tooltip text for every numeric field in the wizard form
3. Show tooltip on hover AND on focus (keyboard accessibility)

---

## Steps

### Step 1: Install Floating UI

```bash
cd app/frontend && npm install @floating-ui/react-dom
```

Verify it's in `package.json` dependencies.

### Step 2: Rewrite `Tooltip.tsx`

Replace the entire `Tooltip.tsx` with a portal-based implementation:

```tsx
import { useState, useRef } from 'react';
import { useFloating, offset, flip, shift, autoUpdate } from '@floating-ui/react-dom';
import { createPortal } from 'react-dom';

interface TooltipProps {
  content: string;
  children: React.ReactElement;
  placement?: 'top' | 'bottom' | 'right' | 'left';
}

export function Tooltip({ content, children, placement = 'top' }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const { refs, floatingStyles } = useFloating({
    placement,
    middleware: [offset(8), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });

  return (
    <>
      {React.cloneElement(children, {
        ref: refs.setReference,
        onMouseEnter: () => setIsVisible(true),
        onMouseLeave: () => setIsVisible(false),
        onFocus: () => setIsVisible(true),
        onBlur: () => setIsVisible(false),
        'aria-describedby': isVisible ? 'tooltip' : undefined,
      })}
      {isVisible && createPortal(
        <div
          id="tooltip"
          role="tooltip"
          ref={refs.setFloating}
          style={floatingStyles}
          className="tooltip-popup"
        >
          {content}
        </div>,
        document.body
      )}
    </>
  );
}
```

Add `.tooltip-popup` styles in `App.css` (or `tokens.css`):
```css
.tooltip-popup {
  background: var(--color-text);
  color: var(--color-bg-card);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  max-width: 280px;
  line-height: 1.4;
  z-index: 9999;
  pointer-events: none;
  white-space: normal;
}
```

### Step 3: Create tooltip content for all fields

In `app/frontend/src/lib/field-config.ts` (or `experiment.ts`), add a `FIELD_TOOLTIPS` export:

```typescript
export const FIELD_TOOLTIPS: Record<string, string> = {
  baseline_rate: 'Current conversion rate before the experiment. Example: 3.5 for 3.5% checkout conversion.',
  mde: 'Minimum Detectable Effect — the smallest change worth detecting. Example: 0.5 pp means detecting 3.5% → 4.0%.',
  alpha: 'Significance threshold. 0.05 means accepting 5% probability of a false positive result.',
  power: 'Probability of detecting a real effect. 0.8 (80%) is the standard minimum.',
  daily_traffic: 'Average number of unique users/sessions per day entering the experiment. Example: 10 000.',
  audience_share: 'Fraction of daily traffic included in the experiment. 1.0 = 100% of traffic.',
  traffic_split: 'Traffic share per variant. For 2 variants: [50, 50]. For 3: [34, 33, 33]. Must sum to 100.',
  std_dev: 'Standard deviation of the metric (for continuous metrics only). Example: 12.5 for average order value.',
  baseline_mean: 'Current average value of the metric before the experiment. Example: 45.20 for average order value in USD.',
  mde_absolute: 'Minimum change in absolute units you want to detect. Example: 2.0 means detecting a change of ≥2 in the metric value.',
  variants: 'Number of test variants including control. 2 = A/B test. 3+ = multivariate (requires Bonferroni correction).',
  duration_cap: 'Maximum number of days to run the experiment. Example: 28 to limit to 4 weeks.',
};
```

### Step 4: Wrap field labels with `<Tooltip>` in `WizardDraftStep.tsx`

For each numeric input in the form, wrap the `<label>` element (or add an info icon next to it) with `<Tooltip content={FIELD_TOOLTIPS['field_name']}`.

Pattern to use:
```tsx
import { Tooltip } from './Tooltip';
import { FIELD_TOOLTIPS } from '../lib/field-config';

// In JSX:
<div className="form-group">
  <label htmlFor="baseline_rate">
    Baseline rate (%)
    <Tooltip content={FIELD_TOOLTIPS.baseline_rate}>
      <span className="field-info-icon" aria-label="More info" tabIndex={0}>ⓘ</span>
    </Tooltip>
  </label>
  <input id="baseline_rate" type="number" ... />
</div>
```

Add `.field-info-icon` style:
```css
.field-info-icon {
  display: inline-flex;
  align-items: center;
  margin-left: var(--space-1);
  color: var(--color-text-muted);
  cursor: help;
  font-size: var(--font-size-sm);
}
.field-info-icon:hover, .field-info-icon:focus {
  color: var(--color-primary);
  outline: none;
}
```

Apply tooltips to ALL of these fields:
- Step 2 (Hypothesis): no numeric fields
- Step 3 (Setup): `variants`, `daily_traffic`, `audience_share`, `traffic_split[]`
- Step 4 (Metrics): `baseline_rate` / `baseline_mean`, `mde`, `std_dev`, `mde_absolute`
- Step 5 (Constraints): `alpha`, `power`, `duration_cap`

---

## Verify

- [ ] `npm install` runs without errors (Floating UI added)
- [ ] `npm run build` exits 0
- [ ] `npm test` passes all 64 tests
- [ ] `npx tsc --noEmit` exits 0
- [ ] Hovering over the ⓘ icon on `baseline_rate` field shows tooltip with example text
- [ ] Tooltip near the right edge of sidebar does NOT clip — it flips to the other side
- [ ] Tooltip is visible on keyboard focus (Tab to ⓘ icon → tooltip appears)
- [ ] All 11+ fields listed in FIELD_TOOLTIPS have a corresponding ⓘ icon in the form

---

## Constraints

- Keep existing `Tooltip.tsx` API (`content` prop) — only change the implementation
- Do NOT break existing usages of `<Tooltip>` in other components (check all usages first)
- The info icon must not be a focusable button if it contains no action — use `tabIndex={0}` with `role="img"` or `role="note"`
- Bundle size increase should be < 8KB gzip (Floating UI is ~3KB gzip)
