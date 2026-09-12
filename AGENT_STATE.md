# Agent state

Last updated: 2026-09-11

Start with `docs/SESSION_HANDOFF.md`. Git and tracked state override stale chat. When present, detailed local planning lives at gitignored `archive/plans/plan_23_08_2026.md`; historical notes live under `archive/handoffs/`.

## Snapshot

| Item | Fact |
| --- | --- |
| Repo | `D:\AB_TEST_new`, branch `main` |
| Published | Before K-05, `origin/main` = `5dea15cc` (the measured K-01 result recorded in the entry documents); `origin` is the private `ab-evidence` repository. The local K-05 documentation commit is intentionally not pushed in this session. `public` is fetch-only (`no_push`). Verify the live state rather than trusting this row. |
| Full backend baseline | 2026-09-08 on `66abac76`: the backend suite **2047 passed, 25 skipped, no deselect** in 1540.43s, with the abx package split and its functions decomposed, alongside `ruff check app/backend/app app/backend/tests scripts` and strict mypy (183 files). Read the count and the exit status, not the wall clock: this run shared the machine with a CI watch, and the same suite measured 1197.66s on `6d57ed92` and 813.93s on `56a1dfc0` the same day. The superseded J-02 baseline was the same day on `56a1dfc0`: **2046 passed, 25 skipped, no deselect** in 813.93s, alongside `ruff check app/backend/app app/backend/tests scripts` and strict mypy (177 files). This is the first full run with the DuckDB budget test selected; see the phase-J CI-fix note. The superseded H-phase baseline was 2026-09-07: **1994 passed, 25 skipped**, one deselect, in 1195.9s on tree `69e95649fd`. That tree is `80f36493` plus the two entry documents; the later commits in this phase change only Markdown, `package-lock.json` and the two frontend config files, each re-verified by its own step. Supersedes the T-13 `445c2879` / 541.4s baseline, which predates the widened lint scope and the frontend gate steps. Later focused gates do not replace it. |
| Phase | Phase 0 and **all of phase A** are complete, as are B-01 through B-08 and C-01 through C-08. D-01 and D-03 are complete locally (`244459a9`, `cccbd426`). Phase-A commits: A-01, A-02, A-05 (`445c2879`), A-03 (`66edcf7c`), A-04 (`d44165d0` plus `0d7d7f45`), A-06 (`9928a71e`), A-07 (`1e91d0d1`), A-08 (`c663c454`), A-09 (`f4015866`), A-10 (`bce7013b`), A-11 (obsolete — see Durable boundaries; residual closed in `89c666d8`). |
| Next | `plan_07_09_26.md` continues the phase numbering with H (gate and publication), I (trust-hardening), J (external track) and K (maintainability); it answers the audit `audit_fable_07_09_26.md` (F-01…F-15). **Phases H and I are complete**: H-01 `d78e9840`, H-04 `0d92bb42`, H-03 `1266acd7`, H-05 `80f36493`, H-02 below; I-02 `85d4e91a`, I-03 `35bfb375`, I-04 `6a4f99d6`, I-05 `1b41efe9`, I-01 `16f3b7c6` + `b6c29daf`. **J-01 and J-02 are complete** (`ff8df25c` CI fix, `c704b484` the Gate 3 aggregator, `56a1dfc0` `source validate`), which closes the J-code half of the plan. What remains in J is calendar work: J-04 three real practitioner sessions, then J-05 the Gate 3 verdict from their records. **K-01, K-02, K-04, and the authorized K-03 scope are complete** (the commits below). **K-05 is complete in the local documentation commit**: `bundle-container.md`, `lineage-binding.md`, and `privacy-policy.md` contain 31 executable scenarios, each bound to a focused pytest nodeid; those selectors collected and passed 42 tests on 2026-09-11. No safe local code or documentation item remains in the plan. Q7 is settled: K-03 took its documented default, `evidence/reserved/`, for two of three modules and raised **Q9** for the third. J-03 needs Q8 — it publishes externally. D-02 and D-04 still need real external practitioners and cannot be fabricated; D-01/D-03 are complete but unpublished (Q8 gates publication). E/F/G stay shut until two external users return for a second run, and Gate 3 is `PIVOT` with zero cycles. Containers run only on the Mac. |
| Safety | Preserve the gitignored local `.trialmark/` workspace. Preserve stash commit `9a45f24d`. Push to the private `origin` is authorized (decision Q5, 2026-09-07): no force, no tags. `public` stays `no_push`. |
| Product | Trialmark; `.tmk`; `application/vnd.trialmark.bundle+zip`; identity is the manifest digest, not the filename. |
| Gate 3 | `PIVOT`; zero partner cycles. See `archive/handoffs/pilot-acceptance.md`. |

## Completed C-01/C-02 statistical preflight

- Preflight now generates binary null p-values internally from aggregate arm counts by frozen-seed conditional permutation, records their digest and count, and applies a KS threshold of `0.01` independent of experiment alpha. The minimum is 200 permutations and the default is 1000.
- Externally asserted calibration remains explicit and fails with `AA_CALIBRATION_ASSERTED_FAILED`; internal failures retain `AA_CALIBRATION_FAILED`.
- Fresh verification: simulated A/A **18 passed** including the 100-seed ≤1% false-alarm check; all preflight tests **119 passed**; project Ruff and strict mypy (**173 files**) passed.
- Empirical power now bootstraps historical binary outcomes through the bounded `DuckDbFileAdapter`, using frozen PCG64 with 500…100000 resamples (default 1000). The profile keeps a distribution digest and aggregate results, never historical rows or query text.
- `internal_bootstrap` power is computed from data; `upstream_asserted` remains explicit and retains the legacy consistency guard. Recommendation fields are derived from the same baseline/effect contract without changing the shared sizing APIs reserved for C-04.
- Fresh C-02 verification: empirical-power **38 passed**; all five preflight files **124 passed**; project Ruff and strict mypy (**173 files**) passed; `git diff --check` passed.

