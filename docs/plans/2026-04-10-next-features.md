# AB Test Research Designer — Next Features
**Date**: 2026-04-10  
**Phase**: After guardrail metrics + MDE detectability (112 backend / 87 frontend tests passing)  
**Goal**: Export, discovery, templates — highest-value features for day-to-day analyst workflow  
**Executor**: Codex

## Context for Codex

This is a local A/B experiment planning tool: React wizard → FastAPI → SQLite.

Current feature set (done):
- Sample size calc: binary + continuous metrics
- Guardrail metrics (max 3, with detectability thresholds)
- Power curves, sensitivity tables
- Project CRUD, revisions, comparison, archive/restore
- Full workspace export/import with HMAC signing
- Auth: token-based (read-write + read-only), rate limiting
- Diagnostics, readiness endpoints

Missing — ordered by analyst workflow impact:

---

## TASK 1 — PDF Report Export

**Priority**: P0 — analysts must share results with PMs/stakeholders who don't use the tool  
**Time estimate**: 2-3h  

### What to build

`GET /api/projects/{id}/report/pdf` → returns a formatted PDF of the experiment design report.

### Backend files to create/modify

```
app/backend/app/
  services/
    pdf_service.py         # NEW: PDF generation
  routes/
    reports.py             # add /report/pdf endpoint (route already exists for JSON)
requirements.txt           # add: weasyprint or reportlab or playwright
```

### PDF content spec (pages)

**Page 1 — Experiment Summary**
- Project name, hypothesis, created date
- Experiment type (binary/continuous), test type (one/two-tailed)
- Primary metric + MH/effect size
- Test variants (names + traffic split)

**Page 2 — Sample Size Results**
- Table: variant | required n | daily traffic | duration (days)
- Power: α={α}, power={power}, MDE={mde}
- Guardrail metrics table: name | detectable MDE | status

**Page 3 — Power Curve**
- Embed the power curve chart as SVG/PNG
- Sensitivity table: effect size → required n

**Page 4 — Warnings & Recommendations**
- All design warnings (traffic, seasonality, etc.)
- LLM recommendations if present
- Revision history (compact: date + change summary)

### Implementation approach

Use `weasyprint` (CSS → PDF) for styled output. Create `pdf_service.py` that:
1. Fetches project + latest report from DB
2. Renders `templates/report.html` (Jinja2) with project data
3. Converts HTML → PDF via weasyprint

```python
# app/backend/app/services/pdf_service.py
from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

def generate_report_pdf(project: dict, report: dict) -> bytes:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html")
    html_content = template.render(project=project, report=report)
    return HTML(string=html_content).write_pdf()
```

Create `app/backend/app/templates/report.html` — clean CSS-styled HTML template.

### Frontend

Add "Export PDF" button in `ResultsPanel.tsx`:
```tsx
async function handleExportPDF() {
  const res = await fetch(`/api/projects/${projectId}/report/pdf`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${project.name}-report.pdf`;
  a.click();
}
```

### Acceptance criteria

- [x] `GET /api/projects/{id}/report/pdf` returns `Content-Type: application/pdf`
- [x] PDF contains all 4 sections (summary, results, power curve, warnings)
- [x] Download triggered correctly from "Export PDF" button in UI
- [x] 404 if project doesn't exist
- [x] Auth required (same token as other endpoints)
- [x] `tests/test_api_routes.py` — 3 tests: success, no project, unauthenticated
- [x] PDF filename: `{project-name}-report.pdf` (slugified)

---

## TASK 2 — Project Search, Filter & Sort

**Priority**: P0 — workspace list becomes unusable after 20+ projects  
**Time estimate**: 1.5h  

### What to build

Add search + filter + sort to the project list endpoint and UI.

### Backend files to modify

```
app/backend/app/
  routes/projects.py     # add query params to GET /api/projects
  services/
    project_service.py   # add search/filter logic to list query
```

### API changes

```python
# GET /api/projects — new query params:
@router.get("/projects")
async def list_projects(
    q: str | None = None,                    # full-text: searches name + hypothesis
    status: Literal["active", "archived", "all"] = "active",
    metric_type: Literal["binary", "continuous", "all"] = "all",
    sort_by: Literal["created_at", "updated_at", "name", "duration_days"] = "updated_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    limit: int = Query(50, le=200),
    offset: int = 0,
):
```

SQLite query (in `project_service.py`):
```python
# Full-text search using LIKE on name + hypothesis fields
# Filter by status (archived flag) and metric_type
# Sort dynamically with sanitized column name
```

Response adds pagination metadata:
```json
{
  "projects": [...],
  "total": 47,
  "offset": 0,
  "limit": 50,
  "has_more": false
}
```

### Frontend files to modify

```
app/frontend/src/components/
  ProjectList.tsx         # add search input + filter dropdowns + sort controls
  ProjectListFilters.tsx  # NEW: filter bar component
