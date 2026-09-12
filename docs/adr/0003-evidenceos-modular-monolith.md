# ADR 0003: EvidenceOS as a modular monolith

- Status: Accepted
- Date: 2026-08-21
- Scope: AB_TEST_new foundation
- Superseded in part by ADR 0005.

## Context

AB_TEST уже содержит зрелое статистическое ядро, live ingestion, SQLite и
PostgreSQL backends, FastAPI/React surfaces и сильный test corpus. Его основные
архитектурные ограничения находятся не в формулах, а в границах:

- `ExperimentInput` и `projects.payload_json` одновременно являются authoring,
  execution и persistence моделями;
- HTTP routes напрямую собирают statistical, repository и LLM calls;
- `ProjectRepository.__getattr__` скрывает широкий динамический интерфейс;
- долгие вычисления ограничиваются process-local admission, но не имеют
  durable lifecycle;
- UI организован вокруг wizard/results, а не вокруг protocol/preflight/review.

Переписывание в микросервисы разрушило бы проверенный oracle и добавило бы
распределённые транзакции до подтверждения product-market fit.

## Decision

AB_TEST_new остаётся одним deployable приложением, но получает строгие
внутренние модули:

1. `evidence.domain` — Protocol, Run, Finding, Estimate, Decision, Artifact;
2. `evidence.application` — compile, freeze, preflight, build, verify, import;
3. `evidence.ports` — узкие ProtocolStore, EvidenceStore, ArtifactStore,
   DataSourceAdapter, StatsKernel и JobStore;
4. `evidence.adapters` — SQLite/PostgreSQL, DuckDB/files, legacy stats, ZIP,
   FastAPI и CLI;
5. существующие `stats/` и результаты AB_TEST — неизменяемый legacy oracle за
   `StatsKernel` adapter.

`main.py` остаётся composition root. Новые domain/application modules не
импортируют FastAPI, React, concrete repository backends или environment
configuration. Новые use cases получают явные typed dependencies; динамический
`__getattr__` не используется.

Долгие операции получают persistent `jobs` table, lease, heartbeat,
cancellation и budgets. Первый runtime остаётся single-instance; отдельный
queue broker и multi-instance control plane не вводятся.

Frontend получает URL-addressуемые surfaces Portfolio, Protocol Studio,
Preflight Lab и Evidence Review. Zustand остаётся для draft/preferences;
server state и job state не смешиваются с authoring state.

## Consequences

### Positive

- существующие scientific tests продолжают защищать математику;
- CLI, API и UI вызывают одни use cases;
- SQLite остаётся first-class local mode, PostgreSQL — durable production mode;
- ports позволяют добавить DuckDB без протаскивания SQL в domain;
- boundaries можно проверять import/contract tests.

### Costs

- некоторое время существуют legacy и evidence модели параллельно;
- нужен явный converter и compatibility projection;
- новый persistence слой нельзя быстро добавить в `ProjectRepository` как ещё
  один mixin — потребуются typed repositories;
- schema migration и UI navigation выполняются поэтапно.

## Rejected alternatives

- **Microservices now:** нет подтверждённой независимой нагрузки или командных
  границ; стоимость выше пользы.
- **Rewrite the statistics kernel:** уничтожает главный проверенный актив и
  затрудняет локализацию расхождений.
- **Keep extending payload_json:** не обеспечивает стабильную identity,
  immutability, lineage и referential integrity.
- **Graph database first:** relational edge table достаточно до измеренной
  проблемы поиска или масштаба.

## Fitness rules

- `evidence/domain` imports no FastAPI, repository adapter or OS environment.
- Every write use case uses an explicit port and one transaction boundary.
- Frozen protocol revisions and succeeded runs are append-only through the API.
- No UI-only rule may decide a statistical verdict.
- Legacy converter tests must pass before any legacy read path is retired.
