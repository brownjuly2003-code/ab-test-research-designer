# Task 3.4: Shareable reports — self-contained HTML + print CSS

**Phase:** 3 — Product features  
**Priority:** Medium  
**Depends on:** Phase 0.2 (routes/export.py), Phase 2.1 (charts data)  
**Effort:** ~4h

---

## Context

Read these files before starting:
- `app/backend/app/services/export_service.py` — existing HTML export
- `app/backend/app/schemas/api.py` — `ExportRequest`, `ExportResponse`
- `app/backend/app/routes/export.py` (from Phase 0.2, or `main.py`)
- Current `POST /api/v1/export/html` — outputs a basic HTML file

Current limitation: The existing HTML export is a simple HTML file with inline CSS but no charts and no print layout.
A stakeholder opening it sees the same text data they could read in the UI — no visual advantage.

---

## Goal

1. Add `POST /api/v1/export/html-standalone` — richer HTML with:
   - Pre-rendered SVG charts (power curve approximation, sensitivity table)
   - Print-optimized layout (`@media print`)
   - Fully self-contained (no external CDN, no JavaScript required to read)
2. Improve the existing HTML export with better structure and print CSS

---

## Steps

### Step 1: Add `html-standalone` export schema

In `app/backend/app/schemas/api.py`, extend `ExportRequest` or create `StandaloneExportRequest`:

```python
class StandaloneExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    # Core experiment data (same as existing ExportRequest)
    project_name: str
    hypothesis: str | None = None
    calculation: dict          # CalculationResponse dict
    design: dict               # DesignResponse dict
    ai_advice: dict | None = None
    
    # Optional: sensitivity matrix for chart rendering
    sensitivity: dict | None = None   # SensitivityResponse dict
    
    # Optional: actual results if post-experiment analysis was done
    results: dict | None = None
```

### Step 2: Build standalone HTML in export service

In `export_service.py`, add `build_standalone_html(request: StandaloneExportRequest) -> str`:

The function builds a complete HTML string. Key sections:

```python
def build_standalone_html(request) -> str:
    calc = request.calculation
    design = request.design
    
    # Build SVG sensitivity table (pure SVG, no JS)
    sensitivity_svg = ""
    if request.sensitivity:
        sensitivity_svg = _render_sensitivity_svg(request.sensitivity)
    
    # Build sample size bar (pure SVG)
    sample_bar_svg = _render_sample_bar_svg(calc)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AB Test Report: {html.escape(request.project_name)}</title>
<style>
  /* === Design tokens === */
  :root {{
    --color-primary: #0d9488;
    --color-border: #e2e8f0;
    --color-text: #1e293b;
    --color-bg: #ffffff;
    --space-4: 16px;
    --space-5: 24px;
    --radius-md: 8px;
    --font-sans: 'Segoe UI', system-ui, sans-serif;
    --font-mono: 'Cascadia Code', 'Courier New', monospace;
  }}
  
  /* === Base === */
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: var(--font-sans); color: var(--color-text); background: var(--color-bg); padding: var(--space-5); max-width: 900px; margin: 0 auto; }}
  
  /* === Report sections === */
  .report-header {{ border-bottom: 2px solid var(--color-primary); padding-bottom: var(--space-4); margin-bottom: var(--space-5); }}
  .report-title {{ font-size: 1.75rem; color: var(--color-primary); }}
  .section {{ margin-bottom: var(--space-5); padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-md); page-break-inside: avoid; }}
  .section h2 {{ font-size: 1.1rem; font-weight: 600; margin-bottom: var(--space-4); color: var(--color-primary); border-bottom: 1px solid var(--color-border); padding-bottom: var(--space-2); }}
  
  /* === Metric cards (3-up layout) === */
  .metric-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); }}
  .metric-card {{ text-align: center; padding: var(--space-4); background: #f8fafc; border-radius: var(--radius-md); }}
  .metric-value {{ font-size: 2rem; font-weight: 700; color: var(--color-primary); font-variant-numeric: tabular-nums; }}
  .metric-label {{ font-size: 0.85rem; color: #64748b; margin-top: 4px; }}
  
  /* === Tables === */
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  th {{ background: #f1f5f9; font-weight: 600; padding: 8px 12px; text-align: left; border: 1px solid var(--color-border); }}
  td {{ padding: 8px 12px; border: 1px solid var(--color-border); }}
  tr:nth-child(even) td {{ background: #fafafa; }}
  
  /* === Warnings === */
  .warning-high {{ background: #fef2f2; border-left: 3px solid #ef4444; padding: 8px 12px; margin: 4px 0; border-radius: 0 var(--radius-md) var(--radius-md) 0; }}
  .warning-medium {{ background: #fffbeb; border-left: 3px solid #f59e0b; padding: 8px 12px; margin: 4px 0; border-radius: 0 var(--radius-md) var(--radius-md) 0; }}
  
  /* === Print styles === */
  @media print {{
    body {{ padding: 0; max-width: 100%; font-size: 11pt; }}
    .section {{ page-break-inside: avoid; border: 1px solid #ccc; }}
    .report-header {{ page-break-after: avoid; }}
    h2 {{ page-break-after: avoid; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>

<div class="report-header">
  <div class="report-title">📊 {html.escape(request.project_name)}</div>
  <div style="color:#64748b; margin-top:8px;">
    A/B Test Design Report · Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
  </div>
</div>

<!-- SECTION: Key metrics -->
<div class="section">
  <h2>Key Metrics</h2>
  <div class="metric-grid">
    <div class="metric-card">
      <div class="metric-value">{calc.get('sample_size_per_variant', '—'):,}</div>
      <div class="metric-label">Users / variant</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">{calc.get('duration_days', '—')}</div>
      <div class="metric-label">Days estimated</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">{calc.get('total_sample_size', '—'):,}</div>
      <div class="metric-label">Total sample</div>
    </div>
  </div>
</div>

<!-- SECTION: Sample size breakdown bar SVG -->
{sample_bar_svg}

<!-- SECTION: Hypothesis -->
{_hypothesis_section(design)}

<!-- SECTION: Design details -->
{_design_section(design)}

<!-- SECTION: Warnings -->
{_warnings_section(calc.get('warnings', []))}

<!-- SECTION: Sensitivity table SVG -->
{sensitivity_svg}

<!-- SECTION: AI recommendations (if available) -->
{_ai_section(request.ai_advice) if request.ai_advice else ''}

<!-- SECTION: Post-experiment results (if available) -->
{_results_section(request.results) if request.results else ''}

<footer style="margin-top:32px; padding-top:16px; border-top:1px solid var(--color-border); color:#94a3b8; font-size:0.8rem;">
  Generated by AB Test Research Designer · Local-first, deterministic, open-source
</footer>

</body>
</html>"""
    return html
```