```

UI elements:
- Search input (debounced 300ms): filters by name/hypothesis
- Status toggle: Active | Archived | All
- Metric type filter: All | Binary | Continuous
- Sort dropdown: Last updated | Name | Duration
- Result count: "47 experiments"

### Acceptance criteria

- [x] `GET /api/projects?q=checkout` returns only projects matching "checkout" in name/hypothesis
- [x] `GET /api/projects?status=archived` returns only archived projects
- [x] `GET /api/projects?metric_type=binary&sort_by=name&sort_dir=asc` works
- [x] Response includes `total` count
- [x] Search input debounced (no request on every keystroke)
- [x] Empty state: "No experiments match your filters" with clear-filters link
- [x] `tests/test_api_routes.py` — 6 tests covering search, filter combos, sort

---

## TASK 3 — Experiment Templates

**Priority**: P1 — common test types (checkout, onboarding, pricing) are set up identically every time  
**Time estimate**: 2h  

### What to build

A template library of pre-filled wizard configurations. User picks a template → wizard pre-populates → they adjust and run.

### Files to create

```
app/backend/app/
  routes/templates.py    # NEW: CRUD for templates
  services/
    template_service.py  # NEW: template management
  schemas/
    template.py          # NEW: TemplateSchema
app/backend/
  templates/             # NEW: built-in template YAML files
    checkout_conversion.yaml
    onboarding_completion.yaml
    pricing_sensitivity.yaml
    feature_adoption.yaml
    latency_impact.yaml
app/frontend/src/components/
  TemplateGallery.tsx    # NEW: template picker modal
  WizardDraftStep.tsx    # modify: "Start from template" button
```

### Template schema

```python
# app/backend/app/schemas/template.py
class Template(BaseModel):
    id: str
    name: str                  # "Checkout Conversion"
    category: str              # "Revenue", "Engagement", "Performance"
    description: str           # 1-2 sentences
    built_in: bool             # False = user-created
    payload: dict              # full wizard payload (pre-filled)
    tags: list[str]            # ["binary", "revenue", "conversion"]
    usage_count: int           # how many times used
```

### Built-in template example (`checkout_conversion.yaml`)

```yaml
name: "Checkout Conversion"
category: "Revenue"
description: "Test changes to checkout flow. Measures conversion rate from cart to purchase."
tags: [binary, revenue, conversion]
payload:
  project_name: ""         # user fills in
  hypothesis: "Changing [element] in checkout will increase purchase conversion by [X]%"
  experiment_type: binary
  primary_metric:
    name: "Purchase Conversion Rate"
    baseline_rate: 0.03
    mde: 0.10
    direction: increase
  alpha: 0.05
  power: 0.80
  test_type: two_tailed
  variants:
    - name: Control
      traffic_split: 50
    - name: Treatment
      traffic_split: 50
  guardrail_metrics:
    - name: "Revenue per User"
      direction: no_decrease
    - name: "Cart Abandonment Rate"
      direction: no_increase
```

### API endpoints

```
GET  /api/templates              — list all templates (built-in + user-created)
GET  /api/templates/{id}         — get single template
POST /api/templates              — save current wizard draft as template
DELETE /api/templates/{id}       — delete user-created template (cannot delete built-in)
POST /api/templates/{id}/use     — increment usage_count, return payload for wizard
```

### Frontend

`TemplateGallery.tsx` — modal with:
- Category tabs: All | Revenue | Engagement | Performance
- Template cards: name, description, tags, usage count
- "Use template" button → pre-fills wizard and closes modal

Add "Start from template" button to wizard step 1 (or new project creation screen).

### Acceptance criteria

- [x] `GET /api/templates` returns 5 built-in templates on fresh install
- [x] `POST /api/templates/{id}/use` pre-fills wizard (returns the payload)
- [x] User can save their own template: `POST /api/templates` with name + description
- [x] Built-in templates cannot be deleted (403)
- [x] `TemplateGallery` modal opens/closes, shows all 5 built-ins
- [x] Selecting a template → wizard populates with template payload (user can edit all fields)
- [x] `tests/test_api_routes.py` — 5 tests: list, use, save, delete built-in (403), delete user

---

## TASK 4 — Chart Image Export (SVG/PNG)

**Priority**: P1 — analysts paste power curves into Confluence/Google Docs constantly  
**Time estimate**: 1h  

### What to build

Download button on every chart in `ResultsPanel.tsx` that exports SVG or PNG.

### Files to modify

```
app/frontend/src/components/
  ResultsPanel.tsx        # add export buttons to each chart
  ChartExport.tsx         # NEW: reusable export utility component
