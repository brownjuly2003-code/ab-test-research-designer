# Session handoff

Last verified: 2026-09-11

Session entry. `AGENT_STATE.md` and Git are authoritative. When present, detailed local planning is in gitignored `archive/plans/plan_23_08_2026.md`; historical detail is in Git and `archive/handoffs/`.

## Resume

1. Work in `D:\AB_TEST_new` on `main`; begin with `git status --short --branch` and `git log -1 --oneline`.
2. C-07 is complete in `d9bbe7a4`, `73c97ee6`, and `91a73c42`; C-08 is complete in `97a2f5b0`. The gitignored `.trialmark/` workspace is unrelated and must be preserved.
3. Preserve stash commit `9a45f24d`. Push to the private `origin` (`ab-evidence`) is authorized since 2026-09-07 (decision Q5): plain `git push origin main`, no force and no tags. `public` stays fetch-only (`no_push`). The 23.08 prohibition was written to protect the public repository and outlived its reason; 61 unpushed commits with no second copy were the larger risk.
4. **Phase A is complete** — A-01 through A-11, finished 2026-09-07 (`66edcf7c`, `d44165d0` plus `0d7d7f45`, `9928a71e`, `1e91d0d1`, `c663c454`, `f4015866`, `bce7013b`; A-11 obsolete, residual closed in `89c666d8`). **Phase H of `plan_07_09_26.md` is also complete** — H-01 `d78e9840`, H-04 `0d92bb42`, H-03 `1266acd7`, H-05 `80f36493`, plus the unplanned privacy-scanner fix `85129136`, and H-02 published the branch and then drove CI green: `dependency-audit` (pypdf
`GHSA-4qc7-h8xc-9jjr`), two CPython 3.14 differences (hardened `zipfile._EndRecData64`; a
different zlib, so ASOS bundles are compared by uncompressed member rather than ZIP bytes),
the optional oracle dependencies, `if: github.repository` guards on CodeQL and the Pages
deploy, and the statistical tail fix below. **Phase I is also complete** — I-02 `85d4e91a`, I-03 `35bfb375`, I-04 `6a4f99d6`, I-05 `1b41efe9`, and I-01 in two commits: `16f3b7c6` for `decision.schema.json` alone, ahead of any run that resolves build identity, then `b6c29daf` for the rest. **J-01 and J-02 are complete** — `ff8df25c` fixes the DuckDB deadline that cancelled the Windows CI leg, `c704b484` adds `evidence/gate3.py` plus `trialmark gate3`, and the commit after it adds `trialmark source validate`. That closes the J-code half; the rest of J is calendar work (J-04 three real practitioner sessions, then J-05 the Gate 3 verdict from their records) and must not be simulated. **K-02 is also complete** — the evidence CLI defers every import a command does not use, and a cold `trialmark verify` went from a 1.394s median to 0.570s. **K-04 is also complete** -- `scripts/gate_trialmark.py`, the focused gate, plus the known-limitation and CLI-surface records in the architecture. **K-03 is complete for two of its three modules** -- `dbt_manifest` and `legacy` are in `evidence/reserved/` and out of the wheel; `public_pilot_abx` stayed, because moving it rotates three published bundle ids (open question **Q9**). **K-01 is complete in its mechanical half** -- `abx.py` is now the package `evidence/abx/` (`_core`, `zip_safety`, `privacy`, `lineage`, `verify`, `pack`), proved a pure move by an AST comparison of all 70 top-level statements, with `STATS_KERNEL_SOURCE_PATHS` updated in the same commit. The three functions still over 200 lines were decomposed in the commit after it, so the package's longest function is 182 lines. **K-05 is complete in the local documentation commit**: the three durable specs under `docs/specs/` define 31 executable scenarios, each bound to a focused pytest nodeid; those selectors collected and passed 42 tests on 2026-09-11. No safe local code or documentation item remains in the plan. Three things still need Julia's word and must not be assumed: **Q8**, publishing the D-01/D-03 article (J-03), because it is an external publication; **Q9**, moving `public_pilot_abx`, because that rotates three published bundle ids; and **Q6 variant B**, migrating the namespace to `urn:trialmark:tmk:*`, because it rotates every bundle identity ever issued — variant A shipped as ADR 0006 and is the standing answer until she says otherwise. **Q7** has a documented default (K-03 moves the dead modules to `evidence/reserved/`) and needs no confirmation. See `AGENT_STATE.md` §§ "2026-09-07 phase-A closure", "2026-09-07 phase H" and "2026-09-07 phase I" for what each commit delivered. A-04's 403 path is no longer reachable only by injecting a principal: an issued API key can carry a role.
5. For any future container acceptance, use the Mac. Do not install or run WSL, Docker, containers, or equivalent on this Windows machine.

