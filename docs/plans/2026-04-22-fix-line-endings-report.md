# Fix Line Endings Report

Date: 2026-04-22

## Summary

- Added `.gitattributes` with repository-wide `LF` normalization and explicit `CRLF` exceptions for Windows scripts.
- Patched `scripts/generate_frontend_api_types.py` so `--check` compares raw bytes and normal writes always use `newline="\n"`.
- `git add --renormalize .` did not stage mass text churn on this `HEAD`: the tracked blob for `app/frontend/src/lib/generated/api-contract.ts` was already `LF`; only the local Windows working tree copy was `CRLF`.
- Rewriting `app/frontend/src/lib/generated/api-contract.ts` with the generator converted the working tree file back to `LF` without a content diff.

## Staged Diff Stat Before Commit

```text
 .gitattributes                                     |  23 ++++
 docs/plans/2026-04-22-fix-line-endings-report.md   |  50 +++++++
 .../codex-tasks/2026-04-22-cx-fix-line-endings.md  | 144 +++++++++++++++++++++
 scripts/generate_frontend_api_types.py             |   5 +-
 4 files changed, 220 insertions(+), 2 deletions(-)
```

## `file` Output

Before:

```text
D:\AB_TEST\app\frontend\src\lib\generated\api-contract.ts: ASCII text, with CRLF line terminators
```

After:

```text
D:\AB_TEST\app\frontend\src\lib\generated\api-contract.ts: ASCII text
```

## Verify

- `python scripts/generate_frontend_api_types.py --check`:
  - before the rewrite, after the byte-compare patch: exit `1`, `api-contract.ts is out of date`
  - after `python scripts/generate_frontend_api_types.py`: exit `0`, `api-contract.ts is up to date`
- `scripts/verify_all.cmd --with-e2e`: exit `0`

## CI Reference

- Failing GitHub Actions run kept for history:
  - `https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/24785461941`

## Note

- After push to `main`, the next CI run should stay green on both Ubuntu and Windows because checkout normalization is now explicit and the generator no longer depends on platform newline defaults.
