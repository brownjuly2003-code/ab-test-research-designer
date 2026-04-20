# Task 0.3: Frontend refactor — App.tsx + experiment.ts split

**Phase:** 0 — Foundation  
**Priority:** Critical  
**Depends on:** nothing (can run in parallel with 0.1, 0.2)  
**Effort:** ~5h

---

## Context

Read these files before starting:
- `app/frontend/src/App.tsx` (713 lines, 20+ state variables)
- `app/frontend/src/hooks/useProjectManager.ts`
- `app/frontend/src/hooks/useAnalysis.ts` (if it exists)
- `app/frontend/src/hooks/useDraftPersistence.ts` (if it exists)
- `app/frontend/src/lib/experiment.ts` (697 lines)
- `app/frontend/src/App.test.tsx` (32 tests — must pass after refactor)

Current problems:
1. `App.tsx` has 713 lines and 20+ useState variables. Hooks return raw setters that App calls directly (e.g., `setLoading`, `setError`, `setResults` all called separately).
2. `experiment.ts` has 697 lines mixing types, validation, payload builders, field config, and review sections.

---

## Goal

1. Refactor hooks to export high-level actions instead of raw setters
2. Reduce `App.tsx` to ≤ 300 lines by moving orchestration into hooks
3. Split `experiment.ts` into 4 focused files
4. All 64 frontend tests must pass unchanged

---

## Steps

### Step 1: Split `experiment.ts` into 4 files

Create these files in `app/frontend/src/lib/`:

**`types.ts`** — all TypeScript interfaces and type definitions:
- `ExperimentDraft`, `MetricInput`, `VariantConfig`, `ConstraintsConfig`
- `AnalysisResult`, `CalculationResult`, `DesignReport`, `AiAdvice`
- `Project`, `AnalysisRun`, `ProjectRevision`, `WorkspaceStatus`
- All other types currently in `experiment.ts`

**`validation.ts`** — all validation logic:
- `validateStep(step, draft): string[]` function
- `isStepValid(step, draft): boolean`
- Field-level validators

**`payload.ts`** — request payload builders:
- `buildCalculatePayload(draft): CalculateRequest`
- `buildAnalyzePayload(draft): AnalyzeRequest`
- `buildDesignPayload(draft): DesignRequest`
- `buildExportPayload(result): ExportRequest`

**`field-config.ts`** — wizard field definitions and review section config:
- `WIZARD_STEPS: WizardStep[]` (step names, icons, labels)
- `FIELD_DEFINITIONS: Record<string, FieldDef>` (label, tooltip text, validation rules)
- `REVIEW_SECTIONS: ReviewSection[]`

Keep `experiment.ts` as a re-export barrel for backwards compatibility:
```typescript
// experiment.ts — re-export barrel (backwards compat)
export * from './types';
export * from './validation';
export * from './payload';
export * from './field-config';
```

This avoids breaking any imports in test files.

### Step 2: Upgrade `useAnalysis` hook

Current: likely exports `loading`, `error`, `results`, `setLoading`, `setError`, `setResults`.

Refactor to export high-level actions:

```typescript
interface UseAnalysisReturn {
  // State (read-only from App perspective)
  isAnalyzing: boolean;
  analysisError: string | null;
  analysisResult: AnalysisResult | null;

  // High-level actions
  runAnalysis: (draft: ExperimentDraft) => Promise<void>;
  clearAnalysis: () => void;
}
```

Internally the hook manages all the `fetch`, `setLoading`, `setError`, `setResults` logic.
Add `AbortController` support: cancel any in-flight request when `runAnalysis` is called again.

```typescript
const abortRef = useRef<AbortController | null>(null);

const runAnalysis = async (draft: ExperimentDraft) => {
  // Cancel previous request
  abortRef.current?.abort();
  abortRef.current = new AbortController();
  
  setIsAnalyzing(true);
  setAnalysisError(null);
  try {
    const result = await api.analyze(buildAnalyzePayload(draft), { signal: abortRef.current.signal });
    setAnalysisResult(result);
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') return; // ignore cancellation
    setAnalysisError(e instanceof Error ? e.message : 'Analysis failed');
  } finally {
    setIsAnalyzing(false);
  }
};
```

### Step 3: Upgrade `useProjectManager` hook

Current: exports many individual setters and separate load/save/delete functions.

Refactor to group into logical action objects:

```typescript
interface UseProjectManagerReturn {
  // State
  projects: Project[];
  activeProject: Project | null;
  isSaving: boolean;
  projectError: string | null;

  // Actions
  saveProject: (draft: ExperimentDraft, analysisResult?: AnalysisResult) => Promise<Project>;
  loadProject: (projectId: string) => Promise<ExperimentDraft>;
  deleteProject: (projectId: string) => Promise<void>;
  refreshProjects: () => Promise<void>;
  compareProjects: (id1: string, id2: string) => Promise<ComparisonResult>;
}
```

The hook handles all the state management internally.

### Step 4: Upgrade `useDraftPersistence` hook

Expose:
```typescript
interface UseDraftPersistenceReturn {
  draft: ExperimentDraft;
  isDirty: boolean;
  updateDraft: (partial: Partial<ExperimentDraft>) => void;
  updateDraftField: (path: string, value: unknown) => void;
  resetDraft: () => void;
  storageWarning: string | null; // QuotaExceededError message
}
```

### Step 5: Slim down `App.tsx`

After hook upgrades, `App.tsx` should:
- Import the 3 hooks and use their high-level API
- Manage only UI state: `currentStep`, `activeView` (wizard/results/history)
- Render the layout: `<SidebarPanel>`, `<WizardPanel>` or `<ResultsPanel>`
- Handle routing between views
- No direct `setLoading`, `setError`, `setResults` calls — only hook actions

Target: `App.tsx` ≤ 300 lines.

---

## Verify

- [ ] `npm test` — all 64 vitest tests pass (no test file changes allowed)
- [ ] `npx tsc --noEmit` exits 0
- [ ] `npm run build` exits 0
- [ ] `App.tsx` is ≤ 300 lines
- [ ] `experiment.ts` still exists as a re-export barrel (for test compatibility)
- [ ] `lib/types.ts`, `lib/validation.ts`, `lib/payload.ts`, `lib/field-config.ts` all exist
- [ ] `useAnalysis` has `AbortController` — grep: `AbortController` found in `useAnalysis.ts`
- [ ] No raw setters (`setLoading`, `setError`, `setResults`) called directly in `App.tsx`

---

## Constraints

- Do NOT change any test files
- `experiment.ts` must remain as a re-export barrel — do NOT delete it
- Do NOT change API endpoint URLs or request/response shapes
- Do NOT add new npm dependencies
- All imports in test files must resolve — check `App.test.tsx` imports before removing anything