## C-01/C-02 delivered contract

- `simulate_aa_profile` generates binary null p-values from aggregate arm counts by conditional hypergeometric permutation with the protocol's frozen seed. Profiles retain a p-value vector digest and count, not input rows.
- The run budget is at least 200 permutations and defaults to 1000. KS calibration uses a fixed `0.01` threshold independent of protocol alpha.
- Upstream asserted calibration is labelled explicitly and uses `AA_CALIBRATION_ASSERTED_FAILED`; internally generated calibration uses `AA_CALIBRATION_FAILED`.
- `simulate_empirical_power_profile` reads bounded historical 0/1 outcomes through `DuckDbFileAdapter`, bootstraps achieved power with frozen PCG64, and requires 500…100000 resamples (default 1000).
- Internal profiles contain aggregate distribution digests and derived power/remediation fields only. Upstream asserted profiles remain explicit and retain their consistency guard.

## C-03/C-04 delivered contract

- `_build_sequential_block` evaluates O'Brien–Fleming only at the fixed K-look grid; between looks the existing mSPRT remains the continuous-monitoring readout. The 20 000-path / 200-read regression measures type-I **0.0510** versus the old **0.07885**.
- `obrien_fleming_boundaries` uses one numerically inverted Lan–DeMets spending construction; boundary probabilities match cumulative spending, and designs accept at most 20 looks.
- Binary, continuous, ratio, duration, and CUPED calculations honour the normalized `traffic_split`. Total sample size is sized for the limiting control-treatment comparison; deterministic 90/10 simulations achieve requested power.

## C-05/C-06 delivered contract

- The oracle has **106/106 checks across 39 cases** with independent references; constant-table/self cases are removed.
- `_add_check` scales, including finite zero-reference diffs. Anytime mSPRT type-I is **0.0059** (limit 0.055); JSON is strict.
- `examples/demo/` records the ASOS question and frozen protocol. Its fault suite blocks bad metric role, 90/10 assignment imbalance, and late exposure before corrected CLI run → decision → offline verify.

## C-07/C-08 delivered contract

- Added schema-backed `methods/profile.json` for analysis and blocked preflight bundles. It states the `binary_pooled_z_newcombe` method/version, estimands, error control, asymptotics, numeric and determinism contracts, assumptions, oracle evidence, and the bound implementation digest.
- ABX manifest roles, completed-run artifacts, CLI output, and verifier lineage now support `method`. Mutation coverage proves a rebound implementation digest is rejected.
- `scripts/generate_method_profile_table.py --check` owns the deterministic README table.
- Pipeline tests use an autouse fixed, non-degenerate `StatsKernelBuild`, leaving dirty-provenance behavior to `test_evidence_stats_kernel.py`.
- Evidence schema v3 rebuilds `run_artifacts` with role `method` and preserves v2 rows. A targeted regression covers the v2→v3 restart path.
- The documented README generator entrypoint has a subprocess regression. The privacy scanner suppresses phone-like digits only for schema-valid 40/64-character `git_commit` fields, not arbitrary text.
- Final human decisions are unsigned DSSE envelopes whose payload is an in-toto Statement v1. The subject is the parent analysis bundle digest and the predicate is the existing decision record; analytical proposed decisions stay legacy JSON.
- `verify` reports the statement and enforces subject equality with both `cites_bundle_id` and `supersedes`; a foreign subject fails lineage. Signing and Sigstore are deferred beyond C-08.

## Verification evidence

- K-01 (2026-09-08), after the decomposition: the full backend suite is
  **2047 passed, 25 skipped** in 1540.43s on `66abac76`, and CI run
  `34214146431` is green on all twelve jobs. `scripts/gate_trialmark.py` on the
  same tree is 153.4s (361 passed, 1 skipped). The longest function in
  `evidence/abx/` measures 182 lines by `ast`, against the plan's 200.

- K-01 (2026-09-08): the split is verified as a move, not read as one. An AST
  comparison of every top-level statement in the old `abx.py` against the six
  new modules reports `original=70 split=70`, nothing missing, nothing added,
  and one changed statement -- `_SCHEMA_ROOT`, which had to climb a directory.
  While the split was still uncommitted, the four CLI tests in
  `test_decision_role_source.py` failed with `stats kernel Git provenance is
  unavailable`: that is the dirty-tree guard working on a kernel-source change,
  not a regression, and it is why this commit had to land before its own gate
  could run clean.

