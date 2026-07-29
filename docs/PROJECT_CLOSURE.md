# Project closure

Scope freeze date: 2026-07-27.
Closure status updated: 2026-07-29.

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

## External closure status

The closing code is published through exact SHA
`58f48b147e0963c768dce90b66dd3be78e2c86f6`.

Completed on that SHA:

- [Tests run 30430078244](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30430078244)
  is terminal `success`, including Ubuntu and Windows verification;
- [dependency-audit job 90505047047](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30430078244/job/90505047047)
  reports no known backend vulnerabilities and zero frontend/docs-site npm
  vulnerabilities;
- [PostgreSQL job 90505047072](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30430078244/job/90505047072)
  passed all 24 contract tests;
- [Docker job 90505047149](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30430078244/job/90505047149)
  passed the secure compose flow;
- [CodeQL run 30430078276](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30430078276)
  passed for Python and JavaScript/TypeScript; open code-scanning alerts are
  zero;
- [docs run 30430078277](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30430078277)
  passed audit, test, build, and Pages deployment.

The project remains a closure candidate until these owner-gated items are
complete:

- Dependabot PRs `#129`–`#134` receive a final one-by-one disposition;
- a final release/tag is built and its GHCR image/release evidence passes;
- the public Hugging Face demo is verified on the closing release or explicitly
  retired.

Push, PR mutations, release, and deploy require explicit owner authorization.
Publishing a later documentation-only commit creates a new exact SHA and
therefore requires fresh CI/CodeQL/dependency/PostgreSQL/Docker evidence.

## Preserved local artifacts

The `.playwright-mcp/` evidence, HTML presentations/explainers,
`docs/data-flow.html`, and the three local plan files remain untracked and are
not part of the closing product tree.
