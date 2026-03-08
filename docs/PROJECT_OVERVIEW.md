# Project Overview

## Product

AB Test Research Designer is a local web app that helps a PM or analyst design an experiment before launch.

The user provides:

- project context and hypothesis
- experiment setup and traffic split
- primary, secondary, and guardrail metrics
- operational constraints and risk context

The system returns:

- deterministic sample-size and duration estimates
- feasibility warnings and assumptions
- a structured experiment design report
- optional AI advice from a local orchestrator

## Scope

### In scope

- multi-step experiment wizard
- deterministic binary and continuous metric calculations
- feasibility/risk rules
- combined analysis endpoint
- local save/load/update/delete for projects
- analysis and export history per project
- project comparison from saved snapshots
- Markdown and HTML export

### Out of scope

- production analytics integrations
- real experiment execution
- live metric ingestion
- Bayesian or sequential engines
- multi-user collaboration

## Architecture

### Frontend

- React wizard and result surfaces
- generated TypeScript contracts from backend OpenAPI
- local draft persistence via browser storage

### Backend

- FastAPI routes for analysis, projects, history, compare, and export
- deterministic services separated from LLM logic
- SQLite repository for projects, analysis runs, and export events

### AI layer

- optional local orchestrator via adapter boundary
- advisory only; deterministic math never depends on LLM output
- retry/backoff and structured fallback responses

## Core principles

- deterministic math first
- explainability before polish
- local-first workflow
- graceful degradation when the orchestrator is unavailable
- small typed contracts across frontend and backend

## Runtime assumptions

- backend runs locally on `127.0.0.1:8008`
- frontend dev server runs locally on `127.0.0.1:5173`
- optional orchestrator remains a separate local service

## Primary docs

- `README.md` for setup and daily usage
- `docs/DATA_CONTRACTS.md` for payloads and API shapes
- `docs/HISTORY.md` for implementation timeline and current verification baseline
