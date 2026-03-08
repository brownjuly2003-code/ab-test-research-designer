# Build Plan

## Phase 0 — Discovery and repo study
Цель:
- изучить документы
- предложить финальную repo structure
- проверить, как интегрировать локальный оркестратор
- создать `docs/progress.md`

Done when:
- Codex описал plan
- создан skeleton repo
- зафиксированы assumptions and risks

## Phase 1 — Backend skeleton
Сделать:
- FastAPI app
- config handling
- health endpoint
- schemas basics
- test setup

Done when:
- backend starts locally
- `/health` works
- basic test command works

## Phase 2 — Statistical engine
Сделать:
- binary calculations
- continuous calculations
- duration estimator
- tests

Done when:
- deterministic calculations pass tests
- invalid inputs are handled

## Phase 3 — Rules engine
Сделать:
- warning catalog
- rule evaluation logic
- tests

Done when:
- warnings generated for key scenarios

## Phase 4 — Design composer
Сделать:
- report assembler
- report schema
- deterministic fallback report

Done when:
- full report can be built without LLM

## Phase 5 — LLM adapter
Сделать:
- inspect integration strategy for local orchestrator
- implement adapter interface
- add timeout and graceful fallback
- add parser for structured AI response

Done when:
- if adapter is reachable, AI advice returns parsed structure
- if adapter fails, app still works

## Phase 6 — API routes
Сделать:
- calculate endpoint
- design endpoint
- llm advice endpoint
- projects CRUD endpoints
- export endpoints

Done when:
- all endpoints work locally
- endpoint tests exist for core flows

## Phase 7 — Storage
Сделать:
- SQLite setup
- project persistence
- read/update flows

Done when:
- projects can be saved and re-opened

## Phase 8 — Frontend form
Сделать:
- wizard layout
- all input sections
- client-side validation
- API wiring

Done when:
- user can complete form and submit

## Phase 9 — Results page
Сделать:
- calculations block
- warnings block
- design report block
- export actions

Done when:
- user can see separated deterministic and AI sections

## Phase 10 — Polish
Сделать:
- empty/error states
- UX cleanup
- docs update
- runbook

Done when:
- project is understandable for a beginner
- local run instructions are complete
