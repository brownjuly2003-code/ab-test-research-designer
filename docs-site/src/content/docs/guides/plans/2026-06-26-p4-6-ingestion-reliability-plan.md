---
title: "P4.6 — Ingestion reliability (Phase 4 · 2026-06-26)"
---

# P4.6 — Ingestion reliability (Phase 4 · 2026-06-26)

The final Phase 4 slice. The dedup primitives already exist and are correct (`record_exposures`
first-exposure-wins via `UNIQUE(experiment_id, user_id)` + `ON CONFLICT DO NOTHING`;
`record_conversions` idempotency via `UNIQUE(experiment_id, idempotency_key)`). What was missing is
**proof that those invariants hold at production scale under retried (at-least-once) delivery**, plus
operator documentation of batch semantics, throughput, and limits. This is a **verification + docs**
slice: **no code change, no schema bump, no API/i18n change**.

## Why this matters
Production ingestion is at-least-once: clients retry on timeout, queues redeliver. If a redelivered
10k batch were recorded twice it would double one arm's exposures and manufacture a false SRM, or
double-count conversions and inflate the effect. The `ON CONFLICT DO NOTHING` dedup must absorb the
full retry at scale, returning `recorded == 0` on an exact replay and keeping the stored totals flat.

## Invariants verified (load tests, N = 10 000)
- **Exposure idempotency under load** — 10k unique exposures → `recorded == 10000`; re-ingesting the
  identical batch → `recorded == 0, deduplicated == 10000`; `exposures_total` stays 10k (not 20k).
- **Arm-balance invariant** — a duplicate redelivery does not inflate either arm (the false-SRM
  guard): per-variation counts are unchanged after the replay.
- **Conversion idempotency under load** — 10k keyed conversions → `recorded == 10000`; replay →
  fully deduplicated.
- **Mixed batch / partial dedup at scale** — a 10k batch where half the users were already seen →
  `recorded == 5000, deduplicated == 5000`, and the accounting invariant
  `received == recorded + deduplicated` holds; `exposures_total == 10000`.

## Documentation (docs/PRODUCTION.md — new "Ingestion" section)
- Batch semantics and the `{received, recorded, deduplicated}` response contract.
- Idempotency keys for conversions (retries safe; events without a key are always recorded).
- Capacity / limits: `AB_MAX_REQUEST_BODY_BYTES` (default 1 MiB) bounds a single batch → chunk large
  backfills; each batch is one transaction (all-or-nothing per request); throughput scales with the
  PostgreSQL backend.

## Steps
- [ ] `test_ingestion_load.py` (new) — the four invariant tests above at N = 10 000.
- [ ] `docs/PRODUCTION.md` — add the "Ingestion: batch semantics, idempotency, limits" section.

## Verify / gate
Serial Windows gate: backend pytest (new load tests green + no regressions), ruff / mypy untouched
(no app code changed), contract / locale untouched. Then push → PR → CI → merge under the standing
"реши сам" mandate. Closes Phase 4 (P4.1–P4.6 all in main); deploy gated on "задеплой".