- K-03 (2026-09-08): a real wheel build passes -- `python
  scripts/check_wheel_payload.py` reports 212 members and 30 required runtime
  resources, with no `evidence/reserved/` member; its `--self-test` flags a
  reserved path among 11 forbidden extras, so the rule is exercised rather
  than merely present. The moved tests are 29 passed. The reason
  `public_pilot_abx.py` did not move is checkable in one command: `run/run.json`
  is an entry in the committed `d53f0e.tmk` manifest and carries
  `runner.build_digest`, which is derived from the module's own path string.

- K-04 (2026-09-08): `python scripts/gate_trialmark.py` exits 0 in 166.0s and
  in 156.0s across two runs, against the plan's 180s target; the two differ
  only in which cache was cold. Backend selection 361 passed and 1 skipped over
  32 files, `tsc` clean, 2 preflight Vitest files and 4 tests green. Use it
  between edits; `verify_all.py` is still the only gate that clears a push.

- K-02 (2026-09-08): seven cold `trialmark verify` runs of the committed
  `d53f0e.tmk` on a quiet machine, median 1.394s before and 0.570s after,
  against the plan's 0.8s target. `test_cli_cold_start.py` is the regression
  guard and it has to run in a subprocess: inside a test session DuckDB and
  psycopg are already imported by something else, so `sys.modules` there
  proves nothing. On the previous `cli.py` it fails listing `duckdb`,
  `psycopg`, `data_sources` and the rest; on the new one the list is empty.
  Full local gate on the same tree: ruff clean, strict mypy 177 files, backend
  suite 2046 passed and 25 skipped in 813.93s with nothing deselected.

- J-02 (2026-09-08): `trialmark source validate` on the README pair answers `valid: true` with the metric id, both digests and the four counts; a row-level CSV answers `valid: false` naming the expected columns beside the found ones; two aggregate rows answer `found 2 -- this looks like a row-level export`. `app/backend/tests/test_source_validate.py` is 6 scenarios green, including one that patches `_create_repository` to raise and asserts the working directory stays empty, which is the slice's actual promise. `pipeline.validate_binary_source` is the one implementation the pipeline and the pre-flight share.

- J-01 (2026-09-08): `trialmark gate3` measures Gate 3 from `docs/pilots/*.md` alone. `app/backend/tests/test_gate3.py` is 14 scenarios green; an empty cohort decides `stop` with every denominator zero and still exits 0; re-rendering an unchanged cohort is byte-identical and the `report_digest` recomputes from the rendered JSON block. Ahead of it, `ff8df25c` fixes why the Windows `Tests` leg for `b6c29daf` was cancelled at its 20-minute timeout: the DuckDB deadline fired one interrupt, DuckDB clears that flag when a query starts, and a lost shot left a 5 ms budget unbounded. The new regression test never finishes on the old code (killed at 60s) and raises `QueryTimeoutError` in ~2.5s on the new; the budget test passes 10/10 in ~1.5s each. That deselect is now gone: two Windows CI legs have passed (`34194681103`, `34195927695`) and the local full suite ran 2046 passed, 25 skipped in 813.93s with the nodeid selected.

- Phase I close-out (`b6c29daf`, 2026-09-08): the I→J gate run end to end, not only through tests. A real CLI `run` → `decide` with no `--role` records `role_source: policy_default` in the child bundle's DSSE payload; `--role impostor` exits 1 with `role_not_permitted`; `--role benchmark_reviewer` records `asserted`; the three committed ASOS bundles still verify `valid` under the widened `decision.schema.json`; that CLI run is fetchable as `GET /api/v2/runs/{id}:bundle` → 200 from a working directory outside the repository. The gate's literal `get_settings()` production check does not hold by design — I-02 kept that guard in `main._verify_production_auth`, where the database is visible, and `test_production_auth.py` covers it with seven cases. Focused selection 20 passed; the full backend suite for the same tree was 2024 passed, 25 skipped, 1 deselected in 727.8s.

