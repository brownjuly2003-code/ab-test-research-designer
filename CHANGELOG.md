# Changelog

## 2026-03-08

### UI modernization

- redesigned the frontend into a dashboard-style interface with metric cards, accordion sections, timeline history, live backend status, progress bar, tooltips, and loading spinners
- upgraded typography to Inter + JetBrains Mono and added dark-mode support
- surfaced browser draft storage issues as dismissible UI toasts

### Backend and contracts

- added explicit `bonferroni_note` to calculation responses for multivariant designs
- regenerated frontend API contracts from FastAPI OpenAPI
- kept deterministic calculations, warnings, saved-project history, and comparison flows aligned with the new UI

### Documentation and packaging

- added architecture, API, and rules documentation
- added benchmark script and Docker packaging
- consolidated docs and demo assets for README-driven walkthroughs

## Earlier milestones

- local SQLite project CRUD, export, history, and comparison flows
- combined `POST /api/v1/analyze`
- local smoke test coverage against the backend-served frontend
- OpenAPI-generated frontend contracts and one-command verification
