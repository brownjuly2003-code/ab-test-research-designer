# Task 1.4: Inline validation + toast system + keyboard shortcuts + confirmations

**Phase:** 1 — UX transformation  
**Priority:** High  
**Depends on:** Phase 0.3 (validation.ts)  
**Effort:** ~5h

---

## Context

Read these files before starting:
- `app/frontend/src/App.tsx`
- `app/frontend/src/components/WizardDraftStep.tsx`
- `app/frontend/src/components/WizardPanel.tsx`
- `app/frontend/src/lib/validation.ts` (from Phase 0.3, or `experiment.ts`)
- `app/frontend/src/hooks/useProjectManager.ts`

Current problems:
1. Validation runs only on "Next step" click or "Run analysis" — no inline feedback
2. Destructive actions (delete project) use `window.confirm()` — native browser dialog, jarring UX
3. Success events (save, export) have no confirmation feedback
4. No keyboard shortcuts — power users must use mouse for everything

---

## Goal

1. Inline validation: show field-level errors on blur + tab-level error indicators
2. Toast notification system: success/error/warning toasts with auto-dismiss
3. Replace `window.confirm()` with inline confirmation countdown
4. Keyboard shortcuts: Ctrl+S, Ctrl+Enter, Ctrl+E, ←/→ for wizard steps

---

## Steps

### Step 1: Create `ToastSystem` component

Create `app/frontend/src/components/ToastSystem.tsx`:

```typescript
interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  autoDismiss?: number; // ms, default 5000 for success, 0 (persistent) for error
}
```

Implementation:
- Toast stack positioned at bottom-right: `position: fixed; bottom: var(--space-5); right: var(--space-5); z-index: 1000;`
- Each toast: icon + message + close button
- CSS animation: `slideUp` on enter, fade on exit
- Auto-dismiss using `setTimeout` — errors are persistent (user must close)

```tsx
// Success toast style
background: var(--color-success-light);
border-left: 3px solid var(--color-success);
color: var(--color-text);

// Error toast style
background: var(--color-danger-light);
border-left: 3px solid var(--color-danger);

// Warning style
background: var(--color-warning-light);
border-left: 3px solid var(--color-warning);
```

Create a `useToast` hook:
```typescript
export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((type: Toast['type'], message: string, autoDismiss?: number) => {
    const id = crypto.randomUUID();
    setToasts(t => [...t, { id, type, message, autoDismiss }]);
    if (type !== 'error') {
      setTimeout(() => removeToast(id), autoDismiss ?? 5000);
    }
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts(t => t.filter(toast => toast.id !== id));
  }, []);

  return { toasts, addToast, removeToast };
}
```

Use `useToast` in `App.tsx` and pass `addToast` to hooks that need it.

**Trigger toasts for:**
- Project saved: `addToast('success', 'Project saved')`
- Project updated: `addToast('success', 'Project updated')`
- Export downloaded: `addToast('success', 'Report exported')`
- Workspace import success: `addToast('success', 'Workspace imported — N projects restored')`
- Analysis error: `addToast('error', error.message)`
- Save error: `addToast('error', 'Save failed — ' + error.message)`
- localStorage quota exceeded: `addToast('warning', 'Draft not saved — browser storage full')`

### Step 2: Inline validation on blur

In `WizardDraftStep.tsx`, add `fieldErrors: Record<string, string>` state.

For each input that has validation rules, add:
```tsx
onBlur={() => {
  const error = validateField('field_name', value);
  setFieldErrors(prev => ({ ...prev, field_name: error || '' }));
}}
```

Display errors inline:
```tsx
{fieldErrors.baseline_rate && (
  <span className="field-error" role="alert">{fieldErrors.baseline_rate}</span>
)}
```

Style:
```css
.field-error {
  color: var(--color-danger);
  font-size: var(--font-size-xs);
  margin-top: var(--space-1);
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
input.has-error {
  border-color: var(--color-danger);
  outline-color: var(--color-danger);
}
```

### Step 3: Tab error indicators in WizardPanel

In `WizardPanel.tsx`, add a dot indicator on the step tab when that step has validation errors:

```tsx
<button className={`wizard-tab ${hasErrors ? 'has-errors' : ''}`}>
  Step {n}
  {hasErrors && <span className="error-dot" aria-label="This step has errors" />}
</button>
```

```css
.error-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-danger);
  display: inline-block;
  margin-left: var(--space-1);
}
```

