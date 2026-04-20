# Task 0.1: Design tokens + CSS Modules

**Phase:** 0 — Foundation  
**Priority:** Critical (prerequisite for all UI tasks)  
**Depends on:** nothing  
**Effort:** ~6h

---

## Context

Read these files before starting:
- `app/frontend/src/App.css` (939 lines — monolithic, all global styles)
- `app/frontend/src/components/` (all 12 component files — note class names they use)
- `app/frontend/src/App.tsx` (713 lines)
- `app/frontend/vite.config.ts`

Current problem: All 939 lines of CSS are global. No scoped styles. No formal token system.
Class names can conflict. Adding new components is risky.

---

## Goal

1. Extract CSS custom properties into a formal design token file `tokens.css`
2. Add a CSS reset file `reset.css`
3. Create CSS Module files for the 3 largest components (SidebarPanel, ResultsPanel, WizardPanel)
4. Add a secondary accent color (indigo `#4f46e5`) for navigation, keeping teal for primary actions
5. Keep `App.css` for global layout only (≤ 200 lines after extraction)

---

## Steps

### Step 1: Create `src/styles/tokens.css`

Create `app/frontend/src/styles/tokens.css` with this token system:

```css
:root {
  /* Spacing scale */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --space-8: 64px;

  /* Typography scale */
  --font-size-xs: 0.75rem;
  --font-size-sm: 0.875rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.125rem;
  --font-size-xl: 1.25rem;
  --font-size-2xl: 1.5rem;
  --font-size-3xl: clamp(1.5rem, 2.5vw, 2rem);

  /* Radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;

  /* Colors — primary (teal, for actions) */
  --color-primary: #0d9488;
  --color-primary-hover: #0f766e;
  --color-primary-light: #ccfbf1;

  /* Colors — secondary (indigo, for navigation/tabs) */
  --color-secondary: #4f46e5;
  --color-secondary-hover: #4338ca;
  --color-secondary-light: #e0e7ff;

  /* Colors — semantic */
  --color-danger: #ef4444;
  --color-danger-light: #fee2e2;
  --color-warning: #f59e0b;
  --color-warning-light: #fef3c7;
  --color-success: #10b981;
  --color-success-light: #d1fae5;
  --color-info: #3b82f6;
  --color-info-light: #dbeafe;

  /* Neutral palette */
  --color-bg: #f8fafc;
  --color-bg-card: #ffffff;
  --color-bg-sidebar: #f1f5f9;
  --color-border: #e2e8f0;
  --color-border-focus: var(--color-primary);
  --color-text: #1e293b;
  --color-text-secondary: #64748b;
  --color-text-muted: #94a3b8;

  /* Shadows / elevation */
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.05), 0 2px 4px rgba(0, 0, 0, 0.04);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.07), 0 4px 6px rgba(0, 0, 0, 0.05);

  /* Transitions */
  --transition-fast: 150ms ease;
  --transition-base: 200ms ease;
  --transition-slow: 300ms ease;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: #0f172a;
    --color-bg-card: #1e293b;
    --color-bg-sidebar: #162032;
    --color-border: #334155;
    --color-text: #f1f5f9;
    --color-text-secondary: #94a3b8;
    --color-text-muted: #64748b;
    --color-primary-light: #134e4a;
    --color-secondary-light: #1e1b4b;
  }
}
```

### Step 2: Create `src/styles/reset.css`

Create `app/frontend/src/styles/reset.css`:

```css
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  -webkit-text-size-adjust: 100%;
  scroll-behavior: smooth;
}

body {
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

img, picture, video, canvas, svg {
  display: block;
  max-width: 100%;
}

input, button, textarea, select {
  font: inherit;
}

p, h1, h2, h3, h4, h5, h6 {
  overflow-wrap: break-word;
}
```

### Step 3: Update `src/main.tsx` imports

Ensure `main.tsx` imports in this order:
```tsx
import './styles/reset.css';
import './styles/tokens.css';
import './App.css';
```

### Step 4: Create CSS Module for SidebarPanel

Create `app/frontend/src/components/SidebarPanel.module.css`.
Move all CSS rules from `App.css` that match selectors starting with `.sidebar`, `.sidebar-*`, `.project-*`, `.history-*`, `.diagnostics-*`, `.workspace-*`, `.status-board-*` into this module.
Replace class names in `SidebarPanel.tsx` with module references: `styles.sidebar`, etc.

### Step 5: Create CSS Module for ResultsPanel

Create `app/frontend/src/components/ResultsPanel.module.css`.
Move all CSS from `App.css` matching `.results-*`, `.metric-card-*`, `.report-*`, `.ai-advice-*`, `.warning-*`, `.comparison-*`.
Update `ResultsPanel.tsx` to use `import styles from './ResultsPanel.module.css'`.

### Step 6: Create CSS Module for WizardPanel area

Create `app/frontend/src/components/WizardDraftStep.module.css`.
Move `.wizard-*`, `.step-*`, `.form-group`, `.form-row`, `.field-*`, `.constraint-*`, `.metric-input-*` rules.
Update `WizardDraftStep.tsx`, `WizardPanel.tsx`, `WizardReviewStep.tsx` accordingly.

### Step 7: Update App.css

After extraction, `App.css` should contain only:
- Global layout (`.app`, `.main-content`, `.content-area`)
- Typography base (body, font imports)
- Global button and input base styles (not component-specific)
- Animation keyframes (`@keyframes fadeSlideIn`, `slideUp`, `spin`, `pulse`)
- Print styles

Target: ≤ 250 lines remaining in `App.css`.

### Step 8: Update teal → use token, add indigo for navigation

In `App.css` and the new module files:
- Replace all hardcoded `#0d9488` / `#0f766e` with `var(--color-primary)` / `var(--color-primary-hover)`
- Find wizard step tabs / navigation elements — change their active/hover color from teal to `var(--color-secondary)` (indigo)
- Keep teal (`var(--color-primary)`) for: primary buttons (Run analysis, Save, Export)

---

## Verify

- [ ] `npm run build` in `app/frontend/` exits 0
- [ ] `npm test` (vitest) passes all 64 tests
- [ ] `npx tsc --noEmit` exits 0
- [ ] `App.css` is ≤ 250 lines
- [ ] `tokens.css` exists with full token set
- [ ] Primary action buttons are teal, wizard navigation tabs are indigo
- [ ] No hardcoded hex color `#0d9488` remains in CSS files (replaced by token)
- [ ] No visual regressions visible on `npm run dev` in browser

---

## Constraints

- Do NOT change any HTML structure or component logic — CSS only
- Do NOT introduce any new runtime JS libraries
- Keep all existing class names working (module local names must match what the component uses)
- Do NOT remove dark mode support — it must work via the new token system
- If a CSS rule is used in more than one component, keep it in `App.css` (global), not in a module