## Completed C-03/C-04 sequential and allocation-aware sizing

- Live O'Brien–Fleming evaluation occurs only at predeclared looks; between looks the existing mSPRT remains the continuous readout. The 20 000-path / 200-read regression measures type-I **0.0510** versus the old **0.07885**.
- Sequential design now uses one numerically inverted Lan–DeMets OBF construction, with spending and boundaries aligned and at most 20 looks (`aa15bf71`).
- Binary, continuous, ratio, duration, and CUPED sizing now honour the planned allocation; deterministic 90/10 simulations achieve requested power (`0ce610fb`).
- Fresh C-04 verification: sequential **37 passed**, consumers/live **44 passed**, allocation focused **82 passed**, integration **275 passed**, oracle **97/97**, Ruff and strict mypy (**173 files**) passed.

## Completed C-05/C-06 validation

- Oracle now has **106/106 checks across 39 cases** (`5a317041`) using independent Statsmodels/SciPy/NumPy or null-simulation references; constant-table/self comparisons are removed.
- The ASOS walkthrough (`a68e531b`) blocks metric-role conflict, 90/10 assignment imbalance, and late exposure, then completes CLI run → decision → offline verify.
- C-06 gates: focused **3 passed**, related CLI/pipeline/preflight **106 passed**, Ruff and strict mypy passed. Mac Docker acceptance was unavailable: daemon off; no Windows container runtime ran.

## Completed C-07/C-08 evidence profiles

- C-07 added schema-backed `methods/profile.json`, bound method/version and guarantees to the stats-kernel build digest, and taught manifests, persistence, CLI, and lineage verification the `method` role.
- Evidence schema v3 preserves v2 rows while adding `method`; README generation remains deterministic. C-07 commits: `d9bbe7a4`, `73c97ee6`, `91a73c42`.
- C-08 (`97a2f5b0`) emits the final human decision as an unsigned DSSE envelope containing an in-toto Statement v1. Its subject SHA-256 binds the parent analysis bundle; the existing decision record is the Trialmark predicate.
- Offline verification reports the statement and checks its subject against both `predicate.cites_bundle_id` and manifest `supersedes`; a foreign subject fails `lineage/unbound_reference`. Legacy proposed decisions remain compatible JSON. Signing and Sigstore remain out of scope.
- Fresh C-08 gates: schema/run/persisted **49 passed, 1 deselected**; verifier/content binding **102 passed**; persisted/storage/pipeline **48 passed**; dirty-safe CLI/demo **30 passed, 2 deselected**; stats-kernel **22 passed**. Ruff and strict mypy (**174 files**) passed. Clean-HEAD CLI/demo acceptance **2 passed**.
- Preserve the local `.trialmark/` workspace, stash commit `9a45f24d`, and the no-push boundary.

## 2026-09-06/07 collection fix, git-state independence, and A-05

- `927bd15a` (2026-09-06) deleted `app/backend/tests/test_trialmark_upload_contract.py`. `015212e8` (2026-09-02) had deleted `app/backend/tests/test_evidence_workbench.py` but left this importer of `_configure_app`, `_ready_bundle`, and `_use_asos_control_archive`. From `015212e8` until `927bd15a` the backend suite failed at collection with `ModuleNotFoundError: No module named 'app.backend.tests.test_evidence_workbench'`, so no full backend run was possible for four days; only focused gates ran in that window. The route it exercised, `/api/v2/bundles:verify`, is gone from `app/backend/app/`; `test_persisted_workbench_routes.py` already requires the served path set to be disjoint from it. T-21 restored a full gate on tree `844e070ce4`: 1971 passed, 25 skipped, 1 deselected, 378.2s.
- `8eda1b15` (2026-09-07) made `test_c06_demo.py`, `test_abx_cli.py`, `test_persisted_workbench_seed.py`, and `test_record_trialmark_demo.py` independent of git tree state. Each module now has a fixed `StatsKernelBuild` and an autouse fixture patching `app.backend.app.evidence.pipeline.load_stats_kernel_build`, matching `test_evidence_pipeline.py`. The corrected-demo test replaces `examples.demo.run_demo._run_cli` with an in-process shim; `app/backend/tests/test_c06_in_process_cli.py` pins SystemExit-to-returncode mapping, environment and settings restoration, and parity against measured subprocess exit codes. The slice gives up end-to-end coverage of the successful path through a real CLI process: a test cannot both spawn a subprocess and be independent of tree cleanliness. Remaining subprocess coverage is `test_recorder_help_runs_from_the_repository_root` and the error paths. `test_evidence_stats_kernel.py` is untouched and still owns dirty/missing-provenance behaviour.
- `445c2879` (2026-09-07) is A-05. `write_stats_kernel_build_info` and `load_stats_kernel_build` now document the `BUILD_INFO.json` stamp: canonical JSON with a lowercase 40- or 64-character `git_commit`, `dirty=false`, and `tracked_digest` equal to the Git-path `build_digest`, so a runtime image and a clean checkout yield the same bundle identity. Git remains a development fallback. The fallback error wrap covers only a failing `rev-parse --show-toplevel`; a dirty tree or an untracked kernel source keeps `stats kernel Git provenance is unavailable`. New `app/backend/tests/test_stats_kernel_build_info.py`. T-13 full gate: tree `e03caa7a93`, 541.4s, same DuckDB deselect.

## 2026-09-07 phase-A closure

