# Codex Tasks: AB Test Research Designer → Commercial Product

> Based on `archive/2026-04-23-bcg-planning-docs/commercial-upgrade-plan.md`  
> Generated: 2026-04-10  
> Total tasks: 18 | Estimated: ~9 weeks (1 dev)

---

## Dependency order

```
Phase 0 (Foundation) ──┬── Phase 1 (UX)        ──┬── Phase 3.3 (Results)
MUST RUN FIRST         ├── Phase 2 (Visual)     ├── Phase 3.4 (Shareable)
                       └── Phase 3.1-3.2 ──────┘
                                    │
                                    └── Phase 4 (Advanced stats)
                                                    │
                                                    └── Phase 5 (Polish)
```

**Phases 1 + 2 + 3.1 + 3.2 can run in parallel after Phase 0.**

---

## Task index

| File | Task | Priority | Effort |
|------|------|----------|--------|
| [phase-0-1-css-architecture.md](phase-0-1-css-architecture.md) | Design tokens + CSS Modules | Critical | 6h |
| [phase-0-2-backend-modularization.md](phase-0-2-backend-modularization.md) | Split main.py into APIRouter modules | Critical | 4h |
| [phase-0-3-frontend-refactor.md](phase-0-3-frontend-refactor.md) | Refactor App.tsx + split experiment.ts | Critical | 5h |
| [phase-1-1-onboarding.md](phase-1-1-onboarding.md) | Empty state + sidebar tabs | High | 4h |
| [phase-1-2-tooltips.md](phase-1-2-tooltips.md) | Floating UI tooltips on all numeric fields | High | 3h |
| [phase-1-3-live-calculations.md](phase-1-3-live-calculations.md) | Real-time preview + MDE/Power sliders | High | 5h |
| [phase-1-4-ux-polish.md](phase-1-4-ux-polish.md) | Inline validation + toasts + keyboard shortcuts | High | 5h |
| [phase-2-1-data-visualization.md](phase-2-1-data-visualization.md) | Power curve + sensitivity table (Recharts) | High | 6h |
| [phase-2-2-visual-polish.md](phase-2-2-visual-polish.md) | Elevation + skeletons + micro-interactions | Medium | 4h |
| [phase-2-3-icon-system.md](phase-2-3-icon-system.md) | Replace inline SVGs with Lucide React | Medium | 2h |
| [phase-3-1-multi-metric.md](phase-3-1-multi-metric.md) | Guardrail metrics (UI + backend) | High | 5h |
| [phase-3-2-srm-detection.md](phase-3-2-srm-detection.md) | SRM checker (chi-square) | High | 4h |
| [phase-3-3-results-tracker.md](phase-3-3-results-tracker.md) | Post-experiment results input + significance | Medium | 6h |
| [phase-3-4-shareable-reports.md](phase-3-4-shareable-reports.md) | Self-contained HTML export + print CSS | Medium | 4h |
| [phase-4-1-sequential-testing.md](phase-4-1-sequential-testing.md) | O'Brien-Fleming alpha spending | Medium | 6h |
| [phase-4-2-cuped.md](phase-4-2-cuped.md) | CUPED variance reduction estimator | Medium | 4h |
| [phase-4-3-bayesian.md](phase-4-3-bayesian.md) | Bayesian power analysis mode | Low | 5h |
| [phase-5-polish.md](phase-5-polish.md) | A11y audit + i18n + Lighthouse CI | Medium | 6h |
