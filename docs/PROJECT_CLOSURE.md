# Project closure

Scope freeze date: 2026-07-27.

## Closing scope

The closing release keeps the product described in `README.md`: deterministic
experiment design and sizing, the shipped post-hoc statistical repertoire,
live-experiment monitoring, local SQLite/PostgreSQL storage, optional local or
caller-keyed LLM advice, seven locales, exports/integrations, and the existing
security, accessibility, backup, CI, and release controls.

After the closing release this scope is feature-frozen. New methods, research
experiments, and product extensions require a separately authorized project.

## Plan disposition

- The 78 tracked files under `docs/plans/` are implementation history, design
  records, and superseded proposals. Their unchecked boxes are not an active
  backlog.
- The local untracked plans dated 2026-06-17, 2026-06-25, and 2026-06-29 are
  preserved without modification. They are research input, not closing-release
  commitments.
- Optional statistical methods or refinements not listed as shipped in
  `README.md` are `future`, not unfinished AB_TEST work.
- Manual NVDA/JAWS validation remains out of scope as already recorded in the
  public roadmap; automated accessibility gates remain part of the release.

This disposition closes the open-ended roadmap without claiming that every
historical proposal was implemented.

## Required external closure gates

The project is only a closure candidate until all of these are complete:

- the five local commits are published to `main`;
- CI is green on the exact closing SHA; the local PostCSS lock fix must remove
  `GHSA-r28c-9q8g-f849` from the remote dependency-audit job;
- all open Dependabot PRs receive a final one-by-one disposition;
- a final release/tag is built and its GHCR image/release evidence passes;
- the public Hugging Face demo is either verified on the closing release or
  explicitly retired.

Push, PR mutations, release, and deploy require explicit owner authorization.

## Preserved local artifacts

The `.playwright-mcp/` evidence, HTML presentations/explainers,
`docs/data-flow.html`, and the three local plan files remain untracked and are
not part of the closing product tree.
