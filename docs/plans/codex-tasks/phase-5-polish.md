# Task 5: A11y audit + i18n infrastructure + Lighthouse CI

**Phase:** 5 — Polish and go-to-market  
**Priority:** Medium  
**Depends on:** All previous phases  
**Effort:** ~6h

---

## Context

Read these files before starting:
- `app/frontend/src/components/Accordion.tsx` (40 lines)
- `app/frontend/src/components/WizardPanel.tsx` (142 lines)
- `app/frontend/src/App.tsx`
- `.github/workflows/test.yml`
- `app/frontend/package.json`

Current a11y issues (from `archive/2026-03-08-legacy-loose-docs/rec.md`):
- Accordion missing `aria-expanded` and `aria-controls`
- Wizard step changes don't move focus to new content
- No skip-to-content link

---

## Goal

1. Fix all identified accessibility issues (WCAG AA compliance)
2. Extract all UI strings to `src/i18n/en.json` (i18n infrastructure without translation)
3. Add Lighthouse CI to GitHub Actions
4. Verify: axe-core audit shows 0 critical violations

---

## Steps

### Step 1: Fix Accordion accessibility

In `app/frontend/src/components/Accordion.tsx`:

```tsx
// BEFORE: button without aria state
<button onClick={toggle} className="accordion-toggle">
  {title}
</button>

// AFTER: proper ARIA
<button
  onClick={toggle}
  className="accordion-toggle"
  aria-expanded={isOpen}
  aria-controls={panelId}
  id={headingId}
>
  {title}
  <Icon name="chevron-right" className={`accordion-icon ${isOpen ? 'rotated' : ''}`} aria-hidden={true} />
</button>
<div
  id={panelId}
  role="region"
  aria-labelledby={headingId}
  hidden={!isOpen}
  className="accordion-body"
>
  {children}
</div>
```

Generate stable IDs: `const id = useId()` (React 18+), then:
- `headingId = \`accordion-heading-${id}\``
- `panelId = \`accordion-panel-${id}\``

Fix the CSS transition to not use `max-height: 2200px` (hardcoded max-height causes uneven animation):

```css
/* Replace max-height animation with grid approach */
.accordion-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows var(--transition-base);
  overflow: hidden;
}
.accordion-body:not([hidden]) {
  grid-template-rows: 1fr;
}
.accordion-body > * {
  overflow: hidden;
}
```

Remove `hidden` attribute approach if it conflicts — use `aria-hidden` + CSS visibility instead:
```tsx
<div
  id={panelId}
  role="region"
  aria-labelledby={headingId}
  aria-hidden={!isOpen}
  className={`accordion-body ${isOpen ? 'open' : ''}`}
>
```

### Step 2: Focus management in wizard

In `WizardPanel.tsx` or `App.tsx`, add focus management when the step changes:

```typescript
const stepHeadingRef = useRef<HTMLHeadingElement>(null);

useEffect(() => {
  // When step changes, move focus to the heading of the new step
  if (stepHeadingRef.current) {
    stepHeadingRef.current.focus();
  }
}, [currentStep]);
```

In `WizardDraftStep.tsx`, add `ref={stepHeadingRef}` and `tabIndex={-1}` to the step heading:
```tsx
<h2 ref={stepHeadingRef} tabIndex={-1} className="step-heading">
  Step {currentStep}: {WIZARD_STEPS[currentStep - 1].label}
</h2>
```

`tabIndex={-1}` allows programmatic focus without adding to the tab order.

### Step 3: Skip-to-content link

In `App.tsx`, add a skip link as the very first element in the DOM:

```tsx
<a href="#main-content" className="skip-link">Skip to main content</a>
<div id="main-content" tabIndex={-1}>
  {/* main app content */}
</div>
```

CSS:
```css
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  background: var(--color-primary);
  color: white;
  padding: var(--space-2) var(--space-4);
  z-index: 100;
  text-decoration: none;
  border-radius: 0 0 var(--radius-sm) 0;
  transition: top var(--transition-fast);
}
.skip-link:focus {
  top: 0;
}
```

### Step 4: Color contrast audit

Check all text/background combinations for WCAG AA compliance (4.5:1 for normal text, 3:1 for large text):