- Phase A is finished. Six of its tasks were already implemented in the tree and had simply never been closed in the MyFlow ledger; each was verified by running its own acceptance tests before being recorded as done. A-03 `66edcf7c` (privacy scanner; `test_evidence_abx_privacy.py`, 17 tests, covers camelCase/PascalCase key splitting, ≥7-digit numerics in `id|subject|user|phone|msisdn|account` fields, E.164 and RU phone forms, octet-validated IPv4 and compressed IPv6, POSIX and Windows absolute paths). A-06 `9928a71e` (`-k parity_mutation` runs the six required mutations). A-07 `1e91d0d1` (`-k p_b_beats_a_boundary`, 53 boundary configurations). A-08 `c663c454` (Newcombe interval replaces the `(0, 0)` degenerate CI; relative lift is `None` when `p1 == 0`). A-09 `f4015866` (`app/backend/app/evidence/_common.py` is the single home of `sha256_hex`, `canonical_json_bytes`, `canonical_digest`, the I-JSON parser and `fsync_directory`).
- A-04 was completed by `0d7d7f45`, on top of `d44165d0`. A principal whose role is outside the run's frozen `decision.approval_policy.roles` now raises `RoleNotPermittedError` — deliberately not a `ValueError`, so the workbench routes' `except (EvidenceRunConflictError, ValueError)` arm cannot swallow it into a 409 — and both write routes catch it ahead of that arm and answer **403 with error code `role_not_permitted`**. `Principal` gained an optional `role`; a principal that declares none still inherits the frozen policy's first approval role, so no previously accepted write is now refused. **Do not claim A-04 is enforced end to end in production:** that 403 path is reachable only by injecting a principal, because no credential carries a role yet. Wiring roles into API keys is unstarted work.
- A-10 met its target. The 22 `test_evidence_*.py` files run in 61.11s on a quiet tree (277 passed, 1 skipped, 1 deselected) against a ≤120s goal and a 308s baseline, via `bce7013b` plus A-05's `BUILD_INFO.json` work, which removed the per-case `git init` outright rather than merely scoping it per module.
- A-11 is obsolete rather than done: its subject, `app/backend/app/evidence/workbench.py`, was deleted by `015212e8`, and `app/frontend/src/test/e2e-workbench.spec.ts` carries no finding-code expectations at all. Its one residual — an unchecked `cast(FindingCode, code)` in `preflight.py` — was closed by `89c666d8`, which annotates the `counters` tuple as `tuple[tuple[int, FindingCode, str, str], ...]` so mypy checks each literal where it is written and drops the cast.
- `docs/specs/` now exists and holds the project's **first** durable capability spec, `docs/specs/workbench-authorization.md` (2 requirements, 5 scenarios), written in the A-04 slice. State the gap honestly: 17 of the 24 tasks in this plan were delivered with no durable requirement, so most of what phase 0 and phase A decided survives only as code, tests and these notes.

## 2026-09-07 phase H — gate and publication

- **H-01 `d78e9840`.** `tsc --noEmit` had been red since `015212e8` (2026-09-02) and no local gate saw it. `target`/`lib` are now ES2021, and the full gate runs `npm --prefix app/frontend run typecheck` and `run test:unit`. The lesson generalizes: a gate is only evidence for what it actually runs, and "the tests pass" said nothing about types because Vitest transpiles through esbuild.
- **H-04 `0d92bb42`.** `docs-site/public/demo/**` (derived, ~3 MB), `research/**` (moved to `archive/research/`) and `scripts/update_ai_state_new.py` (personal, absolute path outside the repo) left the tracked tree; `check_repo_hygiene.classify` now knows all three.
- **H-03 `1266acd7`.** README, architecture §12.2 and the CHANGELOG describe the `trialmark.aggregate-binary` CSV profile and `pilot-session`, which had existed since `c655aed2`/`b34e68e8` with zero documentation. `examples/pilot/` is a runnable protocol + CSV; the README's CSV block is byte-identical to it.
- **`85129136` (not in the plan).** Publishing the first external-pilot bundle failed with `sensitive_value: detected phone_number` on `rendered/report.html`. The protocol's own digest contained `80493398107`, which the Russian branch of the phone pattern reads as a phone number. Measured: 0.415% of random SHA-256 digests match, three digests per report, so ~1.2% of bundles were unpublishable at random — and deterministically, so an affected protocol never recovers on retry. Any 64-hex digest is now neutralized before the phone scan only. **This class of bug is invisible to the ASOS fixtures**: they are three fixed bundles whose digests happen to be clean. Any privacy pattern matching raw digits needs an argument about digests, not a passing fixture.
- **H-05 `80f36493`.** `app/backend/tests` is inside the ruff gate. The 21 `B905` sites were decided individually: `strict=True` where equal length is the assertion, `strict=False` for the `zip(seq, seq[1:])` sliding windows. mypy still covers only `app/backend/app`.
- **H-02.** `origin/main` now matches local `main`. Before the push, `npm audit --audit-level=high` was red in both npm roots — `nanoid`/`undici` in `app/frontend`, `postcss` and two others in `docs-site` — which `dependency-audit` would have failed regardless of this work; `npm audit fix` cleared both with patch-level lockfile bumps and no `package.json` change.
  The first push then turned three jobs red and they were fixed without weakening a gate:
  `dependency-audit` (pypdf 6.14.2 -> 6.16.1, `GHSA-4qc7-h8xc-9jjr`), the zip64 transport
  tests (CPython 3.14.7 hardened `zipfile._EndRecData64`, so the two suites now branch on
  `_stdlib_reads_archive` and accept `invalid_archive` where the stdlib refuses to open the
  forged archive at all), and the ASOS fixture comparison (CPython 3.14 links a different
  zlib, so the test compares uncompressed members rather than ZIP bytes, per ADR 0004).
  CodeQL and the Pages deploy are now scoped with `if: github.repository == '...'`: code
  scanning and Pages both live on the public repository, so on the private mirror they ran
  to a guaranteed 403. CodeQL therefore reports `skipped` on the mirror, not `success`;
  enabling it there needs GitHub Advanced Security, a paid add-on, and that is a spend
  decision for the owner. Two more fix commits closed the slice: `2b05d443` moved every
  p-value tail to `erfc` and quantised the ASOS benchmark p-value, which is what made
  `verify (ubuntu-latest)` red; `832923f0` bounded the vitest worker count by
  `availableParallelism()`, which is what made `verify (windows-latest)` red twice on
  different files. At `832923f0` the `Tests` run is 12 jobs green, `Deploy docs site` is
  green, and `CodeQL` is `skipped` by the repository guard -- H-02's criterion reads "all
  success", so record the `skipped` honestly rather than counting it as a pass.