### Step 3: Implement SVG sensitivity table

Add `_render_sensitivity_svg(sensitivity_data: dict) -> str` in `export_service.py`:

Generates a pure SVG `<table>`-like visualization:
- Grid of rectangles
- Color-coded by duration (green=short, amber=medium, red=long)
- Current config cell outlined in teal
- Works without JavaScript, renders in any browser or PDF

```python
def _render_sensitivity_svg(data: dict) -> str:
    cells = data.get("cells", [])
    if not cells:
        return ""
    
    mde_vals = sorted(set(c["mde"] for c in cells))
    power_vals = sorted(set(c["power"] for c in cells))
    
    cell_w, cell_h = 100, 40
    header_w, header_h = 60, 30
    
    svg_w = header_w + len(power_vals) * cell_w + 20
    svg_h = header_h + len(mde_vals) * cell_h + 20
    
    rows = []
    for mi, mde in enumerate(mde_vals):
        for pi, power in enumerate(power_vals):
            cell = next((c for c in cells if c["mde"] == mde and c["power"] == power), None)
            if cell:
                duration = cell["duration_days"]
                color = _duration_color(duration)
                x = header_w + pi * cell_w
                y = header_h + mi * cell_h
                rows.append(f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" fill="{color}" stroke="#e2e8f0" />')
                rows.append(f'<text x="{x + cell_w//2}" y="{y + cell_h//2 + 5}" text-anchor="middle" font-size="13" font-family="system-ui">{math.ceil(duration)}d</text>')
    
    return f"""<div class="section">
<h2>Sensitivity Table (MDE vs Duration)</h2>
<svg width="{svg_w}" height="{svg_h}" xmlns="http://www.w3.org/2000/svg">
  {''.join(rows)}
</svg>
</div>"""
```

### Step 4: Add endpoint

In `routes/export.py`:

```python
@router.post("/api/v1/export/html-standalone")
async def export_html_standalone(request: StandaloneExportRequest, ...):
    html_content = build_standalone_html(request)
    return Response(
        content=html_content,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{sanitize_filename(request.project_name)}-report.html"'},
    )
```

### Step 5: Frontend — add "Export full report" button

In `ResultsPanel.tsx`, add alongside existing Markdown/HTML export buttons:

```tsx
<button className="btn-primary" onClick={handleExportStandalone}>
  Export full report (HTML)
</button>
```

This button builds the `StandaloneExportRequest` payload including sensitivity data if available, calls the endpoint, and triggers a file download.

---

## Verify

- [ ] `python -m pytest tests/ -x -q` — all tests pass
- [ ] `npm run build` exits 0; `npm test` passes
- [ ] `POST /api/v1/export/html-standalone` returns 200 with `content-type: text/html`
- [ ] Downloaded HTML file opens in browser without any JS (disable JS in browser → still readable)
- [ ] `Ctrl+P` from the HTML file → clean print layout, no navigation, proper page breaks
- [ ] All user content is HTML-escaped (no XSS: test with `project_name: "<script>alert(1)</script>"`)
- [ ] File downloads with correct `.html` extension and sanitized filename

---

## Constraints

- The HTML file must be 100% self-contained — no external CSS/JS/font URLs
- Use only SVG for charts (not canvas, not external charting libraries)
- `html.escape()` must be applied to ALL user-provided string values in the output
- The endpoint must work without authentication if auth is disabled (follow existing auth pattern)
- Do NOT break existing `/api/v1/export/html` and `/api/v1/export/markdown` endpoints