Key pairs to verify (use browser DevTools accessibility panel or https://coolors.co/contrast-checker):
- `--color-text` (#1e293b) on `--color-bg` (#f8fafc): should be > 10:1 ✓
- `--color-text-secondary` (#64748b) on `--color-bg-card` (#ffffff): check ~ 4.5:1
- `--color-text-muted` (#94a3b8) — may fail; if so, darken to #6b7f94

If `--color-text-muted` fails WCAG AA: update the token to a darker value.
Do NOT use `--color-text-muted` for meaningful text — only for decorative labels.

### Step 5: Extract strings to i18n

Create `app/frontend/src/i18n/en.json`:

```json
{
  "app": {
    "title": "AB Test Research Designer",
    "tagline": "Deterministic calculations. Local-first. No cloud required."
  },
  "wizard": {
    "steps": {
      "1": "Project",
      "2": "Hypothesis",
      "3": "Setup",
      "4": "Metrics",
      "5": "Constraints",
      "6": "Review"
    },
    "actions": {
      "next": "Next",
      "back": "Back",
      "save": "Save project",
      "runAnalysis": "Run analysis",
      "export": "Export"
    }
  },
  "empty_state": {
    "title": "Plan your A/B experiment",
    "subtitle": "Deterministic calculations. Local-first. No cloud required.",
    "new_experiment": "New experiment",
    "load_example": "Load example",
    "import_project": "Import project"
  },
  "sidebar": {
    "tabs": {
      "projects": "Projects",
      "system": "System"
    },
    "actions": {
      "export_workspace": "Export workspace",
      "import_workspace": "Import workspace",
      "compare": "Compare projects"
    }
  },
  "results": {
    "sample_size_per_variant": "Users / variant",
    "duration_days": "Days estimated",
    "total_sample_size": "Total sample",
    "warnings": "Warnings",
    "ai_advice": "AI recommendations",
    "srm_check": "SRM Check",
    "sequential_design": "Sequential design",
    "guardrail_metrics": "Guardrail metrics",
    "actual_results": "Actual experiment results"
  },
  "errors": {
    "analysis_failed": "Analysis failed",
    "save_failed": "Save failed",
    "load_failed": "Failed to load project",
    "backend_offline": "Backend is offline",
    "storage_full": "Browser storage is full — draft not saved"
  },
  "toasts": {
    "project_saved": "Project saved",
    "project_updated": "Project updated",
    "export_success": "Report exported",
    "import_success": "Workspace imported — {count} projects restored",
    "example_loaded": "Example loaded — click Run analysis to see results"
  }
}
```

Create `app/frontend/src/i18n/index.ts`:

```typescript
import en from './en.json';

type DeepPartial<T> = { [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K] };

const translations = en;

export function t(key: string, vars?: Record<string, string | number>): string {
  const parts = key.split('.');
  let value: unknown = translations;
  for (const part of parts) {
    value = (value as Record<string, unknown>)[part];
    if (value === undefined) return key; // fallback: return key
  }
  if (typeof value !== 'string') return key;
  if (vars) {
    return value.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`));
  }
  return value;
}
```

**Do NOT replace hardcoded strings in the UI yet.** This task only creates the infrastructure. String replacement is a separate task if needed.

### Step 6: Add axe-core to frontend tests

Install `@axe-core/react` for development testing:

```bash
cd app/frontend && npm install --save-dev @axe-core/axe-core jest-axe
```

Or use `vitest-axe` if compatible. Add a smoke a11y test:

In `app/frontend/src/App.test.tsx`, add:
```typescript
import { axe, toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

it('has no critical accessibility violations on initial render', async () => {
  const { container } = render(<App />);
  const results = await axe(container, {
    runOnly: {
      type: 'rule',
      values: ['button-name', 'label', 'aria-required-attr', 'color-contrast'],
    },
  });
  expect(results).toHaveNoViolations();
});
```

### Step 7: Add Lighthouse CI to GitHub Actions

In `.github/workflows/test.yml`, add a Lighthouse CI job (Ubuntu only):

```yaml
lighthouse:
  name: Lighthouse CI
  runs-on: ubuntu-latest
  needs: [frontend-checks]   # depends on frontend build
  steps:
    - uses: actions/checkout@v4
    
    - uses: actions/setup-node@v4
      with:
        node-version: '22'
    
    - name: Install frontend deps
      run: cd app/frontend && npm ci
    
    - name: Build frontend
      run: cd app/frontend && npm run build
    
    - name: Install Lighthouse CI
      run: npm install -g @lhci/cli
    
    - name: Run Lighthouse CI
      run: |
        # Start a static server to serve the built frontend
        cd app/frontend && npx serve dist --port 3000 &
        sleep 3
        lhci autorun --config=.lighthouserc.json
```

Create `.lighthouserc.json` at repo root:
```json
{
  "ci": {
    "collect": {
      "url": ["http://localhost:3000"],
      "numberOfRuns": 1,
      "settings": {
        "preset": "desktop"
      }
    },
    "assert": {
      "assertions": {
        "categories:performance": ["warn", {"minScore": 0.85}],
        "categories:accessibility": ["error", {"minScore": 0.90}],
        "categories:best-practices": ["warn", {"minScore": 0.90}],
        "categories:seo": ["warn", {"minScore": 0.80}]
      }
    },
    "upload": {
      "target": "temporary-public-storage"
    }
  }
}
```

---

## Verify

- [ ] `npm test` passes all tests including new axe test
- [ ] `npm run build` exits 0
- [ ] Browser DevTools Accessibility panel: 0 critical violations on app load
- [ ] Tab through wizard form: focus moves visibly through all controls in logical order
- [ ] Keyboard: Tab to "Skip to content" link (first Tab press), Enter → focus jumps to main content
- [ ] Step change in wizard: focus moves to the new step heading
- [ ] Accordion toggle: `aria-expanded` changes between `true`/`false` in DOM inspector
- [ ] `src/i18n/en.json` exists with all string categories
- [ ] `src/i18n/index.ts` exists with `t()` function
- [ ] `.lighthouserc.json` exists at repo root
- [ ] GitHub Actions: `lighthouse` job appears in CI (may be skipped on this commit but defined)

---

## Constraints

- Do NOT run Lighthouse on every PR if it's slow — gate it on `workflow_dispatch` or `push to main` only
- The `t()` function must gracefully return the key string for unknown keys (never throws)
- `@axe-core` is devDependency only — not included in production bundle
- Focus management `useEffect` must have `currentStep` in dependency array — no stale closure
- Color contrast fix: if you darken `--color-text-muted`, verify it doesn't break any existing designs visually