## 2026-09-07 phase I — trust-hardening

- **I-02.** The slice as planned was "`config.validate` refuses to build Settings in production without a token", and that would have been a regression. `main._verify_production_auth` already refuses to boot, already accepts the three legitimate bootstraps, and its docstring already says why it is not in config: the third bootstrap is an active write-scoped API key in the database, which config cannot see. Moving the check would have broken exactly the deployment that has retired its admin token. `test_production_auth.py` covers it with seven cases. What was actually missing is the other half of the slice, and that is what shipped: `GET /readyz` now reports `auth_mode`, and an open surface logs a `event=auth_open` warning once at startup instead of appearing as one INFO field among fifteen. The readiness value is stricter than the diagnostics field of the same name — `get_auth_mode` calls an admin-token-only or public-demo deployment "open" although both already reject anonymous mutations, so those get their own names and `open` is reserved for a surface that really is open.

- **I-03.** `AB_ARTIFACT_ROOT` is the one place the artifact tree is named, and `Settings.artifact_root` resolves it to an absolute path once at load. Three call sites -- `routes/workbench.py`, `evidence/cli.py`, `evidence/demo_seed.py` -- each held their own `Path(".trialmark") / "artifacts"`, which resolves against the current working directory, so an API server started somewhere other than where the CLI ran answered 404 for a run that had just succeeded (audit F-05). `pack --run` no longer demands the flag, `/readyz` reports the resolved path and whether it is writable, and `docker-compose.yml` points the variable at the data volume because `/app` belongs to root while the process runs as uid 1000. `test_artifact_root.py` covers it, including the cross-directory regression.

- **I-04.** A finding action names two things, and only one of them was checked first. `record_finding_state` tested the run's state before it looked for the finding, so an unknown `finding_id` on a run that already carried a decision came back 409 "finding actions require a pre-decision run" -- a conflict reported for a resource that does not exist (audit I-04). The existence check now sits directly after the run lookup, and the two state guards keep their relative order behind it. The pre-decision guard is now unreachable for a finding that really is there, because `pipeline` sets `blocked = bool(findings)` and stamps `kind="preflight"` for any run with a finding, while `record_human_decision` refuses anything but `kind="analysis"`; it is kept as a guard against a future format where findings survive into a decided run. `test_finding_not_found_outranks_the_run_state_guards` covers all three run states.

- **I-05 (Q6, variant A).** ADR 0006 freezes the format identifiers: `abx` is the name of the bundle format, Trialmark is the name of the product, and `urn:evidenceos:abx:schema:0.1:*` stays the namespace of format version 0.1. ADR 0005 had deferred them to a "phase B migration" that no decision stood behind. Renaming is not a text substitution: a manifest entry's `schema_id` is inside the canonical bytes the manifest digest covers, and ADR 0004 makes that digest the bundle identity, so a rename rotates every `bundle_id` ever issued and forces the three committed ASOS bundles to be repacked. Thirty-one files carry the string. Variant B (migrating to `urn:trialmark:tmk:*`) stays available and costs about a session; it needs Julia's word, because it is a product-identity call, not a cleanup.

