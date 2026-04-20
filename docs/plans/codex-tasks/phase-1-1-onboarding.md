# Task 1.1: Onboarding + sidebar redesign

**Phase:** 1 — UX transformation  
**Priority:** High  
**Depends on:** Phase 0.1 (CSS tokens), Phase 0.3 (App.tsx refactor)  
**Effort:** ~4h

---

## Context

Read these files before starting:
- `app/frontend/src/App.tsx`
- `app/frontend/src/components/SidebarPanel.tsx` (881 lines)
- `app/frontend/src/hooks/useProjectManager.ts`
- `docs/demo/sample-project.json` (the demo payload to load)
- `app/frontend/src/lib/api.ts` (check how projects are loaded)

Current problem:
- New user sees empty form with no guidance
- Sidebar shows SQLite pragmas, rate limiter counters, uptime stats by default
- "How this UI is split" explanation is dev-facing documentation, not user content
- 80% of sidebar content is technical noise irrelevant to a first-time user

---

## Goal

1. Add an empty state "hero screen" shown when no draft is in progress and no project is loaded
2. Redesign sidebar into 2 tabs: **"Projects"** (default) and **"System"** (diagnostics, moved here)
3. Hide all technical details (SQLite pragmas, rate limiter, uptime, runtime counters) behind the System tab
4. Add "Load example" button that imports `docs/demo/sample-project.json` in one click

---

## Steps

### Step 1: Create `EmptyState` component

Create `app/frontend/src/components/EmptyState.tsx`:

```tsx
interface EmptyStateProps {
  onNewExperiment: () => void;
  onLoadExample: () => void;
  onImportProject: () => void;
}
```

Renders a centered card with:
- Title: "Plan your A/B experiment"
- Subtitle: "Deterministic calculations. Local-first. No cloud required."
- Three action cards in a row:
  1. **New experiment** — "Start from scratch" → calls `onNewExperiment`
  2. **Load example** — "See a filled experiment in 1 click" → calls `onLoadExample`  
  3. **Import project** — "Restore from a workspace backup" → calls `onImportProject`

The component is shown when: `isEmptyState === true` (no draft content AND no active project).

### Step 2: Add "Load example" logic

In `useProjectManager` (or `App.tsx`), add `loadExample()` action:
1. Fetch `docs/demo/sample-project.json` — use a static import or `fetch('/demo/sample-project.json')`
2. The JSON contains an experiment draft payload — parse it and call `updateDraft()` to fill the form
3. Navigate to step 1 of the wizard (so user sees the filled form)
4. Show a success toast: "Example loaded — click Run analysis to see results"

Note: The example loads the draft only — it does NOT save a project. User can see results without saving.

### Step 3: Redesign SidebarPanel into 2 tabs

Add a tab bar at the top of `SidebarPanel.tsx`:

```
[ Projects ]  [ System ]
```

**Projects tab** (default active) shows:
- Active project info (name, last saved, dirty indicator)
- Project list with search/filter
- Project history (analysis runs timeline)
- Workspace export/import actions
- Compare projects button

**System tab** shows (everything currently shown by default that is technical):
- Backend health status card
- API token configuration
- Runtime diagnostics (SQLite pragmas, WAL mode, busy timeout)
- Rate limiter stats
- Request counters (total requests, error counts)
- Workspace status board (project/snapshot/revision counts)
- Uptime display

Implementation: add `activeTab: 'projects' | 'system'` state in SidebarPanel.
Use `var(--color-secondary)` (indigo) for the active tab indicator.

### Step 4: Remove developer documentation from sidebar

Remove (or hide in System tab) the section that explains "How this UI is split" / architecture description. This is dev documentation, not user content.

### Step 5: Update `App.tsx` to show EmptyState

Add `isEmptyState` computation:
```typescript
const isEmptyState = !isDirty && !activeProject && currentStep === 1;
```

When `isEmptyState` is true, render `<EmptyState>` instead of `<WizardDraftStep>`.

When user clicks "New experiment" — set `isEmptyState` to false, show wizard at step 1.
When user clicks "Load example" — call `loadExample()`, navigate to filled wizard.

---

## Verify

- [ ] `npm run build` exits 0
- [ ] `npm test` — all existing tests pass
- [ ] New user flow: open app → EmptyState shown → click "Load example" → wizard shows pre-filled form
- [ ] Sidebar has 2 tabs, "Projects" is active by default
- [ ] SQLite pragmas are NOT visible on the Projects tab
- [ ] System tab contains all technical diagnostics
- [ ] Tab active state uses indigo color (`var(--color-secondary)`)
- [ ] No text "How this UI is split" or similar dev-facing descriptions visible in default view

---

## Constraints

- Do NOT remove any existing functionality — everything in sidebar must still be accessible via System tab
- The sample-project.json path may need a Vite static asset approach — check `vite.config.ts` public dir
- Keep the existing project list, history, and workspace features intact
- "Load example" must not create a database record — only fill the draft form