Pass `stepErrors: Record<number, boolean>` from `App.tsx` to `WizardPanel`.
Compute it from `fieldErrors` — map which step each field belongs to.

### Step 4: Inline confirmation (replace `window.confirm()`)

Find all `window.confirm()` calls in the codebase (likely in `SidebarPanel.tsx` and `useProjectManager.ts`).

Create an `InlineConfirmButton` component:

```tsx
interface InlineConfirmButtonProps {
  onConfirm: () => void;
  label: string;
  confirmLabel?: string;
  countdownSeconds?: number; // default 3
  variant?: 'danger' | 'warning';
}
```

Behavior:
1. First click: button changes to "Sure? (3)" and starts countdown
2. Countdown: "Sure? (2)", "Sure? (1)"
3. Click again during countdown OR wait for countdown to finish → `onConfirm()` called
4. Click elsewhere → cancel, return to original state
5. If countdown expires without second click → cancel

```tsx
function InlineConfirmButton({ onConfirm, label, countdownSeconds = 3 }: InlineConfirmButtonProps) {
  const [confirming, setConfirming] = useState(false);
  const [count, setCount] = useState(countdownSeconds);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startConfirm = () => {
    setConfirming(true);
    setCount(countdownSeconds);
    timerRef.current = setInterval(() => {
      setCount(c => {
        if (c <= 1) { cancel(); return 0; }
        return c - 1;
      });
    }, 1000);
  };

  const cancel = () => {
    setConfirming(false);
    setCount(countdownSeconds);
    if (timerRef.current) clearInterval(timerRef.current);
  };

  const confirm = () => {
    cancel();
    onConfirm();
  };

  return confirming
    ? <button onClick={confirm} className="confirm-btn danger">Sure? ({count})</button>
    : <button onClick={startConfirm}>{label}</button>;
}
```

Replace all `window.confirm('Are you sure...')` calls with `<InlineConfirmButton onConfirm={...} label="Delete" />`.

### Step 5: Keyboard shortcuts

In `App.tsx`, add a global `keydown` listener via `useEffect`:

```typescript
useEffect(() => {
  const handleKeyDown = (e: KeyboardEvent) => {
    const ctrl = e.ctrlKey || e.metaKey;
    if (!ctrl) return;

    switch (e.key) {
      case 's':
        e.preventDefault();
        if (!isReadOnly) handleSave();
        break;
      case 'Enter':
        e.preventDefault();
        if (!isReadOnly && isDraftComplete) handleRunAnalysis();
        break;
      case 'e':
        e.preventDefault();
        if (analysisResult) handleExport();
        break;
      case 'ArrowRight':
        e.preventDefault();
        if (currentStep < MAX_STEPS) setCurrentStep(s => s + 1);
        break;
      case 'ArrowLeft':
        e.preventDefault();
        if (currentStep > 1) setCurrentStep(s => s - 1);
        break;
    }
  };

  window.addEventListener('keydown', handleKeyDown);
  return () => window.removeEventListener('keydown', handleKeyDown);
}, [isReadOnly, isDraftComplete, analysisResult, currentStep, handleSave, handleRunAnalysis, handleExport]);
```

Show keyboard shortcuts in tooltips on buttons:
- "Save project (Ctrl+S)"
- "Run analysis (Ctrl+Enter)"
- "Export (Ctrl+E)"
- Navigate wizard with ← →

---

## Verify

- [ ] `npm run build` exits 0
- [ ] `npm test` passes all existing tests
- [ ] `npx tsc --noEmit` exits 0
- [ ] No `window.confirm()` calls remain — grep: `window.confirm` returns nothing
- [ ] Enter `-5` in baseline_rate field, tab away → red border + error message appears
- [ ] Save project → green toast "Project saved" appears and auto-dismisses in 5s
- [ ] Analysis fails → red persistent toast with error message
- [ ] Click "Delete" → shows "Sure? (3)" countdown
- [ ] Ctrl+S with unsaved draft → save triggered (if not read-only)
- [ ] ← / → → wizard step changes
- [ ] Toast stack shows multiple toasts without overlap

---

## Constraints

- Do NOT use any external toast library — implement from scratch
- `InlineConfirmButton` must cleanup timer on unmount (`useEffect` return)
- Keyboard shortcuts must check `isReadOnly` before destructive actions
- Do NOT break existing test coverage — inline errors are additional, not replacing existing validation
- Accessibility: toasts must have `role="alert"` for screen readers