- H-02 close-out (`832923f0`, 2026-09-07): `origin/main` == `HEAD`; the `Tests` run for that commit is 12 jobs green, including both `verify` matrix legs, `statistical-oracle`, `verify-postgres`, `docker`, `lighthouse` and `update-metrics-badges`. `CodeQL` is `skipped`, not `success`, because code scanning on a private repository needs paid GHAS. Local evidence for the two fix commits: full backend suite 1995 passed / 25 skipped in 1186s, ruff and strict mypy (176 files) clean, the differential statistical oracle 110/110 against scipy/statsmodels, ASOS bundles re-packed identically under CPython 3.13 and 3.14, and the frontend 72 files / 446 tests in 61.7s with lint at 0 errors.
- T-13 / A-05 (`445c2879`, 2026-09-07): full backend gate green on tree `e03caa7a93` in 541.4s with `test_duckdb_file_adapter_enforces_scan_result_and_timeout_budgets` deselected. Documents the `BUILD_INFO.json` stamp on `write_stats_kernel_build_info` and `load_stats_kernel_build`; narrows the Git-fallback wrap to `rev-parse --show-toplevel`; adds `app/backend/tests/test_stats_kernel_build_info.py`.
- T-22 (`8eda1b15`, 2026-09-07): `test_c06_demo.py`, `test_abx_cli.py`, `test_persisted_workbench_seed.py`, and `test_record_trialmark_demo.py` now inject a fixed `StatsKernelBuild` via an autouse patch of `app.backend.app.evidence.pipeline.load_stats_kernel_build`. The corrected-demo path uses an in-process `_run_cli` shim whose contract is pinned by `test_c06_in_process_cli.py`. Successful end-to-end coverage through a real CLI process is given up; remaining subprocess coverage is `test_recorder_help_runs_from_the_repository_root` and the error paths. `test_evidence_stats_kernel.py` is untouched.
- T-21 (`927bd15a`, 2026-09-06): deleted the dead `test_trialmark_upload_contract.py` importer of `test_evidence_workbench` helpers left behind by `015212e8` (2026-09-02). Collection had failed for four days with `ModuleNotFoundError: No module named 'app.backend.tests.test_evidence_workbench'`. `/api/v2/bundles:verify` is absent; `test_persisted_workbench_routes.py` already asserts that. Full gate: tree `844e070ce4`, 1971 passed, 25 skipped, 1 deselected, 378.2s.
- D-01/D-03: tamper demo **3 passed**, recorder **6 passed**, Ruff and strict mypy (**174 files**) passed. The fresh real-UI recording produced a 36.44 s H.264 MP4 and two strict-valid bundles; tamper rejection and Markdown/diff QA passed.
- D-02 tooling: **86 tests**, scoped Ruff, and strict mypy passed at `b34e68e8`; no unfinished Gate 3 code remains.
- C-08: schema/run/persisted **49 passed, 1 deselected**; verifier/content binding **102 passed**; persisted/storage/pipeline **48 passed**; dirty-safe CLI/demo **30 passed, 2 deselected**; stats-kernel **22 passed**; Ruff and strict mypy (**174 files**) passed. From clean `97a2f5b0`, persisted CLI and corrected demo acceptance **2 passed**.
- C-07: combined evidence/storage **125 passed**; dirty-safe ABX **166 passed**; oracle **110/110**; Ruff, strict mypy (**173 files**), README generation, and clean-HEAD CLI/demo acceptance passed.
- Earlier C-01 through C-06 verification detail remains in `AGENT_STATE.md` and Git history.
- B-08 Mac acceptance passed at `c81af0f914b4746c80f45d79caa0ec8cd8beec4d` with explicit `DONE`; Compose cleanup completed. Local packaging/container contracts passed **6 tests**. No Windows container runtime ran.
- B-06 persisted-flow evidence: live E2E **7 passed** (`archive/e2e-runs/20260902-041139`), frontend **72 files / 446 tests passed**, generated contracts were current, and production build passed. Detailed recovery evidence remains in Git and `archive/`.

## Baselines and next boundary

- Last full backend gate is 2026-09-08 on `66abac76`: Ruff over `app/backend/app app/backend/tests scripts`, strict mypy, and backend pytest all passed; pytest reported **2047 passed, 25 skipped, no deselect** in 1540.43s. This supersedes the T-13 `445c2879` baseline; later focused checks do not replace it.
- All locally executable work in `plan_07_09_26.md`, including K-05, is complete. K-05 adds 31 scenarios across the bundle-container, lineage-binding, and privacy-policy specs; their referenced pytest selectors collected and passed 42 tests on 2026-09-11. D-01/D-03 stay unpublished pending Q8; D-02/D-04 and J-04/J-05 remain gated on real sessions; Q9 remains open. Do not fabricate sessions, recruit/publish/push, or open E/F/G without validated reuse by two external practitioners. With the local plan exhausted, the next session needs a new authorized goal or external evidence rather than resuming an implementation item.
- Gate 3 remains `PIVOT` with zero partner cycles. Do not claim external adoption or trust beyond the recorded verifier evidence.

## Useful commands and artifacts

