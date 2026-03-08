# Starter Prompts for Codex

## 1. Repo study prompt

```text
Read all files in docs/ first.
Then study the repository structure.
Then give me:
1. a short summary of the project,
2. the implementation risks,
3. the proposed phase-1 plan,
4. what you need to inspect inside D:\Perplexity_Orchestrator2 to integrate the local orchestrator.
Do not implement yet.
Write the answer in beginner-friendly language.
```

## 2. Skeleton prompt

```text
Implement only Phase 1 from docs/BUILD_PLAN.md.
Follow docs/AGENT_INSTRUCTIONS.md.
Keep the architecture simple.
After implementation:
1. list changed files,
2. explain how to run locally,
3. update docs/progress.md.
```

## 3. Statistical engine prompt

```text
Implement only Phase 2 from docs/BUILD_PLAN.md.
Use deterministic code only.
Do not use LLM for calculations.
Add tests for binary and continuous metrics.
Keep formulas and assumptions explicit.
After implementation update docs/progress.md.
```

## 4. Rules engine prompt

```text
Implement only Phase 3 from docs/BUILD_PLAN.md.
Create a warning catalog and a rules engine.
Cover at least the required MVP warnings from docs/IMPLEMENTATION_SPEC.md.
Add tests.
Update docs/progress.md.
```

## 5. Orchestrator integration prompt

```text
Study D:\Perplexity_Orchestrator2 first.
Figure out the thinnest viable way to call Claude Sonnet 4.6 Thinking through the local orchestrator.
Then implement only the backend adapter layer and graceful fallback.
Do not redesign the whole app.
Explain what assumptions you made.
Update docs/progress.md.
```

## 6. Frontend prompt

```text
Implement only the current frontend phase from docs/BUILD_PLAN.md.
Make the interface beginner-friendly.
Clearly separate deterministic calculations, warnings, and AI advice in the UI.
Do not over-design.
Update docs/progress.md.
```
