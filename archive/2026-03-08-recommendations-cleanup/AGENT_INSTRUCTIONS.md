# Agent Instructions

This repository is implemented using phased development.

Always follow this reading order:

Always read progress.md before reading other documentation.

1. progress.md
2. README.md
3. docs/BUILD_PLAN.md

Only open other docs if required.

---

## Core Rules

1. Implement one phase at a time
2. Never redesign architecture without explicit reason
3. Prefer small localized changes
4. Avoid modifying more than 5 files per step
5. Deterministic calculations must NOT use LLM
6. LLM is only used for:
   - risk analysis
   - recommendations
   - explanation

---

## Workflow

For each phase:

1. implement functionality
2. verify structure
3. update progress.md
4. summarize changes

---

## LLM Integration

LLM provider:

Claude Sonnet 4.6 Thinking

Accessed through local orchestrator:

D:\Perplexity_Orchestrator2

The coding agent must first study this orchestrator
before implementing the LLM adapter.

---

## Stability Rules

Avoid:

- massive refactoring
- unnecessary file creation
- changing existing API contracts

Prefer:

- incremental implementation
- clear module boundaries