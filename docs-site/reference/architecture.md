# Architecture

The product is intentionally split so deterministic sizing, optional AI advice, delivery plumbing, and local persistence can evolve independently.

```mermaid
flowchart LR
    UI[React SPA] --> API[FastAPI]
    API --> Calc[Deterministic calculators]
    API --> Compare[Comparison service]
    API --> Hooks[Webhook service]
    API --> LLM[Optional LLM adapters]
    API --> DB[(SQLite workspace)]
```

Historical implementation notes and milestone context live in [docs/HISTORY.md](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/HISTORY.md).

{% include-markdown "../../docs/ARCHITECTURE.md" start="## Frontend" %}
