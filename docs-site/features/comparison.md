# Multi-project comparison

![Comparison dashboard](../assets/screenshots/comparison-dashboard.png)

The comparison view is built for portfolio triage: pick two to five saved experiments and inspect them side by side before spending traffic or engineering time.

## What the dashboard compares

- projected sample size and duration side by side
- power-curve and sensitivity views across saved projects
- observed-effect and forest-style comparison panels
- overlapping assumptions, risks, and recommendation highlights
- mixed metric-type selections, with clear caveats when direct effect comparison is not meaningful

## Export and sharing

Comparison selections can be exported through `POST /api/v1/export/comparison` as Markdown or PDF, which makes it easy to move an internal shortlist into a stakeholder update.