- Full backend baseline gate: `python -m ruff check app/backend/app app/backend/tests scripts`; `python -m mypy`; `python -m pytest app/backend/tests -q` with nothing deselected.
- Container acceptance (Mac only): `python scripts/verify_docker_compose.py`; it supplies the exact `GIT_SHA`, exercises B-08, and performs Compose cleanup.
- CLI persisted flow: `python -m app.backend.app.evidence.cli run --protocol X.yaml --source Y.parquet --out Z.tmk`, then `decide --run RUN_ID --verdict ship|hold|stop --rationale TEXT --out Z2.tmk`; `runs list` enumerates persisted identities.
- ASOS fixtures and bundles: `app/backend/tests/fixtures/evidence/asos/`; provenance is in its `README.md` and `AGENT_STATE.md`.
- Architecture/API status: `docs/architecture/TRIALMARK_ARCHITECTURE.md` sections 12 and 17.5.

## Known traps

- The DuckDB budget test is part of the full suite. Its deadline watchdog must keep interrupting until the operation returns because DuckDB can clear an interrupt delivered before query execution begins. A timeout permits one narrowed diagnostic, not raw retries.
- Pytest basetemp belongs under `.tmp/pytest-basetemp-*`; keep the newest three. Plugin autoload has hung this workstation before; `pytest.ini` already disables known offenders.
- `archive/`, `.grok-prompts/`, root `audit_*.md`, and root `plan_*` are gitignored. `.trialmark/` is local E2E state and must remain local.
- Never use `git add -A`, amend, destructive Git, or push without fresh authorization.
- Do not resume the cancelled worker/full-legacy-lineage pipeline or start Evidence Graph, MCP, federation, or scale work.
- `STATS_KERNEL_SOURCE_PATHS` (relative to `app/backend/`) contains `app/evidence/abx/__init__.py`, `app/evidence/abx/_core.py`, `app/evidence/abx/lineage.py`, `app/evidence/abx/pack.py`, `app/evidence/abx/privacy.py`, `app/evidence/abx/verify.py`, `app/evidence/abx/zip_safety.py`, `app/evidence/stats_kernel.py`, `app/evidence/stats_kernel_abx.py`, `app/evidence/contracts/schemas/abx/0.1/amendments.schema.json`, `app/evidence/contracts/schemas/abx/0.1/common.schema.json`, `app/evidence/contracts/schemas/abx/0.1/decision-statement.schema.json`, `app/evidence/contracts/schemas/abx/0.1/decision.schema.json`, `app/evidence/contracts/schemas/abx/0.1/estimate.schema.json`, `app/evidence/contracts/schemas/abx/0.1/finding.schema.json`, `app/evidence/contracts/schemas/abx/0.1/manifest.schema.json`, `app/evidence/contracts/schemas/abx/0.1/method-profile.schema.json`, `app/evidence/contracts/schemas/abx/0.1/metric.schema.json`, `app/evidence/contracts/schemas/abx/0.1/protocol.schema.json`, `app/evidence/contracts/schemas/abx/0.1/run.schema.json`, `app/evidence/contracts/schemas/abx/0.1/source.schema.json`, `app/schemas/api/__init__.py`, `app/schemas/api/_results.py`, `app/services/results_service.py`, `app/services/results/__init__.py`, `app/services/results/binary.py`, `app/services/results/common.py`, `app/services/results/dispatch.py`, and `app/stats/binary.py`. An uncommitted edit to any member makes real Git provenance unavailable process-wide, so anything that resolves a real build identity fails while the edit is dirty. Since `8eda1b15` the four CLI/demo/seed modules inject a fixed `StatsKernelBuild`, so a kernel-source slice's full gate is reachable while its edit is still uncommitted: T-13 gated green on tree `e03caa7a93` with `app/backend/app/evidence/stats_kernel.py` dirty, and committed it afterwards as `445c2879` (tree `6415705419`). Any new test that resolves a real build identity through the CLI or the demo must patch `load_stats_kernel_build` itself, or it fails on a dirty kernel source. `test_evidence_stats_kernel.py` deliberately does not patch it and owns dirty/missing-provenance behaviour.
- The project gate lints `app/backend/app app/backend/tests scripts` since 2026-09-07 (H-05); all 81 errors that had kept tests out of scope are fixed. Mypy still type-checks only `files = ["app/backend/app"]` in `pyproject.toml`; extending it to tests is unscoped backlog, not done work.
- An open task is not proof that its work is undone. On 2026-09-07 six plan tasks were already implemented and merely unclosed, and three task details named files that no longer exist (`app/backend/app/evidence/workbench.py`, deleted by `015212e8`; `app/backend/app/evidence/http_runtime.py`, which never existed — it is `app/backend/app/http_runtime.py`; and `app/backend/app/results/`, moved to `app/backend/app/services/results/` by `38ea4e42`). Diff the detail against HEAD and run the task's own acceptance test before starting it.
