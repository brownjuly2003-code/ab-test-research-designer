---
title: "P4.2 — Results IA: 19 accordions → 4 lifecycle stages + anchor ToC"
---

# P4.2 — Results IA: 19 accordions → 4 lifecycle stages + anchor ToC

Audit finding §6.2 п.2: the results panel is a flat wall of ~16 accordions (now 19)
with mixed badges, no grouping, no table of contents, and the most important block
(Decision readout) sits at the very bottom.

Goal: group the accordions into the four experiment-lifecycle stages the audit names
(Planning → Post-hoc → Execution → Decision), add an anchor table of contents, and
surface the Decision stage at the top when the experiment has live execution data.

Model/effort per audit: O48 high. Read cold taste/design skill before markup; no
emoji, no stock icons (house rule [[no-emoji-no-stock-icons]]).

## Stage → section mapping

- **Planning** — design & pre-launch validation:
  experiment design, metrics plan, sensitivity, power curve, sequential design,
  Bayesian posterior (conditional), bandit vs fixed, risk assessment, warnings & risks.
- **Post-hoc** — manual analysis of collected samples:
  observed results, categorical (chi-square), paired samples, multiple groups (omnibus),
  SRM check, multiple testing.
- **Execution** — the live experiment:
  user assignment, live experiment.
- **Decision** — the verdict:
  decision readout, AI recommendations.

**Comparison** is a cross-experiment dashboard loaded from the sidebar, not part of a
single experiment's lifecycle. It stays as a standalone accordion above the stages and
is not listed in the lifecycle ToC.

## Ordering

- Default (no live data): Planning → Post-hoc → Execution → Decision.
- Live data present: Decision → Execution → Planning → Post-hoc, and the Decision
  accordion defaults open.

"Live data present" is detected by a lightweight, abortable, silent-on-error probe:
one `GET /experiments/{id}/live-stats` in the panel when an experiment id is present,
reading `exposures_total > 0`. Sections keep their own on-demand fetch; the probe only
decides stage order. No experiment id (a fresh unsaved analysis) → no live data →
default order.

## Anchor ToC

A `<nav>` chip row at the top of the results with one link per stage (in the active
order). Each stage `<section>` carries `id="stage-<key>"` + `scroll-margin` so the
anchor lands cleanly. Stage headers use a plain ordinal number (1–4), a title, and a
one-line caption — no icons, no emoji.

## i18n

New keys under `results.panel.stages` (tocLabel, tocHeading, and title/caption for
planning/posthoc/execution/decision) in all 7 locales. Injected via round-trip-safe
JSON load/dump (verified byte-identical), additive diffs only. Content passes the
mojibake gate.

## Verify

- Extend `ResultsPanel.test.tsx`: 4 stage headings render, ToC has 4 anchor links,
  Decision stage moves to the top when the live-stats probe reports exposures.
- tsc + full vitest + vite build (< 500 kB) + locale content gate.
- Playwright before/after screenshots (light + RU; live-data reorder).
- Lighthouse gate green.
