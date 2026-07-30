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

Keep these references distinct:

| Role | SHA / identity | Meaning |
|---|---|---|
| **v1.3.1 published release** | `bb314ae15c86eaf2ade77d3a111a66030b77573e` | Annotated tag `v1.3.1`; GitHub Release, Actions, and GHCR evidence recorded in [Published release v1.3.1](#published-release-v131). |
| Last exact-SHA **pre-release code/CI closure baseline** | `58f48b147e0963c768dce90b66dd3be78e2c86f6` | Earlier code-closure gate set (Tests / CodeQL / dependency-audit / PostgreSQL / Docker) retained for history; superseded for publication by the release SHA above. |
| **Audited implementation HEAD** (pre-tag) | `a906ed2d3c6bf9e0409c3262f02f1add5d119cfc` | Implementation tip audited for the pre-publication documentation review (after 2026-07-29 dependency merges on `main`). |

Core audit/code work is closed on the audited tree. The GitHub-only publish
gates for **v1.3.1** are **completed** (tag, Release, green Actions on the
release SHA, GHCR). Remaining unfinished items are explicitly optional future
reopen work — not missing local implementation for the 2026-07-23 audit plan.

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

## Owner decision: Hugging Face publication path retired (2026-07-30)

Completed by owner decision on 2026-07-30 — **not** a verified public HF demo:

- Hugging Face is **not** a publication, acceptance, or demo target for this
  project going forward.
- The public-HF-demo branch of the closure gate is **explicitly retired**.
- GitHub-to-HF automation (`.github/workflows/deploy-hf.yml`,
  `space-maintenance.yml`) is removed from the active tree; recovery is via
  Git history only.
- Optional legacy snapshot code may remain in the repository for historical
  reference; it is **not** a supported publication target and is **outside**
  closure. No active HF setup/deploy/recovery recipe is part of the gate.

## Published release v1.3.1

Owner-authorized **GitHub-only** publication for **v1.3.1** is **complete**.
Hugging Face remains retired (see above); it is not a publication or demo target.

| Item | Evidence |
|---|---|
| Release commit | `bb314ae15c86eaf2ade77d3a111a66030b77573e` |
| Annotated tag | `v1.3.1` |
| GitHub Release | https://github.com/brownjuly2003-code/ab-test-research-designer/releases/tag/v1.3.1 |
| Tests workflow | [run 30534255932](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30534255932) — `success` on the release SHA (dependency audit, repo hygiene, local-runner smoke, Docker, frontend coverage, statistical oracle, Ubuntu full verification, Windows verification, locale content, PostgreSQL verification, Lighthouse, metrics badges) |
| CodeQL workflow | [run 30534256094](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30534256094) — `success` on the release SHA |
| GitHub Pages / docs workflow | [run 30534256023](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30534256023) — `success` on the release SHA |
| GHCR publish workflow | [run 30534834319](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/30534834319) — `success` (image build, critical-vulnerability scan, multi-arch publish) |
| GHCR image | `ghcr.io/brownjuly2003-code/ab-test-research-designer` |
| GHCR tags | `v1.3.1`, `1.3.1`, `latest`, `sha-bb314ae` |
| Immutable digest | `sha256:1d02d8a09f790815127ef5c43792f3a3a809a0f872e6fa9434ed6ea957e8baac` (all four tags resolve to this digest) |

**Fresh local release gate before tagging** (not a claim that Docker was available
locally):

```text
python scripts/verify_all.py --with-e2e --with-coverage --with-lighthouse --artifacts-dir .ci-artifacts
```

All checks passed: backend 1390 passed / 21 skipped / 91.50% coverage (88%
threshold); frontend 69 files / 437 tests; build and bundle budget passed
(1,092,023 raw / 308,360 gzip, 5.0% headroom); Playwright E2E and local smoke
passed; Lighthouse performance 96, accessibility 100, best practices 100,
SEO 82; fresh npm audits for frontend runtime, ESLint toolchain, and docs-site
reported 0 vulnerabilities; docs-site tests 8/8 and production build 23 pages.
Docker was **not** installed locally; the release SHA's GitHub Docker and
PostgreSQL jobs passed (see Tests workflow above).

**Verified local runtime (supported demo):**

```bash
python scripts/run_local.py --bootstrap   # first run only
python scripts/run_local.py
# optional: python scripts/run_local.py --seed-demo
# open http://127.0.0.1:8008
```

## Future / reopen candidates (optional, not core-audit blockers)

Reopen only with an explicit product request:

- Bayesian practical MWE rule (`P(δ > MWE)`);
- explicit OpenAPI `decision_policy` fields on experiment create/update;
- export/history policy evidence polish;
- stricter React lint / React Compiler adoption and `exhaustive-deps` error
  promotion;
- Playwright RTL smoke for ComparisonDetails;
- cold-start restore ordering before `ProjectRepository` construction;
- worst-case compute wall-time benchmarks.

## Preserved local artifacts

The `.playwright-mcp/` evidence, HTML presentations/explainers,
`docs/data-flow.html`, and the three local plan files remain untracked and are
not part of the closing product tree.
