# Task 2.2: Visual polish — elevation, skeletons, micro-interactions, dark mode toggle

**Phase:** 2 — Visual transformation  
**Priority:** Medium  
**Depends on:** Phase 0.1 (CSS tokens)  
**Effort:** ~4h

---

## Context

Read these files before starting:
- `app/frontend/src/App.css` (or CSS modules from Phase 0.1)
- `app/frontend/src/components/MetricCard.tsx` (38 lines)
- `app/frontend/src/components/Spinner.tsx` (16 lines)
- `app/frontend/src/App.tsx` (look for dark mode handling)

Current problem:
- All UI elements appear on the same visual "layer" — no depth or separation
- Loading states use a single spinner for everything (layout shift, no preview of content shape)
- Dark mode is CSS-only via `prefers-color-scheme` — user cannot override manually
- Button click and card hover have no physical feedback

---

## Goal

1. Add subtle elevation (box-shadow) to cards, wizard panel, sidebar
2. Replace spinner with skeleton loading screens for project list and results panel
3. Add micro-interactions: button press, card hover lift
4. Add dark mode toggle (light / dark / system) in the app header

---

## Steps

### Step 1: Add elevation to key elements

In CSS (tokens or App.css), update:

```css
/* Metric cards — lift on hover */
.metric-card {
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition-base), box-shadow var(--transition-base);
}
.metric-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

/* Wizard panel — elevated above sidebar */
.wizard-panel, .content-area {
  box-shadow: var(--shadow-md);
}

/* Sidebar — slightly recessed */
.sidebar {
  box-shadow: inset -1px 0 0 var(--color-border);
}

/* Result panel sections — card-like separation */
.results-section {
  box-shadow: var(--shadow-sm);
  border-radius: var(--radius-md);
  background: var(--color-bg-card);
}
```

### Step 2: Create `Skeleton` component

Create `app/frontend/src/components/Skeleton.tsx`:

```tsx
interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string;
  className?: string;
}

export function Skeleton({ width = '100%', height = '1rem', borderRadius = '4px', className }: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className ?? ''}`}
      style={{ width, height, borderRadius }}
      aria-hidden="true"
    />
  );
}
```

CSS animation:
```css
.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-border) 25%,
    var(--color-bg-sidebar) 50%,
    var(--color-border) 75%
  );
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

@keyframes skeleton-pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

### Step 3: Create `ProjectListSkeleton` component

Create `app/frontend/src/components/ProjectListSkeleton.tsx`:

```tsx
export function ProjectListSkeleton() {
  return (
    <div className="project-list-skeleton">
      {[1, 2, 3].map(i => (
        <div key={i} className="project-skeleton-item">
          <Skeleton height="1rem" width="70%" />
          <Skeleton height="0.75rem" width="40%" />
        </div>
      ))}
    </div>
  );
}
```

Use in `SidebarPanel.tsx`: show `<ProjectListSkeleton>` when `isLoadingProjects` is true, instead of nothing or a spinner.

### Step 4: Create `ResultsSkeleton` component

Create `app/frontend/src/components/ResultsSkeleton.tsx`:

```tsx
export function ResultsSkeleton() {
  return (
    <div className="results-skeleton">
      {/* Metric cards row */}
      <div className="metric-cards-skeleton">
        {[1, 2, 3].map(i => (
          <div key={i} className="metric-card-skeleton">
            <Skeleton height="2.5rem" width="60%" />
            <Skeleton height="0.875rem" width="80%" />
          </div>
        ))}
      </div>
      {/* Chart placeholder */}
      <div className="chart-skeleton">
        <Skeleton height="220px" borderRadius="8px" />
      </div>
      {/* Table placeholder */}
      <div className="table-skeleton">
        <Skeleton height="160px" borderRadius="8px" />
      </div>
    </div>
  );
}
```

Use in `ResultsPanel.tsx`: show `<ResultsSkeleton>` when `isAnalyzing` is true.

### Step 5: Add micro-interactions

In CSS:

```css
/* Button press feedback */
button:not(:disabled):active {
  transform: scale(0.97);
  transition: transform 80ms ease;
}

/* Primary button — explicit */
.btn-primary:not(:disabled):active {
  transform: scale(0.97);
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

/* Success state checkmark animation */
.btn-success-state {
  color: var(--color-success);
}
.btn-success-state::before {
  content: '✓ ';
  animation: fadeSlideIn 200ms ease;
}

/* Project item hover */
.project-item:hover {
  background: var(--color-bg-sidebar);
  transform: translateX(2px);
  transition: transform var(--transition-fast), background var(--transition-fast);
}
```

### Step 6: Dark mode toggle

Add a theme toggle to the app header/top bar.

Three states: `'light' | 'dark' | 'system'`

```typescript
// In App.tsx or a new useTheme hook
type Theme = 'light' | 'dark' | 'system';

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    return (localStorage.getItem('theme') as Theme) ?? 'system';
  });

  useEffect(() => {
    const root = document.documentElement;
    localStorage.setItem('theme', theme);
    
    if (theme === 'system') {
      root.removeAttribute('data-theme');
    } else {
      root.setAttribute('data-theme', theme);
    }
  }, [theme]);

  return { theme, setTheme };
}
```

In CSS, update the dark mode query to also support `[data-theme="dark"]`:

```css
@media (prefers-color-scheme: dark) {
  :root { /* dark vars */ }
}
[data-theme="dark"] {
  /* same dark vars — manual override */
  --color-bg: #0f172a;
  /* ... all dark tokens ... */
}
[data-theme="light"] {
  /* force light even if system is dark */
  --color-bg: #f8fafc;
  /* ... all light tokens ... */
}
```

Add toggle UI in the app header:
```tsx
<div className="theme-toggle">
  <button
    onClick={() => setTheme('light')}
    className={theme === 'light' ? 'active' : ''}
    aria-label="Light mode"
    title="Light"
  >☀</button>
  <button
    onClick={() => setTheme('dark')}
    className={theme === 'dark' ? 'active' : ''}
    aria-label="Dark mode"
    title="Dark"
  >◐</button>
  <button
    onClick={() => setTheme('system')}
    className={theme === 'system' ? 'active' : ''}
    aria-label="System theme"
    title="System"
  >⊕</button>
</div>
```

---

## Verify

- [ ] `npm run build` exits 0
- [ ] `npm test` passes
- [ ] `npx tsc --noEmit` exits 0
- [ ] Loading projects: skeleton cards appear, not blank or spinner
- [ ] Running analysis: results skeleton shown during loading
- [ ] Metric cards lift visually on hover (translateY)
- [ ] Clicking any primary button: slight scale-down then release
- [ ] Dark mode toggle in header: clicking cycles through light/dark/system
- [ ] Theme preference persists after page reload
- [ ] Dark mode still works via system preference when toggle is on "system"

---

## Constraints

- Skeletons are `aria-hidden="true"` — screen readers don't read them
- The `data-theme` attribute approach must not break existing `@media (prefers-color-scheme: dark)` CSS
- Micro-interactions must NOT apply when `prefers-reduced-motion: reduce` is set:
  ```css
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition: none !important; animation: none !important; }
  }
  ```
- Do NOT add new npm dependencies (pure CSS + minimal JS)