```

### Implementation

Charts are rendered with Recharts (SVG-based). Export approach:
1. Get the SVG DOM element from the chart container ref
2. Serialize to string: `new XMLSerializer().serializeToString(svgEl)`
3. For SVG: create Blob + download link
4. For PNG: draw to Canvas via `Image` + `canvas.toDataURL("image/png")`

```tsx
// ChartExport.tsx
interface ChartExportProps {
  chartRef: React.RefObject<HTMLDivElement>;
  filename: string;
}

export function ChartExportMenu({ chartRef, filename }: ChartExportProps) {
  const exportAs = async (format: "svg" | "png") => {
    const svg = chartRef.current?.querySelector("svg");
    if (!svg) return;
    if (format === "svg") downloadSVG(svg, filename);
    else await downloadPNG(svg, filename);
  };

  return (
    <div className="chart-export-menu">
      <button onClick={() => exportAs("svg")}>SVG</button>
      <button onClick={() => exportAs("png")}>PNG</button>
    </div>
  );
}
```

Apply to:
- Power curve chart
- Sensitivity table chart (if rendered as chart)
- Any other chart in ResultsPanel

### Acceptance criteria

- [x] Each chart has SVG + PNG download buttons (small, unobtrusive — top-right corner)
- [x] SVG download: valid SVG file, chart colors preserved
- [x] PNG download: 2× resolution (scale canvas before render)
- [x] Filename: `{project-name}-power-curve.svg` (slugified)
- [x] Works in Chrome and Firefox
- [x] No backend required (pure frontend)
- [x] `WizardDraftStep.test.tsx` or new test file — 2 tests: SVG blob creation, PNG canvas

---

## TASK 5 — Keyboard Shortcuts + Accessibility

**Priority**: P1 — power users hate the mouse; a11y is table stakes  
**Time estimate**: 1h  

### What to build

Global keyboard shortcuts for common actions + ARIA labels on all interactive elements.

### Files to modify

```
app/frontend/src/
  hooks/
    useKeyboardShortcuts.ts   # NEW: global shortcut registry
  components/
    ShortcutHelp.tsx          # NEW: ? → shows shortcut cheat sheet modal
    WizardDraftStep.tsx       # add aria-labels to form fields
    ResultsPanel.tsx          # add keyboard nav to results tabs
    ProjectList.tsx           # add shortcuts
  App.tsx                     # register global shortcuts
```

### Shortcut map

| Shortcut | Action |
|----------|--------|
| `?` | Open keyboard shortcut help |
| `N` | New project |
| `Ctrl+Enter` | Submit current wizard step |
| `Esc` | Close modal / cancel |
| `Ctrl+Z` | Restore previous draft (if autosave present) |
| `Ctrl+P` | Export PDF (if results visible) |
| `Ctrl+E` | Export current draft JSON |
| `←` / `→` | Previous / Next wizard step |
| `/` | Focus search (in project list) |
| `R` | Refresh / recalculate |

### Implementation

```typescript
// hooks/useKeyboardShortcuts.ts
type ShortcutHandler = (e: KeyboardEvent) => void;