- **I-01.** A decision record now names the provenance of the role it was made under. `decided_by.role_source` is `credential` (the issued API key carries the role -- the only source the service verifies), `asserted` (`trialmark decide --role`, unverified), or `policy_default` (nothing was declared and the frozen policy's first approval role applied). Before this, every decision took the policy default in silence, so a reader could not tell a checked role from a decorative one (audit F-03/F-04). Storage: `api_keys.role TEXT NULL` in the SQLite DDL plus a `migrate_db` `ALTER TABLE`, in the PostgreSQL DDL, and as migration 18 for databases that already exist; `POST /api/v1/keys` accepts `role`; `http_runtime` puts it on the `Principal` together with `role_source="credential"`, and `_principal_identity` refuses to call anything else a credential. `decision.schema.json` (a `STATS_KERNEL_SOURCE_PATHS` member) took the optional field in its own commit `16f3b7c6`, ahead of any run that resolves build identity. Also shipped: `minimum_approvals > 1` is refused with `approval_quorum_unmet` (409 / exit 1) instead of writing one approval against a policy that wants several. `app/backend/tests/test_decision_role_source.py` covers all three sources, both refusals, the report line, and a database created before the column.

- **I close-out.** The I→J gate of `plan_07_09_26.md`, run end to end against the clean tree rather than through tests alone. A real `trialmark run` on `examples/demo/protocol.yaml` produced `run_c47d55c07d3ac469665e1c5b`; deciding it with no `--role` wrote `decided_by = {actor_ref: local-operator, role: benchmark_reviewer, role_source: policy_default}` into the DSSE payload of the child bundle; `--role impostor` exited 1 with `role_not_permitted`; `--role benchmark_reviewer` wrote `role_source: asserted`. The three committed ASOS bundles still verify `valid` under the widened `decision.schema.json`, which is what "the field is optional" has to mean. `GET /api/v2/runs/{id}:bundle` answered 200 with `application/vnd.trialmark.bundle+zip` for that CLI run from a working directory outside the repository, with only `AB_ARTIFACT_ROOT` and `AB_DATABASE_URL` set -- the F-05 regression. The gate's literal production check (`get_settings()` raising without a token) does **not** hold, and must not: I-02 deliberately left that guard in `main._verify_production_auth`, where the database is visible, and `test_production_auth.py` covers the same guarantee with seven cases. Focused selection `-k "role_source or role_not_permitted or approval_quorum or artifact_root or finding_not_found or readyz_auth_mode"`: 20 passed.

## 2026-09-08 phase J — external track

- **CI fix (`ff8df25c`), ahead of J-01.** The Windows leg of the `Tests` run for `b6c29daf` was cancelled at the 20-minute job timeout: pytest went from 38% to 42% in fifteen minutes and that block ends in `F`, which maps to `test_duckdb_file_adapter_enforces_scan_result_and_timeout_budgets`. `_run_bounded` armed a single `threading.Timer` that called `connection.interrupt()` once. DuckDB clears its interrupt flag when a query starts, so an interrupt delivered between arming the timer and execution beginning is discarded -- and at the millisecond budgets `QueryBudget.timeout_ms` accepts, that window is most of the wait. A lost shot left the query unbounded, which is what the timeout exists to prevent. The watchdog is now a thread that keeps interrupting until the operation returns and is joined before the connection closes. `test_duckdb_timeout_survives_an_interrupt_the_engine_never_saw` swallows the first interrupt: on the old code it never finishes (killed at 60s); it now raises `QueryTimeoutError` in ~2.5s. The budget test itself passes 10/10 in ~1.5s each. **The deselect is gone.** Two Windows `verify (windows-latest, --skip-smoke)` legs have since passed -- run `34194681103` for `c704b484` in 10m21s against a 20-minute job timeout, and run `34195927695` for `56a1dfc0` -- and the local full suite ran 2046 passed, 25 skipped in 813.93s with the nodeid selected. The `--deselect` was dropped from the local `.myflow` full-gate command on 2026-09-08.

- **J-01.** `app/backend/app/evidence/gate3.py` measures Gate 3 from the records instead of by hand. `evaluate_gate3(directory)` loads every `<date>-<anon>.md` under it through `load_pilot_record` and returns a frozen `Gate3Report`; `trialmark gate3 --records <dir> [--out <file.md>]` renders it. The report reads nothing but the records -- no clock, no network, no database -- so a cohort always yields the same bytes and the same `report_digest`, which covers every field except itself. Three rules decide what the numbers mean. **One partner is one cycle**: two records from the same `participant_ref` count once toward completed cycles, and the second contributes only if it records reuse. **A criterion nobody measured is never reported as passed**: preflight detection is a property of the engineering suite, not of a partner session, so it is always `unmeasured` and is excluded from the final verdict -- leaving it in would pin every verdict below `continue` forever and hide whether partner evidence arrived. **Absolute-count thresholds can be measured as zero and therefore fail on an empty cohort; rate thresholds have no denominator to rate and stay `unmeasured`.** The verdict is `continue` when the five record-derived criteria pass, `stop` when no partner completed a cycle -- `archive/handoffs/pilot-acceptance.md` is explicit that a second gate with no cycles is STOP, not another PIVOT -- and `pivot` in between. Every verdict exits 0: `stop` is a measurement, not a command failure, and `valid` says only that the report could be produced. A non-record `.md` in the directory is an error rather than a skip, because silently dropping an unparseable record would take a partner out of the denominator; `docs/pilots/.gitkeep` says so. `app/backend/tests/test_gate3.py` covers 14 scenarios including zero, incomplete-only, passing, no-reuse, duplicate participant, a slow cohort failing on the median, the missing directory, byte-identical re-rendering, and the digest recomputed from the rendered JSON block.

- **J-02.** `trialmark source validate --protocol p.yaml --source data.csv` runs the source half of `run` and nothing else -- no repository, no run, no bundle, no writes; `test_source_validate_opens_no_repository_and_writes_nothing` patches `_create_repository` to raise and asserts an empty working directory afterwards. The point of the slice is that a thirty-minute session with a practitioner is not spent debugging a CSV, so the diagnostics had to become actionable, and they did for every caller rather than only this one: a schema mismatch names the expected columns beside the ones the file actually has, a bad row count says how many were found and that the file looks row-level, and a digest mismatch prints both digests. `pipeline.validate_binary_source` is now the single implementation of those checks -- `_load_binary_pipeline_source` calls it -- so the pre-flight and the pipeline cannot drift into disagreeing about whether a source matches its protocol, and `binary_aggregate.metric_definition_digest` is the one place the metric digest is computed. `validate_source_document` takes the `FrozenProtocol` so the check runs against exactly the canonical bytes a later `run` would use.

- **K-01 (2026-09-08).** `app/backend/app/evidence/abx.py` was 2 132 lines
  with 45 top-level definitions and three functions over 300 lines. It is now
  the package `app/backend/app/evidence/abx/`: `_core.py` 278 lines,
  `zip_safety.py` 545, `privacy.py` 107, `lineage.py` 669, `verify.py` 542,
  `pack.py` 125, `__init__.py` 74. The graph is a DAG -- `_core` depends on
  nothing in the package, `zip_safety` and `privacy` on `_core`, `lineage` on
  `_core` and `privacy`, `verify` on all three, `pack` on `verify`,
  `zip_safety` and `_core` -- so there is no cycle to break later.

  The move is checkable rather than trusted: an AST comparison of all 70
  top-level statements before and after reports exactly one difference,
  `_SCHEMA_ROOT`, which climbs one directory because the file is one level
  deeper than the schemas. `__init__.py` re-exports all 28 names the module
  exported, so no importer outside the package changed.

  `STATS_KERNEL_SOURCE_PATHS` lists the seven modules in place of the one, so
  `stats_kernel.build_digest` changed, as it did at `445c2879`. No test pins a
  literal digest, and published bundles need no repacking: a verifier compares
  a bundle's own `methods/profile.json.implementation_digest` against the
  `run.runner.build_digest` inside that same bundle, never against the current
  build. `test_build_identity_hashes_required_sources_lock_and_verified_commit`
  now reads the package directory and asserts the list covers it, so a new
  `abx/` module that nobody registers fails the test instead of silently
  leaving the kernel digest unchanged.

  Five test files needed a one-line change, all of the same kind -- a patch
  target moved to the module where the name is now looked up
  (`abx.pack.os.link`, `abx.pack._fsync_directory`,
  `abx._core.canonical_json_bytes`,
  `abx.zip_safety._sequential_local_header_offsets`) -- plus
  `test_evidence_abx_t20_repair4.py`, whose comment guard now reads every file
  in the package instead of one file.

  **The three long functions were decomposed in the commit after it.**
  `_archive_preflight` (405 lines) became `_scan_local_records`,
  `_check_central_directory`, `_check_archive_trailer` and
  `_check_member_inventory`; `verify_logical_bundle` (311) became
  `_scan_logical_members`, `_inventory_manifest_entries` and
  `_verify_logical_entries`; `_check_references` (483) gave up
  `_check_child_chain`, `_check_queries`, `_check_metric_definitions` and
  `_check_method_profile`, keeping the run-versus-artifact tail inline because
  it reads too many of the resolved id maps to be worth a ten-parameter
  signature. The longest function in the package is now 182 lines, so the
  plan's acceptance criterion is met. Each block moved at its original indent
  with its comments, and the same `errors`/`result` accumulator is threaded
  through the new signatures, so no message, code or ordering changed.

- **K-02 (2026-09-08).** `cli.py` imported the repository, the pipeline,
  `binary_aggregate`, and through them DuckDB, psycopg and numpy, at module
  scope -- so `trialmark verify`, which opens a ZIP and checks digests, paid
  for a query engine it never used. Each of those now loads inside the handler
  that needs it; only `abx` and `redaction` stay eager, because verifying is
  what the command line is for. Measured on the committed `d53f0e.tmk`, seven
  runs each on a quiet machine: median 1.394s before, 0.570s after, against
  the plan's 0.8s target. The one design question was the `except` chain,
  which named exception classes from exactly the modules being deferred.
  `_ERROR_CODES` now resolves them through `sys.modules`, in the order the
  arms used to run in: an exception can only come from a module that is
  already loaded, so an absent entry is proof the error is not that one, and
  nothing is imported in order to classify a failure. `test_abx_cli.py` moved
  its six `monkeypatch.setattr` targets from `cli.get_settings` /
  `cli.ProjectRepository` / `cli.publish_completed_run_abx` to the modules
  that define them, which is where a deferred `from … import …` looks at call
  time.

- **K-04 (2026-09-08).** `scripts/gate_trialmark.py` is the focused gate the
  plan asked for, measured at 166.0s and 156.0s against its 180s target; the
  two runs differ only in which cache was cold, mypy's (35.6s cold, 1.9s warm)
  or Vite's (52.4s cold, 5.9s warm). Its selection is 32 files -- the plan's
  list plus `test_source_validate.py`, `test_cli_cold_start.py`,
  `test_trialmark_bundle_contract.py` and `test_decision_role_source.py`,
  which did not exist or were not named when the plan was written and are
  squarely the same surface. Globs are expanded in Python because only a POSIX
  shell would expand them for pytest, and a pattern that matches nothing raises
  rather than passing: a focused gate that silently tests less than its list
  claims is worse than no focused gate. Time is reported and never enforced.
  Separately, architecture §9.5 now records the three costs that are linear in
  run count and are deliberately not being optimised -- `:bundle` repacking on
  every GET (438 ms), `list_runs` loading each run in full with no pagination,
  and the 83 s demo seed -- and §12.2 lists `source validate` and `gate3`,
  which J-01 and J-02 had added to the CLI without updating the architecture.

- **K-03 (2026-09-08), partial by design.** `dbt_manifest.py`, `legacy.py` and
  the pinned `dbt/manifest/v12.json` are now in
  `app/backend/app/evidence/reserved/`, excluded from the wheel in
  `pyproject.toml` and asserted absent by `check_wheel_payload.py`, whose
  self-test covers a reserved member so the exclusion cannot rot silently.
  Their tests moved to `app/backend/tests/reserved/` and stay in the gate,
  because a reserved module that stops compiling is one nobody can revive.
  `grep -rn "evidence.reserved" app/backend/app --include=*.py | grep -v
  reserved/` is empty and a real wheel build passes with 212 members.

  **`public_pilot_abx.py` was left in place, and this is the open part.** It
  builds `runner.build_digest` from the literal path strings in
  `_RUNNER_SOURCE_PATHS = ("app/evidence/public_pilot_abx.py",
  "app/evidence/public_pilots.py")`, that digest is written into
  `run/run.json`, and `run/run.json` is a manifest entry -- verified by
  reading the committed `d53f0e.tmk`. So moving the file changes the manifest
  digest, which is the `bundle_id` (ADR 0004), for all three published ASOS
  benchmark bundles, and `test_asos_public_pilot_abx.py` pins those three ids
  and archive digests. That is the same class of consequence as Q6 variant B:
  rotating identifiers that have been published. Recorded as **Q9** rather
  than done quietly. Excluding it from the wheel without moving it is the
  cheap alternative if the answer is "do not rotate".

## Decisions

| # | Status |
| --- | --- |
| Q1 | Closed: private `ab-evidence` is `origin`; public legacy repo is not written. |
| Q2 | Resolved: Trialmark / `.tmk`. Schema `$id`, `urn:evidenceos:abx:*`, module names, and `abx_version` are format identifiers, not deferred renames — frozen by ADR 0006 until a bundle format version 0.2. |
| Q3 | Open after phase B; default is a light product track. |
| Q4 | Open after phase C; default is `evidence-0.1` with an explicit README split. |
| Q9 | **Open, raised 2026-09-08 by K-03.** Move `public_pilot_abx.py` into `evidence/reserved/` and accept that all three published ASOS benchmark `bundle_id`s rotate, or leave it in place and exclude it from the wheel by path? Its `runner.build_digest` is derived from `_RUNNER_SOURCE_PATHS`, which holds its own path string, and that digest is inside `run/run.json`, a manifest entry. Default until answered: leave it in place. |

## Durable boundaries

- Two-sided p-values come from a survival function, never from `1 - cdf`. `standard_normal_sf` (`app/stats/binary.py`), `t_sf` (`app/stats/student_t.py`) and `chi_square_sf` (`app/stats/srm.py`) are the entry points; `2.0 * standard_normal_sf(abs(z))` is exact, because multiplying by two only changes the binary exponent. The old form cancels: about two significant digits are gone at z = 2.2, it is 7% wrong at z = 8, and it returns exactly `0.0` above z = 8.3, so the most decisive results were the ones it reported worst. All 23 sites were converted on 2026-09-07; a new one is a regression.
- Anything whose digest is published must not depend on the host libm. `erf`/`erfc`/`lgamma` are not correctly rounded, so Windows and Linux differ in the last one or two digits, and that is enough to rotate a bundle identity per platform. The ASOS packer quantises its p-value to 12 significant digits (`_benchmark_p_value`, `app/evidence/public_pilot_abx.py`); every other float in those documents is sums, quotients and `sqrt`, which are bit-exact everywhere, and `NormalDist.inv_cdf` is a pure-Python rational approximation. Adding a transcendental to a packed document needs the same treatment or the same argument.

- The cancelled worker/full-legacy-lineage slice stays cancelled. Worker work starts only in phase F. Do not start Evidence Graph, MCP, federation, scale work, or the old writer → QA-delegate pipeline.
- Accepted risk `F-T-06-15`: ZIP central-directory-only metadata such as `external_attr`, `create_version`, and `internal_attr` is not authenticated. Consumers using third-party unzip must not honour ZIP file-type bits.
- Root pytest basetemp belongs under `.tmp/`; keep only the newest three. The full gate has no deselect since 2026-09-08. Do not raw-retry a timeout without a narrowed hypothesis. When measuring a hang, `timeout` without `-k` leaves the orphan alive and every later run inherits a saturated machine -- a whole set of flakiness numbers can be self-inflicted that way.
- Two gates, and they are not interchangeable. **Focused gate**: `python scripts/gate_trialmark.py` -- ruff, strict mypy, the 32 evidence/CLI/persisted/pilot test files, `tsc`, and the preflight Vitest files. Measured 166.0s and 156.0s on 2026-09-08 against a 180s target (the gap is whichever cache was cold, mypy's or Vite's). It is for the loop between edits and clears nothing. **Full gate** -- the one a push needs: `python -m ruff check app/backend/app app/backend/tests scripts`; `python -m mypy`; backend pytest over `app/backend/tests` with nothing deselected; `npm --prefix app/frontend run typecheck`; `npm --prefix app/frontend run test:unit`. The two frontend steps were added on 2026-09-07 (H-01) because the gate had been blind to the frontend: `tsc --noEmit` was red from 2026-09-02 (`015212e8` used `String.replaceAll` under `lib: ES2020`) while every local gate reported green, because Vitest transpiles through esbuild and never type-checks. CI does run `tsc`, so the miss would have surfaced only on the first push. Both steps are `level: full` and carry `if_exists: app/frontend/node_modules`, so a checkout without frontend dependencies skips rather than fails. `npm --prefix <dir> run <script>` runs with the package directory as cwd; `npm --prefix <dir> exec` does not, so gate steps must use `run` and a package script.
- Vitest timeouts are a CPU-contention symptom, not a test defect. Two distinct ones are on record. Locally, one cold run (no warm Vite transform cache) failed five files with `[vitest-pool-runner]: Timeout waiting for worker to respond` in 557s while the warm-cache suite passed 446/446 twice — 193s at `--maxWorkers=4` and 219s at 8; that one is a cold-start fork-spawn timeout, so re-run before investigating. On CI, `verify (windows-latest)` failed twice on 2026-09-07 with `Test timed out`, on different files each time (`a11y-results`/`a11y-sidebar`, then `SequentialBoundaryChart`/`SurvivalCurveChart`/`a11y-webhooks`): 165s of wall clock carried 541s of test CPU and 452s of environment CPU, because a flat `maxWorkers: 8` is a cap on a workstation but an oversubscription on a 4-vCPU runner. Since 2026-09-07 the bound is `Math.max(2, Math.min(8, availableParallelism()))` — the same throughput, since the suite is already CPU-saturated, at a fraction of the per-test latency — and the 34 per-test `}, 15000)` overrides are gone, because they predated `testTimeout: 30000` and had quietly become ceilings *below* the global one. Different files failing on each run is the signature; a single file failing repeatedly is not this.
- `STATS_KERNEL_SOURCE_PATHS` (paths relative to `app/backend/`) is `app/evidence/abx/__init__.py`, `app/evidence/abx/_core.py`, `app/evidence/abx/lineage.py`, `app/evidence/abx/pack.py`, `app/evidence/abx/privacy.py`, `app/evidence/abx/verify.py`, `app/evidence/abx/zip_safety.py`, `app/evidence/stats_kernel.py`, `app/evidence/stats_kernel_abx.py`, `app/evidence/contracts/schemas/abx/0.1/amendments.schema.json`, `app/evidence/contracts/schemas/abx/0.1/common.schema.json`, `app/evidence/contracts/schemas/abx/0.1/decision-statement.schema.json`, `app/evidence/contracts/schemas/abx/0.1/decision.schema.json`, `app/evidence/contracts/schemas/abx/0.1/estimate.schema.json`, `app/evidence/contracts/schemas/abx/0.1/finding.schema.json`, `app/evidence/contracts/schemas/abx/0.1/manifest.schema.json`, `app/evidence/contracts/schemas/abx/0.1/method-profile.schema.json`, `app/evidence/contracts/schemas/abx/0.1/metric.schema.json`, `app/evidence/contracts/schemas/abx/0.1/protocol.schema.json`, `app/evidence/contracts/schemas/abx/0.1/run.schema.json`, `app/evidence/contracts/schemas/abx/0.1/source.schema.json`, `app/schemas/api/__init__.py`, `app/schemas/api/_results.py`, `app/services/results_service.py`, `app/services/results/__init__.py`, `app/services/results/binary.py`, `app/services/results/common.py`, `app/services/results/dispatch.py`, and `app/stats/binary.py`. Any uncommitted edit to a member makes real Git provenance unavailable process-wide, so anything that resolves a real build identity fails while the edit is dirty. Since `8eda1b15` the four CLI/demo/seed modules inject a fixed `StatsKernelBuild`, so a kernel-source slice's full gate is reachable while its edit is still uncommitted: T-13 gated green on tree `e03caa7a93` with `app/backend/app/evidence/stats_kernel.py` dirty, and committed it afterwards as `445c2879` (tree `6415705419`). Any new test that resolves a real build identity through the CLI or the demo must patch `load_stats_kernel_build` itself, or it fails on a dirty kernel source. `test_evidence_stats_kernel.py` deliberately does not patch it and owns dirty/missing-provenance behaviour.
- The project gate lints `app/backend/app app/backend/tests scripts` since 2026-09-07 (H-05): the 81 errors that had kept tests out of scope are fixed (58 I001 and 2 F401 by `ruff --fix`, 21 B905 by hand). Of the B905 sites, 14 became `strict=True` because equal length is part of what the test asserts, and 7 became `strict=False` because `zip(seq, seq[1:])` is a deliberate sliding window. mypy still type-checks only `files = ["app/backend/app"]` (`pyproject.toml`); extending it to the tests is unscoped backlog, not done work.
- **A task's stated state is not evidence; the tree is.** On 2026-09-07 six open plan tasks turned out to be already implemented and merely unclosed, and three task details pointed at files that do not exist: `app/backend/app/evidence/workbench.py` (deleted by `015212e8`), `app/backend/app/evidence/http_runtime.py` (never existed — the module is `app/backend/app/http_runtime.py`), and `app/backend/app/results/` (moved to `app/backend/app/services/results/` by `38ea4e42`). Diff a task's detail against HEAD, and run its own acceptance test, before dispatching anyone at it. Re-implementing finished work is the most expensive failure this document can cause.
- A reviewer that greps only this repository will call framework internals dead code. `original_router` is a real FastAPI 0.139.2 attribute (`fastapi/routing.py:1573`, the `_IncludedRouter` dataclass): in this version `include_router` does not flatten sub-routes into `app.routes`, so a test that walks routes to find a dependency must recurse through it. Verify such a claim against the installed package, not the repository.

## Exact committed ASOS identities

Dataset DOI `10.17605/OSF.IO/64JSB`, CC BY 4.0. Source Parquet SHA-256 `bdf88b27185d3f7e65912cbb421129a32ae347c2fb0d9442fe54d74266551524` is not committed. Fixtures are `public_benchmark`, `partner_approved=false`, `statistical_validity=not_asserted`.

| Experiment | Fixture SHA-256 | Archive SHA-256 | Bundle ID |
| --- | --- | --- | --- |
| `d53f0e` | `b190ce2e295e72e79bc77289af38d7e3d8c95373350262a5711fce5c3dc9a78b` | `5fb64dd809aba8e701314874679d7d56794a411e1b177ab3265f2de5b54ce1f0` | `sha256:60fee3fae970b607fec89bec8d6e8fc423d55a42f6d3f02b679436c281b694b3` |
| `26bd38` | `f71c7a8b617ff000ce61f6fd6692a48f7632eee065dc8321bdf62ac0a54452b3` | `76a9e2411ec8254d77b0ec7200b3bde2adec0cd061481949a029be92d7395536` | `sha256:de3b8372fc60bfb8049455d738febde068a062386de8f9253d32177c0025c942` |
| `834947` | `8d345cc311258bb8e6e413e99f7c80ce3c0110219f42c254c9b5cf0c4f3d9953` | `4b747b3f81c2862e8c374089c1b627d5bde0bc7639084d6a6f7c0d230e3148ec` | `sha256:0f6654308d5e89ceb89a780498c79079049b5c087fcb444e444d9a722266602a` |
