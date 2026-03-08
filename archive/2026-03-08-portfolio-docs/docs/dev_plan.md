# Development Plan

## Scope

This document records architecture analysis and implementation planning for the
`AB Test Research Designer` project before code implementation begins.

The analysis is based on:

- `docs/HISTORY.md`
- `docs/PROJECT_OVERVIEW.md`
- the local orchestrator in `D:\Perplexity_Orchestrator2`

## 1. Local Orchestrator Architecture Summary

### High-level structure

The local orchestrator is a separate Python/FastAPI service with these main
layers:

- `api/`
  - external HTTP API
  - route handlers for orchestration, health, threads, analytics, and other UI
    features
- `orchestrator/`
  - orchestration logic
  - task decomposition
  - role-based prompting
  - consensus logic
- `api/browser_worker.py`
  - bridge from HTTP/API layer to browser automation
  - manages a singleton worker and retries
- `browser/`
  - Playwright-based interaction with Perplexity UI
- `accounts/`
  - account/session rotation
- `database/`
  - request logging and persistence for orchestrator-side features
- `config/settings.py`
  - runtime settings such as port, timeouts, headless mode, and API keys

### Runtime model

The orchestrator does not call Claude through a normal provider SDK. Instead,
it uses browser automation against Perplexity and selects the target model in
the UI. This means:

- model access is mediated by Playwright and stored browser sessions
- one request may involve browser startup, model selection, retries, and
  account rotation
- orchestration reliability depends on session validity and UI stability

### External API exposed by the orchestrator

The orchestrator runs as FastAPI on port `8001` according to
`D:\Perplexity_Orchestrator2\config\settings.py` and `SERVERS.md`.

Relevant endpoints:

- `GET /health`
  - basic availability check
  - also reports whether accounts with sessions are available
- `POST /orchestrate`
  - asynchronous orchestration endpoint
  - returns `task_id`
  - requires polling `GET /status/{task_id}`
- `GET /status/{task_id}`
  - returns task progress and final result
- `POST /api/gk/orchestrate`
  - synchronous GraceKelly-style orchestration endpoint
  - returns final payload in one response
- `GET /api/gk/patterns`
  - lists supported orchestration patterns

### Relevant request/response contracts

#### `POST /orchestrate`

Request fields:

- `task`
- `level`
- optional `model`
- optional `mirror_telegram`

Response fields:

- `task_id`
- `status`
- `message`

Final result is fetched from `GET /status/{task_id}` and includes:

- `result.answer`
- `result.final_answer`
- `result.consensus_score`
- `result.models_used`
- `result.duration_ms`
- verification flags and consensus metadata

#### `POST /api/gk/orchestrate`

Request fields:

- `query`
- `pattern`
- optional `thread_id`
- optional `model`
- optional `model_pair`
- optional `reasoning`
- optional `files`

Response fields:

- `task_id`
- `status`
- `pattern`
- `model_responses`
- optional `consensus`
- `duration_ms`

## 2. Recommended Integration Strategy

### Recommendation

Integrate the backend with the orchestrator over HTTP, not by importing its
Python modules.

### Why this is the thinnest viable approach

- the orchestrator already exposes a stable-enough FastAPI interface
- direct Python imports would couple this project to browser automation,
  sessions, database setup, and internal module changes
- HTTP keeps the AB test backend independent and replaceable
- the project requirements already call for a configurable local endpoint and
  graceful fallback

### Preferred endpoint for MVP

Use `POST /api/gk/orchestrate` as the primary integration target for the LLM
adapter.

Reasoning:

- it is synchronous, so our backend can make one request and parse one response
- it already supports selecting a single model or orchestration pattern
- it returns structured model outputs immediately
- it avoids implementing polling logic in the first integration step

### Claude-specific calling strategy

For this project, the narrowest useful initial mode is:

- endpoint: `POST /api/gk/orchestrate`
- pattern: `single`
- model: `Claude Sonnet 4.6`
- reasoning: `true` by default

