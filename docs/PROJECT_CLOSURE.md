# Project closure

Scope freeze date: 2026-07-27.
Documentation review date: 2026-07-30.
Closure status updated: 2026-07-30.

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
- The executable tracked plan `plan_sol_23_07_26` (audit `audit_gpt_23_07_26.md`)
  is **closed locally** for all mandatory code items F-01 through F-10 core.
- The local untracked plans dated 2026-06-17, 2026-06-25, and 2026-06-29 are
  preserved without modification. They are research input, not closing-release
  commitments.
- Optional statistical methods or refinements not listed as shipped in
  `README.md` are `future`, not unfinished AB_TEST work.
- Manual NVDA/JAWS validation remains out of scope as already recorded in the
  public roadmap; automated accessibility gates remain part of the release.

This disposition closes the open-ended roadmap without claiming that every
historical proposal was implemented.

## Implementation baselines (2026-07-30)

Keep these three references distinct:

| Role | SHA / identity | Meaning |
|---|---|---|
| Last exact-SHA **code/CI closure baseline** | `58f48b147e0963c768dce90b66dd3be78e2c86f6` | Last commit whose Tests / CodeQL / dependency-audit / PostgreSQL / Docker evidence is explicitly documented below as the code-closure gate set. |
| **Audited implementation HEAD** | `a906ed2d3c6bf9e0409c3262f02f1add5d119cfc` | Implementation tip audited for this documentation review (after 2026-07-29 dependency merges on `main`). |
| **This documentation update** | commit that contains the three tracked docs (`docs/PROJECT_CLOSURE.md`, `plan_sol_23_07_26`, `CHANGELOG.md`) | Documentation-only refresh; its hash is not known until that commit is created. |

Core audit/code work is closed on the audited tree. Remaining unfinished items
are owner/external publish gates or explicitly optional future reopen work —
not missing local implementation for the 2026-07-23 audit plan.

## Code/CI closure evidence on `58f48b14`

Completed on exact SHA `58f48b147e0963c768dce90b66dd3be78e2c86f6`:

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

Also present on audited HEAD relative to the earlier audit plan residual set:
stable centered moments for continuous/CUPED/ratio aggregates; CUPED and ratio
`analytical_population_v1` alignment (`e18e2a3d`, `530c6db2`); PostgreSQL
`conversions.value` DOUBLE PRECISION (migration 17 already on baseline
`58f48b14`, not a post-baseline delta); compromised Astro lock replacement
(`7e5f2657`); no-Docker local runner; documentation closure record
`b50c855c` (docs-only exact-SHA record, not a dependency merge); and the five
Dependabot merges listed below (`#129`, `#130`, `#131`, `#132`, `#134`).

## Dependabot disposition (local history + live check)

Proven merged on `main` by local history (squash subjects):

- `#129` — frontend minor/patch group (`42abcde2`);
- `#130` — actions minor/patch group (`751b7409`);
- `#131` — `actions/setup-python` 5.6.0 → 7.0.0 (`7199e010`);
- `#132` — `actions/setup-node` 4.4.0 → 7.0.0 (`76c9128c`);
- `#134` — `@astrojs/starlight` (`a906ed2d`).

Live read of `#133` on 2026-07-30: **closed without merge**
([PR #133](https://github.com/brownjuly2003-code/ab-test-research-designer/pull/133),
`build(deps-dev): bump hypothesis … pip-minor-patch group`). It is not an open
disposition backlog item.

Workflow runs observed on audited HEAD `a906ed2d` (push event): Tests
[30443633237](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30443633237)
`success`; CodeQL
[30443633193](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30443633193)
`success`; docs-site Pages
[30443633196](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30443633196)
`success`. A full re-statement of dependency-audit / PostgreSQL / Docker job IDs
for `a906ed2d` is not claimed beyond those completed runs.

## Owner-gated external items (not local code blockers)

The product remains release-candidate until the owner completes:

- a final release/tag with GHCR image and release evidence;
- public Hugging Face demo verification on the closing release, or explicit
  retirement;
- any destructive HF snapshot corrupt/rollback drill (requires a disposable
  repo/token; production demo state is out of bounds per
  `docs/RELEASE_CHECKLIST.md`).

Push, release, tag, GHCR publish, and HF mutation still require explicit owner
authorization. Publishing this documentation update (or any later commit)
creates a new exact SHA and therefore needs fresh CI evidence on that SHA
before treating it as the next code/CI closure baseline.

## Future / reopen candidates (optional, not core-audit blockers)

Reopen only with an explicit product request:

- Bayesian practical MWE rule (`P(δ > MWE)`);
- explicit OpenAPI `decision_policy` fields on experiment create/update;
- export/history policy evidence polish;
- stricter React lint / React Compiler adoption and `exhaustive-deps` error
  promotion;
- Playwright RTL smoke for ComparisonDetails;
- cold-start restore ordering before `ProjectRepository` construction;
- worst-case compute wall-time benchmarks;
- disposable Hugging Face recovery drills beyond the in-repo snapshot suite.

## Preserved local artifacts

The `.playwright-mcp/` evidence, HTML presentations/explainers,
`docs/data-flow.html`, and the three local plan files remain untracked and are
not part of the closing product tree.
