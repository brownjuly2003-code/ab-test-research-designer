# ADR 0002: Frontend JS bundle budget discipline

**Status:** Accepted
**Date:** 2026-07-23
**Context:** audit F-08 / plan step 8 residual (per-chunk/gzip reporting; no silent ceiling bumps)

## Decision

1. Hard fail budgets stay raw (uncompressed) bytes of `app/frontend/dist/assets/*.js`:
   - entry chunk (`index-*.js`): `ENTRY_CHUNK_BUDGET_BYTES` in `scripts/check_bundle_budget.py`
   - total JS: `TOTAL_JS_BUDGET_BYTES` in the same script
2. The gate **reports** per-chunk raw + gzip sizes and total gzip on every run. Gzip is
   observability only until a separate decision adds a hard gzip ceiling.
3. Raising either hard budget requires:
   - a short ADR (or an amendment to this ADR) stating why code-split / dependency
     removal is insufficient;
   - an explicit PR review note;
   - no “drive-by” limit bump as part of an unrelated feature.

## Rationale

Lighthouse scores vary; raw JS weight is deterministic. Raising the ceiling without
review hides real bundle growth. Soft headroom warnings (under 5% of the total
budget) push cleanup before a formal raise.

## Consequences

- `verify_all` / CI fail when raw budgets are exceeded.
- Maintainers see chunk-level growth and gzip transfer weight without extra tooling.
- Feature work must stay under the current ceiling or open an ADR first.