This maps well to the project requirement that LLM is used only for:

- risk analysis
- contextual recommendations
- hypothesis wording improvement
- human-readable explanations

### Fallback option

If later we need stronger reliability or comparison logic, the adapter can add
an alternate path to:

- `POST /orchestrate` with a selected reliability level and optional model

That should remain optional because it adds task polling, larger latency, and a
wider response surface.

## 3. Backend Module Plan

The backend should keep orchestrator-specific behavior isolated to the planned
LLM layer.

### Phase-aligned module layout

#### Phase 1

Create only the backend skeleton:

- `app/backend/app/main.py`
- `app/backend/app/config.py`
- `app/backend/app/api/routes/health.py`
- `app/backend/app/schemas/`
- `app/backend/tests/`

No orchestrator integration should be implemented in this phase.

#### Phase 2

Add deterministic statistics modules only:

- `app/backend/app/stats/binary.py`
- `app/backend/app/stats/continuous.py`
- `app/backend/app/stats/duration.py`
- `app/backend/app/services/calculations_service.py`

No LLM dependency here.

#### Phase 3

Add warning and heuristic modules:

- `app/backend/app/rules/catalog.py`
- `app/backend/app/rules/engine.py`

Still no LLM dependency.

#### Phase 4

Add deterministic design composition:

- `app/backend/app/schemas/report.py`
- `app/backend/app/schemas/warnings.py`
- `app/backend/app/services/design_service.py`

This phase should produce a complete report even when AI is unavailable.

#### Phase 5

Add the orchestrator-facing adapter and parser:

- `app/backend/app/llm/adapter.py`
- `app/backend/app/llm/prompt_builder.py`
- `app/backend/app/llm/parser.py`

Suggested responsibilities:

- `adapter.py`
  - call local HTTP endpoint
  - handle timeout
  - detect unavailable orchestrator
  - normalize response into project schema
- `prompt_builder.py`
  - convert report context into a constrained structured prompt
  - explicitly ask for sections required by `FR-10`
- `parser.py`
  - parse orchestrator output into:
    - `brief_assessment`
    - `key_risks`
    - `design_improvements`
    - `metric_recommendations`
    - `interpretation_pitfalls`
    - `additional_checks`

#### Phase 6 and later

Expose separate API routes so the frontend can clearly distinguish:

- deterministic calculations
- heuristic warnings
- AI advice

## 4. Proposed Communication Contract for This Project

The AB test backend should treat the orchestrator as an external local service.

### Suggested adapter configuration

Configuration values:

- `ORCHESTRATOR_BASE_URL`
  - default: `http://localhost:8001`
- `ORCHESTRATOR_TIMEOUT_SECONDS`
  - initial recommendation: `60` to `120`
- `ORCHESTRATOR_PATTERN`
  - default: `single`
- `ORCHESTRATOR_MODEL`
  - default: `Claude Sonnet 4.6`
- `ORCHESTRATOR_REASONING`
  - default: `true`

### Suggested request payload for MVP

```json
{
  "query": "<structured prompt built from experiment context>",
  "pattern": "single",
  "model": "Claude Sonnet 4.6",
  "reasoning": true
}
```

### Suggested response normalization

The backend adapter should normalize the orchestrator response into an internal
shape similar to:

```json
{
  "provider": "local_orchestrator",
  "model": "Claude Sonnet 4.6",
  "status": "completed",
  "raw_text": "<selected response text>",
  "duration_ms": 12345,
  "warnings": []
}
```

The parser should then convert `raw_text` into the structured AI advice schema
expected by the report generator.

## 5. Risks and Unclear Areas

### Integration risks

- The orchestrator depends on browser automation, not a stable provider API.
- Successful calls depend on valid Perplexity sessions.
- Actual model names are UI-facing strings and may change.
- Response time is variable and can be much slower than normal API-based LLM
  calls.