export function useKeyboardShortcuts(
  shortcuts: Record<string, ShortcutHandler>,
  active: boolean = true
) {
  useEffect(() => {
    if (!active) return;
    const handler = (e: KeyboardEvent) => {
      // Skip if focus is in input/textarea
      if (["INPUT", "TEXTAREA"].includes((e.target as Element).tagName)) return;
      const key = buildKey(e); // e.g. "ctrl+enter", "shift+n"
      shortcuts[key]?.(e);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [shortcuts, active]);
}
```

### Accessibility additions

- All form fields in wizard: `aria-label`, `aria-describedby` (links to hint text)
- Error messages: `role="alert"` + `aria-live="polite"`
- Modal dialogs: `role="dialog"`, `aria-modal="true"`, focus trap
- Chart containers: `role="img"`, `aria-label="Power curve showing..."` 
- Button loading states: `aria-busy="true"`

### Acceptance criteria

- [x] `?` opens shortcut help modal (lists all shortcuts in a table)
- [x] `Ctrl+Enter` advances wizard step (or submits if on last step)
- [x] `←` / `→` navigates wizard steps (when not in input)
- [x] `/` focuses project search input
- [x] `Esc` closes any open modal
- [x] All form fields have `aria-label` or `aria-labelledby`
- [x] Error messages have `role="alert"`
- [x] No keyboard trap outside of modals
- [x] `experiment.test.ts` or new file — 4 shortcut hook tests

---

## TASK 6 — Audit Log

**Priority**: P2 — teams need traceability; "who changed what when?"  
**Time estimate**: 1.5h  

### What to build

Append-only audit log of all write operations (create/update/delete/archive/restore).

### Backend files to create/modify

```
app/backend/app/
  models/
    audit.py               # NEW: AuditEntry model
  services/
    audit_service.py       # NEW: log_action(), get_log()
  routes/
    audit.py               # NEW: GET /api/audit
  routes/projects.py       # instrument existing routes to call log_action()
```

### SQLite schema addition

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,           -- "project.create", "project.update", "project.archive"
    project_id TEXT,
    project_name TEXT,
    actor TEXT,                     -- "api_key:rw", "api_key:ro", "anonymous"
    request_id TEXT,
    payload_diff TEXT,              -- JSON: {field: [old, new]} for updates
    ip_address TEXT
);
```

### Actions to log

| Action | Trigger |
|--------|---------|
| `project.create` | POST /api/projects |
| `project.update` | PUT/PATCH /api/projects/{id} |
| `project.delete` | DELETE /api/projects/{id} |
| `project.archive` | POST /api/projects/{id}/archive |
| `project.restore` | POST /api/projects/{id}/restore |
| `project.export` | GET /api/projects/{id}/export |
| `workspace.import` | POST /api/workspace/import |
| `auth.failure` | Any 401 response |

### API

```
GET /api/audit                      — list recent entries (last 500)
GET /api/audit?project_id={id}      — entries for specific project
GET /api/audit?action=project.delete — filter by action
GET /api/audit/export               — download as CSV
```

Response:
```json
{
  "entries": [
    {
      "id": 1,
      "ts": "2026-04-10T14:32:00Z",
      "action": "project.update",
      "project_id": "abc-123",
      "project_name": "Checkout Test",
      "actor": "api_key:rw",
      "payload_diff": {"primary_metric.mde": [0.05, 0.10]}
    }
  ],
  "total": 47
}
```

### Frontend

Add "Audit Log" tab to workspace/admin view (or collapsible section in project detail):
- Table: time | action | project | actor
- Filter by project (dropdown)
- Export CSV button → `GET /api/audit/export`

### Acceptance criteria

- [x] Every write operation (create/update/delete/archive) creates an audit entry
- [x] `GET /api/audit` returns entries newest-first
- [x] `GET /api/audit?project_id=X` returns only entries for that project
- [x] `GET /api/audit/export` returns `Content-Type: text/csv`
- [x] Auth required (read-only token can read audit log; cannot export if `AGENTFLOW_RO`)
- [x] `tests/test_api_routes.py` — 5 tests: create logs entry, update logs diff, filter by project, CSV export

---

## TASK 7 — Dark Mode

**Priority**: P2 — quick win; high analyst satisfaction (long sessions at night)  
**Time estimate**: 1h  

### What to build

CSS custom properties + toggle that persists to localStorage. Follows system preference by default.

### Files to modify

```
app/frontend/src/
  hooks/
    useTheme.ts            # NEW: theme management hook
  components/
    ThemeToggle.tsx        # NEW: sun/moon toggle button
    Layout.tsx             # wrap with ThemeProvider / data-theme attr
  styles/
    variables.css          # NEW: CSS custom properties for both themes
    global.css             # use variables throughout (replace hardcoded colors)
```

### Implementation

```css
/* styles/variables.css */
:root[data-theme="light"] {
  --bg-primary: #ffffff;
  --bg-secondary: #f9fafb;
  --text-primary: #111827;
  --text-secondary: #6b7280;
  --border: #e5e7eb;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --danger: #ef4444;
  --success: #22c55e;
  --chart-line: #3b82f6;
  --chart-area: rgba(59, 130, 246, 0.1);
}

:root[data-theme="dark"] {
  --bg-primary: #111827;
  --bg-secondary: #1f2937;
  --text-primary: #f9fafb;
  --text-secondary: #9ca3af;
  --border: #374151;
  --accent: #60a5fa;
  --accent-hover: #93c5fd;
  --danger: #f87171;
  --success: #4ade80;
  --chart-line: #60a5fa;
  --chart-area: rgba(96, 165, 250, 0.1);
}
```

```typescript
// hooks/useTheme.ts
export function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("theme");
    if (saved) return saved as "light" | "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  return { theme, toggle: () => setTheme(t => t === "light" ? "dark" : "light") };
}
```

### Acceptance criteria

- [x] Toggle button (sun/moon icon) in top-right header
- [x] All UI surfaces use CSS variables (no hardcoded `#fff` / `#000`)
- [x] Charts (Recharts) use theme-aware colors (passed as props from CSS vars)
- [x] System preference respected on first load (no flash)
- [x] Preference persists across page reloads (localStorage)
- [x] `Ctrl+Shift+D` also toggles dark mode (keyboard shortcut from Task 5)
- [x] No white flash on dark-mode page load (set `data-theme` before React mounts)

---

## TASK 8 — CSV / Excel Data Export

**Priority**: P2 — analysts want raw numbers in spreadsheets  
**Time estimate**: 1h  

### What to build

Export sample size results, sensitivity table, and guardrail metrics as CSV or Excel.

### Backend files to create/modify

```
app/backend/app/
  routes/reports.py      # add /report/csv and /report/xlsx endpoints
  services/
    export_service.py    # NEW: CSV/Excel generation
requirements.txt         # add: openpyxl
```

### Endpoints

```
GET /api/projects/{id}/report/csv    → CSV with all tables (multi-section)
GET /api/projects/{id}/report/xlsx   → Excel workbook with multiple sheets
```

### CSV format

```
# Sample Size Results
Variant,Required N,Daily Traffic,Duration (days),Traffic Split %
Control,15420,5000,4,50
Treatment,15420,5000,4,50

# Sensitivity Analysis
Effect Size,Required N (80% power),Required N (90% power)
5%,38550,51640
10%,9638,12910
15%,4284,5738

# Guardrail Metrics
Metric Name,Direction,Detectable MDE (Control n),Detectable MDE (Treatment n)
Revenue per User,no_decrease,2.3%,2.3%
Cart Abandonment Rate,no_increase,3.1%,3.1%
```

### Excel format (multi-sheet)

- Sheet 1: "Summary" — project info + sample size results
- Sheet 2: "Sensitivity" — effect size table
- Sheet 3: "Guardrails" — guardrail metrics with detectability
- Sheet 4: "Raw Inputs" — all wizard inputs for reproducibility

### Frontend

Add "Export" dropdown to `ResultsPanel.tsx`:
```
[ Export ▾ ]
  PDF Report
  ──────────
  CSV Data
  Excel Workbook
  ──────────
  Export Draft JSON
```

### Acceptance criteria

- [x] `GET /api/projects/{id}/report/csv` returns `Content-Type: text/csv` with all 3 sections
- [x] `GET /api/projects/{id}/report/xlsx` returns valid `.xlsx` with 4 sheets
- [x] Export dropdown in UI replaces individual export buttons (unified UX)
- [x] Auth required
- [x] `tests/test_api_routes.py` — 4 tests: CSV success, XLSX success, 404, unauth

---

## Execution Order

```
TASK 1  (PDF export)      ← P0, most visible to stakeholders
TASK 2  (Search/filter)   ← P0, needed as project count grows
TASK 3  (Templates)       ← P1, depends on wizard payload structure (stable)
TASK 4  (Chart export)    ← P1, pure frontend, parallelize with Task 3
TASK 5  (Keyboard + a11y) ← P1, pure frontend, parallelize with Task 4
TASK 6  (Audit log)       ← P2, backend-heavy
TASK 7  (Dark mode)       ← P2, pure frontend
TASK 8  (CSV/Excel)       ← P2, builds on Task 1 export infrastructure
```

**Parallelizable**: Tasks 4, 5, 7 are pure frontend — can run together.  
**Sequential**: Task 8 after Task 1 (shares export dropdown UX).  

---

## Definition of Done

After all 8 tasks:
1. `GET /api/projects/{id}/report/pdf` → 4-page PDF opens in browser
2. `GET /api/projects?q=checkout&metric_type=binary` → filtered results
3. 5 built-in templates loadable from wizard
4. Power curve downloadable as PNG in 2 clicks
5. `?` shows keyboard shortcut map
6. Every write operation has an audit entry
7. Dark mode persists across reloads, follows system pref
8. `GET /api/projects/{id}/report/xlsx` → 4-sheet Excel file
9. `pytest tests/ -x -q` → 130+ passed
10. `npm test` → 100+ passed
