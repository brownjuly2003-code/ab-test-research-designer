---
title: "P4.4 — Bot / fraud filter (Phase 4 · 2026-06-26)"
---

# P4.4 — Bot / fraud filter (Phase 4 · 2026-06-26)

Builds on P4.3 (identity resolution in the primary rollup). Removes bot / fraudulent participants
from every aggregate, by two sources, and surfaces an "N filtered" indicator. Like P4.3 it **corrects
the primary rollup** but is safe via the **no-op-when-empty** property.

## Two exclusion sources
- **Manual deny-list** — new table `excluded_users (experiment_id, user_id, exclusion_reason, source,
  created_at)`, `UNIQUE(experiment_id, user_id)` first-write-wins (first reason sticks). Ingested via
  `POST /api/v1/experiments/{id}/exclusions`. `source = 'manual'`.
- **Automatic rate-spike** — a canonical user with more than `BOT_CONVERSION_EVENT_THRESHOLD` (= 100)
  conversion events on the analyzed metric is an automation / instrumentation artifact (a human does
  not convert hundreds of times). Computed at read time (not stored — the raw events are never
  mutated). The threshold is deliberately high so ordinary traffic never trips it.

## Composition with P4.3 (exclude the canonical id, after resolution)
The exclusion is applied **inside** `get_experiment_analysis_aggregates`, on the canonical id (resolved
through `identity_map`), so a bot that spans anonymous + login is one excluded unit. Two `NOT EXISTS`
anti-joins on the resolved `arm`:
- `excluded` CTE — manual deny-list resolved to canonical.
- `spike` CTE — `SELECT cuser FROM conv_resolved GROUP BY cuser HAVING COUNT(*) > ?`.

Both portable on SQLite + Postgres (`NOT EXISTS`, `HAVING COUNT`, `?`→`%s`). **No-op-when-empty:** an
empty deny-list and no user over the threshold → byte-identical to the P4.3 rollup (the high threshold
keeps all existing tests green). Read-time filter — raw events are never deleted, so exclusion is
reversible and auditable.

## Indicator
`get_exclusion_summary(experiment_id, metric_name)` → `{total_filtered, manual_filtered,
rate_spike_filtered}`, counting only **exposed** canonical users actually removed, split **disjointly**
(manual takes precedence; `manual_filtered + rate_spike_filtered == total_filtered`). Surfaced as
`LiveExclusionBlock` (status active / inactive — hidden when nothing filtered), mirroring P4.2/P4.3
indicators. i18n ×7.

## Scope
- Resolved + filtered: `get_experiment_analysis_aggregates` (the decision-critical SRM + effect path).
- Left raw (documented follow-up, same as P4.3): holdout / event-timing / stratified / ingestion
  summary reads. `decision_service` untouched.

## Done (all steps)
- [x] `constants.BOT_CONVERSION_EVENT_THRESHOLD = 100`.
- [x] `excluded_users` table in **both** backends (SQLite `_create_execution_tables` + Postgres
  `_init_db` — P4.3 lesson: Postgres has a separate `_init_db`). `schema_version` 13 → 14
  (+ diagnostics tests 13→14).
- [x] `record_exclusions` + `spike`/`excluded` anti-joins in `get_experiment_analysis_aggregates` +
  `get_exclusion_summary`.
- [x] `POST /api/v1/experiments/{id}/exclusions` + collect summary in `_compute_live_stats`.
- [x] `ExclusionEvent` + `ExclusionIngestRequest`; `LiveExclusionBlock` + `LiveStatsResponse +=
  exclusions`. Regenerated `api-contract.ts` + `docs/API.md`.
- [x] Frontend `ExclusionBlock` + `lib/api` re-export + i18n ×7 (`results.liveStats.exclusion*`).
- [x] Tests: repository (+4: no-op equality · manual deny-list removes + raw kept + first-write-wins ·
  rate-spike auto-filter · manual ∩ spike disjoint) · live-stats (+3: inactive · active · endpoint
  e2e) · `test_postgres_backend` (+ exclusion round-trip, skip on Win) · vitest (+2: active · hidden).

## Verify / gate
Serial Windows gate: ruff, mypy --strict (66), backend pytest (701 passed / 17 skip), tsc, vitest
(LiveStatsSection 16), vite build < 500 kB, contract --check, locale 14. The Postgres exclusion
round-trip (NOT EXISTS anti-joins + CASE/EXISTS summary) is skipped on Windows and validated by CI
`verify-postgres`. Then push → PR → CI → merge under the standing "реши сам" mandate; deploy gated on
"задеплой".