- The orchestrator supports many patterns, but not all are necessary for this
  product. Scope creep is likely if the adapter tries to support them all.

### Technical risks

- `api.main.py` contains a stale docstring example mentioning port `8010`, while
  config and server docs point to `8001`.
- Existing tests in the orchestrator reference multiple ports (`8000`, `8001`,
  `8002`), which suggests some historical drift.
- The orchestrator returns free-text model output. Structured parsing for this
  project will need strict prompt design and defensive parsing.
- The `single` pattern is simplest, but it still runs through browser
  automation and may fail for reasons unrelated to prompt quality.

### Product risks

- This project requires deterministic math first. It must never block core
  output on orchestrator availability.
- AI advice may sound authoritative even when the upstream orchestration path is
  flaky; the UI and API must label it as advisory.
- Claude access is indirect through Perplexity, so "Claude Sonnet 4.6 Thinking"
  in product docs should be treated as a deployment assumption, not a hard
  protocol guarantee.

### Unclear areas to validate later

- Whether Perplexity currently exposes the exact model label expected by the
  orchestrator in all sessions.
- Whether `reasoning=true` consistently maps to the intended "Thinking" mode for
  Claude in current UI flows.
- Whether the synchronous `POST /api/gk/orchestrate` route is stable enough
  under repeated local calls from another backend service.
- Whether the orchestrator is expected to be started manually or should only be
  consumed when already running.
- What prompt/response format gives the most reliable structured output for
  `FR-10`.

## 6. Development Plan Based on `docs/HISTORY.md`

### Phase 0 status

Completed in analysis form:

- repository documentation studied
- local orchestrator analyzed
- integration direction selected
- architecture risks documented

### Phase 1

Implement backend skeleton only:

- FastAPI app entrypoint
- config loader
- `/health` endpoint
- minimal schemas
- test scaffold

Exit criteria:

- backend starts locally
- `/health` responds
- basic tests run

### Phase 2

Implement deterministic statistical engine:

- binary metric sample size
- continuous metric sample size
- duration estimation
- input validation and tests

Exit criteria:

- deterministic calculations pass tests
- invalid inputs handled explicitly

### Phase 3

Implement rules engine:

- warning catalog
- rule evaluation service
- tests for MVP warning scenarios

Exit criteria:

- key warnings generated for realistic bad setups

### Phase 4

Implement deterministic report composition:

- report schemas
- design assembly service
- fallback report with no AI dependency

Exit criteria:

- full report can be built without orchestrator

### Phase 5

Implement local orchestrator adapter:

- HTTP client wrapper
- timeout and connection failure handling
- prompt builder for structured AI advice
- parser for normalized result
- graceful fallback when orchestrator is down

Exit criteria:

- AI advice is optional
- backend remains functional without orchestrator

### Phase 6

Implement core API endpoints:

- calculations endpoint
- design endpoint
- AI advice endpoint
- project CRUD endpoints
- export endpoints

Exit criteria:

- local end-to-end backend flows work

### Phase 7

Implement storage:

- SQLite setup
- save/load/update flows

Exit criteria:

- projects persist locally

### Phase 8

Implement frontend form:

- wizard input flow
- validation
- API integration

Exit criteria:

- user can complete and submit experiment form

### Phase 9

Implement results UI:

- deterministic calculations section
- warnings section
- AI advice section
- export actions

Exit criteria:

- results clearly separate math, heuristics, and AI output

### Phase 10

Polish:

- error states
- empty states
- run instructions
- beginner-friendly UX cleanup

Exit criteria:

- project is understandable and runnable locally

## 7. Recommended Implementation Constraints

To stay aligned with the current project requirements:

- do not import orchestrator internals into this repository
- do not use LLM for any statistical calculations
- keep orchestrator access behind one adapter boundary
- treat orchestrator output as optional advisory content
- prefer small incremental phases exactly as defined in `docs/HISTORY.md`
