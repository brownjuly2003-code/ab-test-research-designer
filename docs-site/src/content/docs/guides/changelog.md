---
title: "Changelog"
editUrl: "https://github.com/brownjuly2003-code/ab-test-research-designer/edit/main/CHANGELOG.md"
---

# Changelog

## [Unreleased]

Entries below are a curated, non-exhaustive record from `d06b7a4f` onward,
plus the Node 24 / Hugging Face hygiene commit `1e415f54`; the
experimental evidence layer after `bb314ae1` is summarized here but remains
unreleased. Git history is authoritative for its individual implementation
commits.

### Added

- `scripts/gate_trialmark.py`, a focused gate over the evidence surface: ruff,
  strict mypy, the 32 backend test files that cover the evidence modules, the
  CLI, the persisted routes and the pilot records, then the frontend type check
  and the preflight unit tests. Measured twice on this machine at 166.0s and
  156.0s against a 180s target -- the difference is which cache happened to be
  cold, mypy's or Vite's. It reports its per-step timings and never fails on
  wall-clock, because a gate that fails when the machine is busy teaches people
  to re-run it until it passes. `verify_all.py` remains the full gate and the
  only one that clears a push; a missing test file breaks this one loudly
  rather than silently testing less than its list claims.

- `trialmark source validate --protocol <p.yaml> --source <data.csv>`
  pre-flights a practitioner's aggregate CSV against a frozen protocol. It runs
  the same checks `run` does -- schema, exactly one aggregate row, and the
  metric `definition_digest` -- and touches nothing: no database, no run, no
  bundle. The diagnostics became concrete in the process, for every caller and
  not only this one: a schema mismatch now names the expected columns beside
  the ones the file actually has, a row count says how many were found and
  that the file looks row-level, and a digest mismatch prints both digests.
  `pipeline.validate_binary_source` is the single implementation the pipeline
  and the pre-flight share, so the two cannot drift into disagreeing about
  whether a source matches its protocol.

- `trialmark gate3 --records <dir> [--out <file.md>]` aggregates validated
  external pilot records into the Gate 3 decision. Until now the gate was
  evaluated by hand against prose. The aggregator reads only the records --
  no clock, no network, no database -- so a cohort always yields the same
  report and the same `report_digest`, and re-running writes identical bytes.
  One participant counts as one cycle however many sessions they recorded, and
  a criterion no cohort of records can measure (preflight detection) is
  reported `unmeasured` rather than passed. An empty cohort decides `stop`
  with every denominator at zero, and every verdict exits 0: `stop` is a
  measurement, not a command failure.

- Evidence CLI installs as the console command `trialmark` (`d06b7a4f`):
  `pyproject.toml` `[project.scripts]` points at
  `app.backend.app.evidence.cli:main`. Shipped subcommands are `pack`,
  `verify`, `inspect`, persisted `run` / `decide`, and `runs list`. The B-05
  workflow (`338777c6`) publishes verified analysis and append-only decision
  bundles, reports `run_id`, `bundle_id`, and verdicts, and resolves principals
  from `--actor`, `$USER`, or `local-operator`. After
  `pip install -e . --no-deps` the command is on PATH; the gate still invokes
  `python -m app.backend.app.evidence.cli`.

- External pilot source profile `trialmark.aggregate-binary` (`b34e68e8`,
  `c655aed2`): `trialmark run` accepts a one-row aggregate CSV
  (`control_users,control_conversions,treatment_users,treatment_conversions`)
  instead of ASOS Parquet, binding the partner's metric to the frozen protocol
  through the canonical-JSON digest of `metric.definition`. The published
  bundle stays aggregate-only and records the asserted telemetry counts as
  `telemetry_profile_source: upstream_asserted`. A runnable protocol and CSV
  live in `examples/pilot/`.
- `trialmark pilot-session create|validate` (`b34e68e8`): writes and validates
  the anonymous record of one observed external session as
  `<date>-<anon_ref>.md`, taking its census from the published bundle and
  accepting no source path and no participant identity. Reuse is recorded with
  `--reuse-kind second_run|evidence_reopen`.
- Decision bundles carry `decision/statement.dsse.json` (`97a2f5b0`): an
  unsigned DSSE envelope around an in-toto Statement v1 whose subject is the
  parent analysis bundle identity. `verify` reports statement type, predicate
  type, subject, signature count, and whether the subject matches `supersedes`.
- Analysis and blocked-preflight bundles carry schema-backed
  `methods/profile.json` (`d9bbe7a4`): method id and version, estimands, error
  control, asymptotics, numeric and determinism contracts, assumptions, oracle
  evidence, and the bound implementation digest.

### Changed

- `app/backend/app/evidence/abx.py`, 2 132 lines, became the package
  `app/backend/app/evidence/abx/`: `_core.py` (constants, digests, schema
  validation), `zip_safety.py` (what the archive is allowed to be, before
  anything reads it as evidence), `privacy.py`, `lineage.py` (reference
  integrity and binding, one walk over the same documents), `verify.py` and
  `pack.py`. The dependency graph is a DAG in that order, and `__init__.py`
  re-exports every name the module exported, so no importer changed. The move
  is mechanical: an AST comparison of all 70 top-level statements before and
  after reports one difference, `_SCHEMA_ROOT`, which climbs one directory
  because the file is now one deeper than the schemas.

  `STATS_KERNEL_SOURCE_PATHS` lists the seven new modules in place of the one
  old one, so **`stats_kernel.build_digest` changes**, as it did at `445c2879`.
  Published bundles do not need repacking: a verifier compares a bundle's own
  `methods/profile.json.implementation_digest` against the `run.runner
  .build_digest` recorded inside that same bundle, never against the current
  build. `test_build_identity_hashes_required_sources_lock_and_verified_commit`
  now reads the package directory and fails if a new `abx/` module is missing
  from the list -- otherwise a module could change the kernel without changing
  its digest.

  Four tests moved their patch target one module down, to where the name is
  actually looked up (`abx.pack.os.link`, `abx.pack._fsync_directory`,
  `abx._core.canonical_json_bytes`,
  `abx.zip_safety._sequential_local_header_offsets`), and the comment-guard
  test now reads every file in the package rather than one file, because which
  submodule holds a comment is a refactoring detail.

- The three functions in that package that were over 200 lines are not any
  more. `_archive_preflight` (405 lines) became four checks that name what they
  answer -- `_scan_local_records` walks the local file records in physical
  order, `_check_central_directory` compares each central entry with the local
  record it points at, `_check_archive_trailer` reads the Zip64 trailer and the
  end-of-central-directory record, and `_check_member_inventory` checks the
  members as a set, without reading the archive at all. `verify_logical_bundle`
  (311) became `_scan_logical_members`, `_inventory_manifest_entries` and
  `_verify_logical_entries`, which is the three passes it already made.
  `_check_references` (483) gave up `_check_child_chain`, `_check_queries`,
  `_check_metric_definitions` and `_check_method_profile`; what stays inline is
  the run-versus-artifact tail, which reads too many of the resolved id maps to
  be worth a ten-parameter signature. The longest function in the package is
  now 182 lines. No condition, message, error code or ordering changed: the
  blocks moved with their comments intact and the same `errors`/`result`
  accumulator is threaded through, so diagnostics come out in the same order.

- `dbt_manifest.py` and `legacy.py` moved to
  `app/backend/app/evidence/reserved/` and no longer ship in the wheel, along
  with the pinned `dbt/manifest/v12.json` they need. Neither had a production
  importer; both are kept, not deleted, because phase G needs them and their
  pinned schema is the expensive part to recover. Their tests moved to
  `app/backend/tests/reserved/` and stay in the gate -- a reserved module that
  stops compiling is one nobody can revive. `check_wheel_payload.py` now fails
  the build if any `evidence/reserved/` member appears in a wheel, so the
  pyproject exclusion cannot rot silently. Architecture §8.4 and §16.1 are
  marked reserved.

  `public_pilot_abx.py`, the third module the audit listed, stayed where it is.
  It derives its `runner.build_digest` from the literal path strings in
  `_RUNNER_SOURCE_PATHS`, and that digest sits in `run/run.json`, which is a
  manifest entry -- so moving the file rotates the `bundle_id` of all three
  published ASOS benchmark bundles. That is a decision about published
  identifiers, not a refactor.

- The evidence CLI imports what a command actually uses. `trialmark verify`
  reads a ZIP and checks digests, but it used to load DuckDB, psycopg, numpy,
  the repository and the whole pipeline first, because `cli.py` imported them
  at module scope. They now load inside the handler that needs them, and the
  median cold `verify` of the committed `d53f0e.tmk` fell from 1.394s to
  0.570s over seven runs. `test_cli_cold_start.py` runs `verify` in a fresh
  interpreter and fails if any of those modules appears in `sys.modules`
  afterwards, because inside a test session they are all imported already and
  the assertion would prove nothing. The JSON error envelope is unchanged: the
  codes are resolved from the modules that are loaded, so an error still
  reports as `run_not_found` or `source_invalid` rather than as a traceback.

- Product brand is Trialmark; new bundle destinations use the `.tmk` suffix;
  HTTP uses vendor media type `application/vnd.trialmark.bundle+zip`
  (`8e3b5853`). ADR 0003/0004 stay as historical records (EvidenceOS / `.abx`
  wording kept); the rename is recorded in ADR 0005. Module names, schema
  `$id`, `urn:evidenceos:abx:*`, and `abx_version` stay as they are: ADR 0006
  freezes them as the identifiers of bundle format 0.1, on the reading that
  `abx` names the format while Trialmark names the product. They change only
  with a format version 0.2, because a manifest entry's `schema_id` is inside
  the bytes the manifest digest covers, so renaming rotates every `bundle_id`
  ever issued.
- Node 26 Current → Node 24 LTS in the Docker image and workflows
  (`1e415f54`).
- Lineage identifiers are bound to the content they name (`1965200d`):
  `protocol_revision_id` to the RFC 8785 digest of `protocol.json`, metric
  digest to stored `metric.json` bytes, SQL `statement_digest` to
  `sha256(query.sql)`, `query_id` via the producer identity helper.
  Degenerate runner digests are rejected. The three ASOS control bundles
  stay `lineage: pass`; the Workbench demo fixture is expected
  `lineage: fail` until plan item B-06.
- Binding is reported per bundled metric (`ee3c1ae1`): `unbound_bindings` on
  `verify`/`inspect`; `absent` is listed and accepted, `ambiguous` /
  `unlocated` are listed and rejected. Central-directory relative offsets
  stay authenticated against a layout shift. The offline verifier no longer
  imports the DuckDB/PostgreSQL adapter layer: `query_identity_digest`
  moved to the dependency-free
  `app/backend/app/evidence/query_identity.py`, shared by producer and
  verifier (`F-T-07-24`).

### Removed

- Hugging Face snapshot path (`1e415f54`): `SnapshotService` and its
  startup branch, `ProjectRepository.supports_snapshots` /
  `reinitialize_after_restore`, `scripts/deploy_hf.py`, the `AB_HF_*`
  environment variables, and `huggingface_hub` from the runtime and
  dev locks.

### Fixed

- DuckDB query deadlines are enforced by a retrying watchdog instead of one
  timer shot. DuckDB clears its interrupt flag when a query starts, so an
  interrupt delivered in the window between arming the deadline and execution
  beginning was simply lost -- and at the millisecond budgets the adapter
  accepts, that window is most of the wait. A lost interrupt left the query
  running with no bound at all: on a contended Windows CI runner one 5 ms
  budget outlived the 20-minute job. The watchdog now keeps interrupting until
  the operation returns, and a regression test proves that swallowing the
  first interrupt only delays the timeout instead of removing it.

- Wheel payload (`d06b7a4f`): `[tool.setuptools.package-data]` now ships the
  ABX/dbt schemas, i18n catalogs, and YAML templates (previously zero
  non-.py files, so every subcommand failed on a non-editable install).
  `app.backend.tests*` (108 test modules) and `app.backend.data` (live
  `projects.sqlite3`) are excluded from the distribution. Payload is
  guarded by `scripts/check_wheel_payload.py` and
  `app/backend/tests/test_packaging_metadata.py` in the repo-hygiene job.

- `GET /readyz` reports `auth_mode`, and startup logs a single `event=auth_open`
  warning when nothing gates a mutating request. "Ready" and "safe to send
  traffic to" are different questions, and a deployment could answer yes to the
  first while every mutating endpoint accepted anonymous callers; the open state
  was visible only as one INFO field among fifteen at boot. The readiness value
  reserves `open` for a genuinely open surface: `get_auth_mode`, which backs the
  diagnostics field of the same name, calls an admin-token-only or public-demo
  deployment "open" even though both already reject anonymous mutations, so those
  report `admin_only` and `public_demo` instead. Production cannot reach `open`
  at all -- `main._verify_production_auth` refuses to boot without auth material.

- A decision says where its role came from. `decided_by.role_source` is
  `credential` when the authenticated API key carries the role -- the only
  source the service verifies -- `asserted` when the caller named it
  (`trialmark decide --role`), and `policy_default` when no role was declared
  and the frozen policy's first approval role applied. Until now every decision
  silently used the policy default and the record could not say so, which read
  as if a role had been checked. Issued keys gained a nullable `role` column
  (SQLite migration and PostgreSQL migration 18), `POST /api/v1/keys` accepts
  it, and the field is optional in `decision.schema.json` so bundles recorded
  before it stay valid.

- A frozen policy asking for more than one approval is now refused with
  `approval_quorum_unmet` (HTTP 409, CLI exit 1). Recording a decision writes
  exactly one approval, the decider's own, and a run whose policy set
  `minimum_approvals: 2` used to get an `approved` decision carrying half the
  signatures its own policy demanded.

- A finding action on a `finding_id` the run never carried answers 404 whatever
  else that run has since recorded. `record_finding_state` checked the run's
  state first, so `POST /api/v2/runs/{id}/findings/{unknown}:remediate` reported
  409 "finding actions require a pre-decision run" against a run that already
  carried a decision -- a conflict message about a resource that does not exist.
  The existence check now runs directly after the run lookup; the pre-decision
  and open-finding guards keep their own order behind it, so a finding that is
  really there still conflicts.

- `AB_ARTIFACT_ROOT` names the persisted-evidence artifact tree once, and
  `Settings.artifact_root` resolves it to an absolute path at load. Three call
  sites each held their own `Path(".trialmark") / "artifacts"`, which resolves
  against the current working directory: an API server started anywhere other
  than where the CLI ran served a different tree, so `GET
  /api/v2/runs/{id}:bundle` answered 404 for a run that had just succeeded.
  `pack --run` now defaults to the configured root instead of demanding
  `--artifact-root`, `GET /readyz` reports the resolved path and whether it is
  writable, and `docker-compose.yml` sets the variable under `/app/data` because
  the image runs as uid 1000 and `/app` belongs to root.

- Two-sided p-values no longer lose the tail to cancellation. `2 * (1 - cdf(z))`
  discards about two significant digits at z = 2.2, is 7% wrong at z = 8, and
  underflows to exactly `0.0` for z >= 8.3, so the most decisive results were
  reported as `p = 0`. Three survival functions now carry the tail directly --
  `standard_normal_sf` (`app/stats/binary.py`, `0.5 * erfc(z / sqrt(2))`),
  `t_sf` (`app/stats/student_t.py`) and `chi_square_sf` with
  `regularized_gamma_q` (`app/stats/srm.py`) -- and the 23 `1 - cdf` sites in 18
  modules were converted, including `evidence/stats_kernel.py`,
  `services/results/binary.py`, `services/results/continuous.py`,
  `stats/paired.py`, `stats/survival.py` and `stats/trimmed_t.py`. Chi-square
  with 3 degrees of freedom at x = 200 now returns `4.219e-43` instead of `0.0`.

- ASOS benchmark bundle identity no longer depends on the host libm. `erfc` is
  not correctly rounded, so Windows and Linux disagreed in the last two digits
  of the estimate p-value, which rotated `bundle_id` per platform and reddened
  `test_packs_deterministic_offline_asos_public_benchmark[26bd38]` on
  `ubuntu-latest`. `_benchmark_p_value`
  (`app/evidence/public_pilot_abx.py`) quantises the published p-value to 12
  significant digits, which is far above the disagreement and far below the
  reporting precision; it is the only value in these documents that leaves
  IEEE-754 arithmetic. The three committed bundles and every pinned digest were
  rotated, and re-packing under CPython 3.13 and 3.14 now yields the same
  `bundle_id`.

### Security

- Privacy scanning now splits camelCase/PascalCase keys before checking
  secret-bearing fields and rejects long numeric identifiers in sensitive
  account/user/subject/phone fields, E.164 and Russian-format phone numbers,
  valid IPv4/IPv6 addresses, and Windows/POSIX absolute filesystem paths
  (T-11 / plan A-03). A 12-case adversarial corpus and boundary controls pin
  the behaviour; all three ASOS control bundles remain `privacy: pass`.

- Bundle ZIP transport is authenticated (`2ba57869`): archive and per-entry
  comments and extra fields fail `integrity` (`entry_extra_field`); foreign
  bytes before the first member, between members, and after EOCD fail
  `integrity` (`archive_trailing_bytes`). The same commit derived a
  `special_member` rejection from `external_attr` entry-type bits (always
  on; `create_system` no longer switches the guard off). CD-only metadata
  (`external_attr`, `create_version` / version-made-by, `internal_attr`)
  is not authenticated.
- `ee3c1ae1` removes the `special_member` rejection that `2ba57869` derived
  from `external_attr` entry-type bits; directory entries are still
  rejected by the platform-independent trailing-slash rule
  (`unsafe_member_path`), symlink/special-file entry types are no longer
  rejected — accepted risk `F-T-06-15`.

## [1.3.1] - 2026-07-30

### Added

- `docs/PROJECT_CLOSURE.md` freezes the shipped product scope, classifies
  historical/research plans as non-active work, records preserved local
  artifacts, and keeps the final publish/release/demo evidence gates explicit.
- No-Docker single-port local runner (`scripts/run_local.py`): bootstrap venv,
  install backend lock, build frontend dist, and serve the product on one port
  without Compose. Documented in README; covered by `test_run_local_script.py`.

### Changed

- Hugging Face publication path retired (owner decision 2026-07-30): current
  operational docs and the public docs-site are local-first / GitHub-only;
  GitHub-to-HF workflows `deploy-hf.yml` and `space-maintenance.yml` removed
  from the active tree. Legacy optional snapshot code remains in-repo but is
  not a supported publication target and is outside closure.

### Security

- frontend `eslint-toolchain`: pin transitive `brace-expansion` to audit-clean `5.0.8` via npm `overrides` (GHSA-mh99-v99m-4gvg / CVE-2026-14257), plus a dual-API compat preload so minimatch@3 (eslint-plugin-react / jsx-a11y) still accepts brace globs while modern `.expand` consumers keep working. Lint runs a deterministic preflight; `npm audit --audit-level=high` is clean after clean install.
- docs-site: pin transitive `svgo` to `4.0.2` via npm `overrides` (GHSA-2p49-hgcm-8545 / removeScripts). `npm audit --audit-level=high` is clean after clean install.
- docs-site: replace compromised Astro lock/package resolution state
  (`7e5f2657`) so clean install, audit, tests, and production build stay green.
- Slack ingress (audit F-05): `/slack/commands|interactive|events` now share a dedicated body cap (`AB_MAX_SLACK_BODY_BYTES`, default 64 KiB) and request-count rate limit; invalid signatures are throttled (`AB_SLACK_INVALID_SIGNATURE_*`) before form/json parsing. Oversized bodies return 413 without unbounded buffering.
- Cost-aware compute admission (audit F-06): expensive `/api/v1/results*` and bandit simulation estimate cost units after schema validation (analyzer type, N, resamples/table size) and acquire a bounded heavy/cheap concurrency + in-flight cost budget before resampling starts. Overload returns 429 `compute_capacity_exceeded` with `Retry-After`; cheap summary tests keep a separate lane.
- API key scopes (audit F-09): issued keys are only `read`/`write`. Schema and UI no longer offer `admin`. Legacy stored `scope=admin` keys normalize to `write` on startup with an audit entry (`api_key_scope_normalized`). Operator surfaces (`/api/v1/keys`, `/api/v1/webhooks`) require static `AB_ADMIN_TOKEN` only; missing token returns `401`/`admin_token_not_configured`, and a write key attempting operator routes returns `403`/`admin_token_required`.

### Changed

- Frontend API client split (plan step 8): monolithic `lib/api.ts` → domain modules under `lib/api/` (`client`, `projects`, `analysis`, `keys`, `webhooks`, `system`, `workspace`) with a stable `lib/api.ts` facade. `ApiKey*` / `Webhook*` DTOs re-export OpenAPI-generated types instead of hand-maintained duplicates.
- `ApiKeyManager` i18n (×7 locales) plus create-modal keyboard a11y (focus trap, Escape, focus restore) and destructive delete confirmation via `InlineConfirmButton`.
- `ComparisonDetails` i18n (×7 locales): saved snapshot comparison labels no longer hardcode English.
- Locale key parity + static `t()` usage gate (`scripts/check_locale_parity.py`) in `verify_all` and CI: plural-family-aware coverage vs `en.json`, stale extras fail, missing catalog keys used in `src` fail.
- Frontend ESLint flat baseline (TS parser, React hooks `rules-of-hooks`, JSX a11y) via side-by-side `eslint-toolchain` (TypeScript 5.9) while the app stays on TypeScript 7; wired into `npm run lint` / `verify_all` / CI.
- Bundle budget gate reports per-chunk raw/gzip sizes and total gzip; hard ceilings unchanged. Raising budgets requires ADR (`docs/adr/0002-frontend-bundle-budget.md`).
- Scientific oracle gate (plan step 9): optional pinned SciPy/statsmodels/lifelines environment (`app/backend/requirements-oracle.txt`) plus `scripts/run_statistical_oracle.py`, producing `.ci-artifacts/statistical-oracle.json` with dependency versions, method-specific tolerances, and 97 differential/metamorphic checks across Student/F tails, binary intervals, exact/count/categorical tests, robust/paired/omnibus/survival/Cox, ratio delta method, SRM, multiple-testing, CUPED, cluster design effects, sequential boundaries, Bayesian precision sizing, always-valid inference, and guardrails. CI now uploads the oracle artifact and runs the job on PR/main, manual, and weekly scheduled workflows; production requirements stay unchanged.
- Decision readout practical-significance policy `practical_v1` (audit F-07 / ADR 0001): `ship` now requires a statistical win **and** CI lower bound ≥ design minimum worthwhile effect (absolute MDE from `mde_pct`). Trivial-but-significant effects become `no_ship` / `keep_running` with machine-readable reason codes. Response includes `policy` + `evidence` (policy version, MWE, planned power); observed post-hoc power is explicitly not used for the verdict. Live history snapshots are not rewritten.

### Fixed

- `check_locale_content.py` docstring no longer claims a non-existent CI key-parity gate; it only scans values for mojibake/U+FFFD.
- Broken `t("comparison.loading")` key in `ComparisonSection` → `results.comparison.loading`.
- Wizard field labels for count/ratio/Bayesian/exposure keys now exist in all 7 locales (were RU-only extras / EN `defaultValue` fallbacks).
- jsdom Canvas noise: stable `HTMLCanvasElement.getContext` / `toDataURL` stubs in vitest setup (typed for TS 7).
- PostgreSQL parameter typing (audit F-03): removed content-based `{`/`[` + `json.loads` → `Jsonb` inference. Intentional JSON/JSONB values bind via explicit `JsonParam`; JSON-looking TEXT (`project_name`, `user_id`, `metric`, `stratum`, exclusion reasons, …) round-trips unchanged on SQLite and PostgreSQL. `?` → `%s` remains a documented temporary portability shim.
- Analytical population (audit F-02): primary, holdout, strata, and event-timing now share one `analytical_population_v1` contract (identity one-hop fold, first-exposure-wins, manual + rate-spike exclusions). Holdout no longer groups by raw `user_id` without identity/exclusions. Live-stats gains a `population` fingerprint block; identity ingest rejects chain/cycle links.
- CUPED and ratio rollups now use the same `analytical_population_v1` contract
  as primary/holdout/timing/strata (identity fold, first-exposure-wins, manual
  + rate-spike exclusions); residual raw-`user_id` path closed
  (`e18e2a3d`, `530c6db2`; `test_analytical_population.py`).
- Stable centered moments for continuous primary/holdout/guardrail/stratified,
  CUPED, and ratio aggregates so large-magnitude metric values no longer
  collapse `centered_sxx`/`syy`/`sxy` to zero under float accumulation.
- PostgreSQL `conversions.value` promoted from REAL to DOUBLE PRECISION
  (migration 17, `58f48b14`) so ratio/CUPED metric precision matches SQLite
  float64 semantics near large means.
- HF SQLite snapshots are now WAL-consistent and atomic: push stages via `sqlite3.Connection.backup()` (includes WAL-visible commits), runs `PRAGMA quick_check`, and uploads DB+metadata in one HF `create_commit`. Restore binds both artifacts to one remote revision, refuses corrupt/SHA-mismatched DBs without replacing a working file, and re-runs schema bootstrap after replace so schema `N-1` snapshots migrate to the build `user_version`.
- HF SQLite restore keeps a pre-replace rollback copy and reverts the live DB if post-replace migrate/smoke fails; WAL/SHM sidecars are cleared on replace. Push/restore emit structured metrics (`snapshot_push` / `snapshot_restore`). Concurrent-writer backup integrity and fault-injected `create_commit` failure (previous revision still restorable) are covered by tests.
- SQLite connections are now closed deterministically: `_BackendCore._transaction()` wraps every repository query (transaction scope + `close()`), replacing the bare `with self._connect()` pattern whose context manager only commits and leaves the file handle to the GC. Surfaced as ~4.5k `ResourceWarning`s once pytest-cov 7 stopped suppressing them; the postgres pooled wrapper gained a no-op `close()` since its `__exit__` already returns the connection to the pool.
- Mobile topbar overflow: narrow viewports wrap `.topbar-inner` / `.topbar-controls` so language/theme controls no longer clip off-screen.
- Landing WCAG AA / semantic-region gate: EmptyState demo list is a labeled `section`, accent tokens split fill vs on-surface (`--color-primary-fg`) with muted text raised for AA contrast, and the Playwright e2e smoke asserts axe WCAG 2.0/2.1 A/AA plus theme-settled contrast on the landing surface.

### Dependencies

- 2026-07-29 Dependabot wave on `main` (merged): frontend minor/patch group
  (`#129`), actions minor/patch group (`#130`), `actions/setup-python` major
  (`#131`), `actions/setup-node` major (`#132`), `@astrojs/starlight` (`#134`).
  PR `#133` (hypothesis pip-minor-patch) closed without merge.

## [1.3.0] - 2026-07-18

### Added

- Frontend unit-test coverage gate as a dedicated CI job (`frontend-coverage`): vitest v8 coverage with floors at measured coverage minus ~3 p.p. (lines/statements 75, functions 78, branches 67), kept out of the verify path because instrumentation slows the suite.
- Three Playwright e2e scenarios beyond the smoke flow: locale switching incl. Arabic RTL with persistence across reload, workspace export→import roundtrip, and webhook manager create/delete. The e2e runner now boots a second admin-token-enabled backend for the webhook spec, since keys/webhooks surfaces are admin-only at the middleware level and enabling the token instance-wide would close the anonymous smoke paths.

### Changed

- Toolchain moved to Python 3.14: Docker runtime base image, all CI jobs, and the mypy target. Code keeps a 3.13 compatibility floor (ruff `target-version`) so local dev on 3.13 keeps working. Closes the deferred Dependabot #91.
- Frontend build toolchain moved to Node 26: Docker frontend-build base image and `setup-node` in CI/docs-site workflows. Closes the deferred Dependabot #89.
- Admin retention purge (`POST /api/v1/admin/retention/purge`) now defaults to `dry_run=true`; deletion requires an explicit `dry_run=false` (safety default for a destructive admin operation).
- Caller-keyed OpenAI adapter: default model updated from the retired `gpt-4o-mini` to `gpt-5.6-luna`, and the model is now configurable via `AB_OPENAI_MODEL`.
- CI badge payloads moved off `main`: the badge job now force-pushes a single-commit orphan branch `generated/badges` and README/shields endpoints read from it, so bot commits no longer pollute main history.

### Fixed

- `docs-site/scripts/gen-experiments.mjs`: `tableEscape` now escapes backslashes before pipes, so a literal `\|` in source data can no longer break markdown table cells (CodeQL `js/incomplete-sanitization`).

### Security

- CodeQL alert triage: sessionStorage session-token alert dismissed as by-design with rationale recorded in `SECURITY.md` threat model notes; intentional fake-DSN logging in the redaction test dismissed as test-only.

## [1.2.0] - 2026-07-17

### Added

- Dedicated rate-limit bucket for CPU-heavy simulation endpoints (`/api/v1/projects/compare`, `/api/v1/simulate/bandit`): `AB_HEAVY_RATE_LIMIT_REQUESTS` / `AB_HEAVY_RATE_LIMIT_WINDOW_SECONDS` (default 30/60s) layered on top of the global window, so anonymous demo traffic cannot keep the CPU pegged while staying inside the CRUD-sized limit.
- `SECURITY.md` (private vulnerability reporting, documented threat-model highlights), `CONTRIBUTING.md`, and GitHub issue/PR templates.
- CodeQL static analysis workflow (python + javascript-typescript) on PRs, main pushes and a weekly schedule.

- Durable webhook outbox: delivery rows are committed in the same transaction as their audit event and claimed by a background worker under a database lease, so retries survive restarts and replicas never race the same row (`webhook_deliveries.next_attempt_at` / `lease_expires_at`, schema v15 on both backends). Diagnostics now reports webhook queue depth per status and the age of the queue head.
- Webhook SSRF guard: targets that resolve to a private, loopback or link-local address are refused at delivery time (and literal non-public IPs rejected at subscription create/update); `AB_ENV=local` keeps the localhost carve-out for development. Response bodies are read from the network up to 64 KB with an explicit truncation marker, instead of buffering arbitrarily large responses.
- Metric capability registry (`metric_capabilities` + frontend `metricCapabilities.ts`) as the single source of truth for planning families and post-hoc analyzer payload kinds, so count/ratio support cannot drift across schema/dispatch/UI unions.
- Diagnostics topology contract (`single_instance` / in-process rate limits and counters) and opt-in retention windows (`AB_RETENTION_*_DAYS`) with admin dry-run purge at `POST /api/v1/admin/retention/purge`.
- Process-local RED latency on diagnostics runtime: average/max `process_time_ms` and `error_rate` over the process lifetime.
- Deterministic frontend bundle budget gate and honest Python 3.13 support claim in CI (audit F-13).
- Build SHA stamped into health/diagnostics/image metadata (`AB_BUILD_SHA` / git fallback) so releases are distinguishable between semver tags (audit F-07).

- Added Checkout-redesign case study section to README with reproducible numbers from backend calculation and Bayesian interim check.
- Regenerated demo screenshots to match v1.1.0 UI (comparison dashboard, webhook manager).
- Seeded the Hugging Face Space demo workspace on startup with an idempotent backend hook so the public demo loads with pre-populated projects.
- Added GitHub Actions workflow `docker-publish.yml` to publish multi-arch Docker images to `ghcr.io/brownjuly2003-code/ab-test-research-designer` on every `v*` tag push.
- Added dynamic shields.io badges (tests count, backend coverage, Lighthouse performance) in README, refreshed by a new CI job `update-metrics-badges` that commits `badges/*.json` back to `main` after green verify + lighthouse runs.
- Added `scripts/collect_badge_metrics.py` plus `--with-coverage` and `--artifacts-dir` flags on `scripts/verify_all.{py,cmd}` so the same collector can run locally and in CI.
- Full de/es UI translation (leaf-key parity with `en` enforced by `scripts/check_locale_content.py`, terminology anchors for A/B-Test / Variante / Referenz and test A/B / variante / línea base).
- Hugging Face Dataset snapshot service (`SnapshotService`) pushing SQLite to a private HF Dataset with sha256 verification, atomic rename, startup restore, and opt-in through `AB_HF_SNAPSHOT_REPO` / `AB_HF_TOKEN` / `AB_HF_SNAPSHOT_INTERVAL_SECONDS`.
- Documentation site (Astro Starlight) at [brownjuly2003-code.github.io/ab-test-research-designer](https://brownjuly2003-code.github.io/ab-test-research-designer/), sourced from `docs-site/` and deployed via `.github/workflows/docs-site.yml` on main push (started as mkdocs-material, migrated to Starlight before release).
- Expanded the template library to 10 industry presets (`email_campaign`, `push_notification_reactivation`, `app_onboarding_drop_off`, `search_ranking_ctr`, `trial_to_paid` added on top of the original 5), with a `TemplateGallery` UI entry point from the sidebar.
- Optional OpenAI / Anthropic LLM adapter with browser-session token routing (`X-AB-LLM-Provider` + `X-AB-LLM-Token` headers, CORS-aware), token masking in logs, and a Settings panel to configure credentials client-side.
- Monte-Carlo distribution view in the comparison dashboard: `simulate_comparison` service (parametric Beta-Bernoulli for binary, Normal bootstrap for continuous, deterministic with `seed=42`), `POST /api/v1/projects/compare?include_monte_carlo=true&monte_carlo_simulations=<1000..50000>` opt-in query, 50-bucket histogram + interactive probability-above-threshold slider.
- French / Simplified-Chinese / Arabic locales with RTL layout support for Arabic (`document.documentElement.dir = "rtl"`, ~10 CSS modules switched to `inset-inline-*` / `margin-inline-*` / `border-inline-*` logical properties), frontend and backend leaf-key parity with `en`, 7-button language switcher with `aria-pressed`.
- Extended Hypothesis property-test coverage for numerical stability (degenerate conversions, zero variance, ultra-strict alpha), Bayesian prior edge cases, SRM imbalance, sequential boundary monotonicity, and Monte-Carlo determinism + cap boundaries.
- Optional Postgres backend via `AB_DATABASE_URL` with pluggable `DatabaseBackend` protocol (SQLite default, Postgres via `psycopg[binary]` when URL scheme is `postgresql://`), connection pooling through `AB_DB_POOL_SIZE`, `/healthz` and `/readyz` probes backend-aware, dedicated `verify-postgres` CI matrix job spinning `postgres:16-alpine` via testcontainers.
- Slack App integration bundled alongside Postgres: `slack/app-manifest.yml` for manifest install, OAuth flow with CSRF state, HMAC SHA256 request signature verification with 5-minute replay guard, `/ab-test projects | status <id> | run <id>` slash commands returning Blocks-formatted responses, interactive approve/request-review buttons.
- `scripts/cleanup_test_artifacts.py` — `--dry-run` aware sweeper for pytest temp roots, `.coverage`, the cxkm sandbox, and the local mkdocs `site/` build. Documented in `docs/RUNBOOK.md` under "Local cleanup".
- `scripts/sync_doc_screenshots.py` — mirrors `docs/demo/*.png` (the smoke source of truth, referenced by README via `raw.githubusercontent.com`) into `docs-site/assets/screenshots/`. Compares SHA-256 to skip unchanged pixels; run manually when screenshots change. Documented in `docs/RUNBOOK.md` under "Screenshots".
- `docs/RUNBOOK.md` Slack section now documents the token-at-rest posture: bot/user tokens are stored plaintext in SQLite/Postgres under the local-first threat model, with explicit guidance for hosted setups (filesystem permissions, sandbox workspaces, rotation via re-running `/slack/install`).

### Changed

- The public Hugging Face Space now runs `AB_ENV=demo` (was the default `local`): the webhook SSRF guard and the HTTPS-only webhook target rule stay active on the public host, matching the fly.toml posture.
- Production responses to unexpected `ValueError`s carry a generic `Invalid value` detail; the real message goes to the server log. Local/demo keep the full validation text.
- Backend `requirements.txt` / `requirements-dev.txt` are now uv-compiled universal locks with sha256 hashes for all packages including transitives; direct dependencies live in `requirements*.in`. The Docker image installs with `--require-hashes`.
- All GitHub Actions are pinned to commit SHAs (with version comments so dependabot keeps bumping them).
- Orchestration decompositions without public API breaks (audit F-11): `live_stats` package, `results` family package, `projectStore` domain slices, typed `apiJsonRequest`/`apiBlobRequest` helper, and `repository/execution` rollup package — facades keep prior import paths.
- Public docs-site curated to an explicit allowlist so internal plan archives no longer publish (audit F-08).
- Runtime Docker image split: production image no longer carries test/lint toolchains; bases pinned with a pre-push scan path (audit F-10).
- Lazy-loaded locale JSONs via `i18next-http-backend` (moved to `app/frontend/public/locales/`); main JS chunk dropped from 247.88 KB to 122.18 KB gzip (-50%). Vendor libs split into `vendor-react` / `vendor-i18n` / `vendor-state` chunks for long-term caching.
- Centralized the noop `ResizeObserver` jsdom stub in `app/frontend/src/test/setup.ts`; removed the per-file `vi.stubGlobal('ResizeObserver', …)` boilerplate that was duplicated across 10 chart/a11y test files. `mockBlobDownloadGlobals(objectUrl?)` helper added to `app/frontend/src/test/dom.ts` for the `URL.createObjectURL` + `HTMLAnchorElement.click` stub block previously duplicated across `App.test.tsx` and `ChartExport.test.tsx`.
- `api_key_used` audit log writes are deferred from the auth middleware hot path to a starlette `BackgroundTask` attached to the response. The synchronous SQLite insert no longer blocks request processing for authenticated traffic. The pending audit is recorded on `request.state.pending_api_key_audit` and attached in `finalize_response()` so it still fires on early-return paths (read-scope POST → 403, rate-limit → 429, body-too-large → 413), preserving the previous audit semantics. Client-visible behavior is unchanged for sequential requests; concurrent observers querying `/api/v1/audit?action=api_key_used` immediately after an authenticated call may briefly miss the entry while the background write completes.
- Postgres CI was extended from a project-creation smoke into a contract suite covering workspace import/export, audit log, API key lifecycle, webhook subscription CRUD, Slack installation upsert, and query-filter pagination. A shared `postgres_repository` module-scoped fixture amortizes the testcontainer pull across the suite.
- `_betacf` (the regularized-beta continued fraction backing Student-t) now emits `StudentTConvergenceWarning` if it ever exhausts its 200-iteration budget; this never fires for `df ≥ 1` and `x ∈ [0, 1]` in practice but guards future numerical regressions instead of returning a silent best-estimate.

### Fixed

- **Audit P0/P1 (2026-07-11):** DSN/credential redaction on diagnostics and logs; production auth fail-fast so anonymous mutations cannot run under production config; count metric vertical contract (save/list/filter/load) across backend+frontend; npm advisory gates on both package roots; truthful CI badge counts waiting on both test suites and all verify jobs.
- **Continuous post-test math:** `analyze_results` for continuous metrics now uses Welch Student-t for both the p-value and the confidence interval (was returning a normal-approximation p-value with a z-critical CI regardless of `df`). New `app/backend/app/stats/student_t.py` implements `t_cdf`/`t_ppf` via stdlib regularized incomplete beta (zero scipy dep); 24 unit cases assert ≤1e-7 / ≤1e-4 vs scipy. Continuous `power_achieved` is now computed (was hardcoded `0.0`) using a two-sided expression (upper + lower tail) so it equals α at zero observed effect instead of α/2.
- **Workspace import atomicity:** `import_workspace()` now opens a `BEGIN IMMEDIATE` transaction explicitly. Default Python `sqlite3` deferred-mode transactions could race across concurrent imports.
- **Snapshot loop resilience:** the periodic HF snapshot push is now wrapped in `try/except` so a transient failure logs and continues instead of killing the background task silently.
- **Rate limiter memory:** `SlidingWindowRateLimiter` periodically prunes buckets whose last event is outside the window. Long-uptime deployments no longer accumulate state for rotated client IPs/API keys.
- **Pytest on Windows:** `pytest.ini` now sets `--basetemp=.pytest_basetemp` so the default `python -m pytest` command works without manual flags. Legacy `app/backend/tests/.tmp/` (~990 MB on long-lived checkouts) removable via new `scripts/cleanup_test_artifacts.py`.
- **Locale parity:** ar/de/es/fr/zh receive the missing `sidebarPanel.slackApp.*` block (12 keys); locale leaf-key counts now match en for all shipped locales.
- **OpenAPI metadata:** `license_info` is now `MIT` (was `UNLICENSED`); the placeholder contact email was removed, eliminating the `email-validator not installed` warning during contract/API-doc generation.
- **Cross-backend audit log:** `log_audit_entry` now uses `INSERT … RETURNING id` instead of `cursor.lastrowid`, which `_PostgresCursorResult` always returns as `None`; audit events were silently dropped from API responses when running on Postgres.
- **Rate limiter prune correctness:** `_prune_locked` now respects the per-call `window_seconds` override stored on each bucket. Previously a bucket with an API-key-specific longer window would be evicted at the global window boundary; the next call with the override saw an empty bucket and silently bypassed its limit.
- `.env.example`: `AB_DB_PATH` and `AB_FRONTEND_DIST_PATH` are now commented templates (the backend already derives absolute defaults from the package location). The earlier relative-path defaults broke through `Path('./...').as_posix()` → `sqlite:///app/...` resolving to absolute `/app/...`. `AB_ADMIN_TOKEN=` added so secure self-hosted setup works from copy-paste.
- Accessibility tests (`PosteriorPlot`, `a11y-results` full-panel, `a11y-comparison-dashboard`) no longer time out: a flat recharts mock in `app/frontend/src/test/recharts-stub.tsx` removes 1000+ SVG nodes per chart from axe's scan, reducing full-panel axe duration from 15-30s to ~3s. The deleted visual `.recharts-area-area` assertion was preserved in a new `PosteriorPlot.integration.test.tsx` using a ResponsiveContainer-only clone-element mock so real recharts renders in jsdom.
- `ProjectRepository` now handles unix-absolute SQLite URLs (`sqlite:////home/user/db.sqlite3`) without doubling the leading slash, fixing `test_diagnostics_endpoint` path assertion on Linux CI.
- Postgres integration tests skip on Windows CI where Docker Linux containers are unavailable (`testcontainers-ryuk` 404 on container create).
- Hypothesis property tests uncovered and fixed degenerate-input guards in `calculations_service`: zero variance continuous, conversion in {0, 1}, `mde = 0`, ultra-strict alpha.
- `verify_all.cmd` no longer masks failures of steps inside parenthesized blocks (frontend build, bundle budget, e2e, lighthouse, smoke, docker flows): `%errorlevel%` expands at parse time inside `( … )` — always 0 — so `exit /b %errorlevel%` reported success on failure. Those exits now return a literal 1.

### Dependencies

- Dependabot debt cleared to zero open unaddressed PRs. Minor/patch groups: backend pip (pydantic 2.13.4, psycopg 3.3.4, uvicorn 0.51.0, pypdf 6.14.2, pytest 9.1.1, playwright 1.61, hypothesis 6.156, testcontainers 4.14, ruff 0.15.22), frontend npm (11 packages incl. react patch), docs-site (sharp 0.35, starlight 0.41, yaml 2.9). Majors: TypeScript 7.0.2, Astro 7.1.0, mypy 2.3.0 (two now-unused `type: ignore` comments removed), and the coupled vite 8.1.5 + `@vitejs/plugin-react` 6.0.3 + vitest 4.1.10 cluster. GitHub Actions: upload-artifact 7, docker setup-qemu 4 / metadata 6 / build-push 7. Deliberately deferred pending a runtime decision: Python 3.14-slim and Node 26 Docker bases.
- pydantic 2.13 stopped splitting identical input/output schema variants, so the generated frontend contract (`api-contract.ts`) uses unified names (`ExperimentInput` instead of `ExperimentInput_Input`/`_Output` etc.).
- vite 8 (rolldown) migration: `manualChunks` moved from object to function form (same vendor split); the test helper `mockBlobDownloadGlobals` now stubs `URL.createObjectURL`/`revokeObjectURL` on a `URL` subclass instead of replacing the global, because the vite module runner constructs `URL`s while lazy-loading chunks inside tests.
- Dependabot's lock edits are superseded by uv-recompiled locks (`uv pip compile --universal --generate-hashes`); dependabot regenerates `requirements*.txt` without platform markers, which silently drops win32-only packages (`colorama`) and breaks Windows installs.

### Security

- Repository security features enabled: Dependabot alerts, secret scanning, and push protection.

## [1.1.0] - 2026-04-21

### Added

- multi-project comparison dashboard with lazy-loaded React chunk, power curves, sensitivity grid, forest-plot observed effects, and shared/unique insight panels, plus `POST /api/v1/projects/compare` and `POST /api/v1/export/comparison` (Markdown and PDF)
- outbound webhook subscriptions (Slack and generic JSON) with admin-guarded CRUD, delivery history, retry/dead-letter tracking, and HMAC-signed `X-AB-Signature` headers for generic consumers
- property-based statistical test suite (`hypothesis==6.152.1`) covering monotonicity and round-trip invariants for binary, continuous, SRM, group-sequential, and Bayesian calculators
- German (`de`) and Spanish (`es`) UI and report locales with `Accept-Language` regional fallback on the backend; header switcher now ships all four languages

### Changed

- `resolve_language` now accepts any registered primary language tag and returns it directly instead of an explicit `en`/`ru` ladder
- bumped backend `app_version` default and frontend `package.json` to `1.1.0`

## [1.0.0] - 2026-04-22

### Added

- experiment template gallery with five YAML presets for common test scenarios (`319820a0`)
- shareable HTML and Markdown reports plus stored project PDF/CSV/XLSX exports for deterministic analysis output (`8413328e`)
- project list filters for faster workspace triage (`0cdfa379`)
- keyboard shortcut help for save, run, and export flows (`0cdfa379`)
- project audit log endpoint and persisted request trail metadata (`7eac8f59`)
- deterministic SRM checks, Bayesian sizing, group sequential boundaries, and CUPED-aware calculations in the shipped analysis stack (`8413328e`)
- multi-metric guardrail planning and report sections across backend and UI (`8413328e`)
- Recharts-powered visualisations, result cards, and sensitivity views in the redesigned frontend (`5ea60181`)
- theme toggle for the refreshed dashboard interface (`5ea60181`)
- expanded axe accessibility coverage across wizard, results, sidebar, and modal flows (`9882d079`)
- Lighthouse CI verification against the backend-served frontend with enforced thresholds (`7a156794`)

### Changed

- decomposed `App` and `ResultsPanel` into smaller route- and store-backed frontend modules for the BCG release wave (`8413328e`)
- moved wizard, analysis, project, draft, and theme state into dedicated Zustand stores (`8413328e`)
- refreshed the UI icon system around Lucide components and the new visual design layer (`5ea60181`)
- regenerated the frontend API contract and backend API docs alongside templates, filters, audit, and report endpoints (`7eac8f59`)
- hardened the workspace backup and recovery flow for local verification and restore drills (`a1d8606c`)

### Fixed

- resolved wizard, dialog, and menu accessibility regressions surfaced by the expanded axe suite (`9882d079`)

## 2026-03-09

### Release hardening

- removed build-time frontend token injection and switched the UI to browser-session API tokens
- made the frontend fail closed for write actions until backend diagnostics explicitly confirm write-capable access
- split soft archive from permanent delete so `POST /api/v1/projects/{id}/archive` preserves history while `DELETE /api/v1/projects/{id}` hard-deletes it
- added optional HMAC-signed workspace backups via `AB_WORKSPACE_SIGNING_KEY`, plus signed import/validate enforcement and runtime diagnostics for backup-signing mode
- extended local verify wrappers, Docker verification, and CI wiring to cover signed workspace backup flows and removed the obsolete `VITE_API_TOKEN` path from CI
- made `scripts/verify_all.ps1` a thin delegation wrapper to the canonical batch verify path so Windows verification no longer drifts
- fixed workspace export/import round-trip regressions so exported bundles now validate and reimport cleanly with matching checksums
- normalized repository boolean fields for project list responses and closed the broken workspace import SQL insert path
- regenerated frontend API contracts and API docs to match the current backend/archive schema
- stabilized the smoke flow around free-port backend startup, browser draft persistence checks, and refreshed demo screenshots
- replaced the Playwright E2E launch path with a self-contained runner that builds the frontend when needed, starts a temporary backend on a free port, and cleans it up after the run
- aligned local verify scripts and CI Playwright installation syntax with the hardened E2E path
- re-ran full local verification, including `python scripts/verify_all.py --with-e2e`

## 2026-03-08

### UI modernization

- redesigned the frontend into a dashboard-style interface with metric cards, accordion sections, timeline history, live backend status, progress bar, tooltips, and loading spinners
- added a workspace status board that summarizes saved-project coverage, snapshot depth, export reach, revision depth, and current draft sync state
- made the frontend auth-aware so read-only API sessions disable save, analysis, report export, workspace import, and delete actions instead of failing at runtime
- upgraded typography to Inter + JetBrains Mono and added dark-mode support
- surfaced browser draft storage issues as dismissible UI toasts
- added a quota-specific autosave warning for `QuotaExceededError` while keeping generic storage failure details for other browser-local errors

### Backend and contracts

- added explicit `bonferroni_note` to calculation responses for multivariant designs
- regenerated frontend API contracts from FastAPI OpenAPI
- kept deterministic calculations, warnings, saved-project history, and comparison flows aligned with the new UI
- added backend performance regression coverage with a `<100ms` p95 guard for deterministic calculations
- added `GET /api/v1/diagnostics` with storage/frontend/LLM runtime summary
- added `X-Request-ID` and `X-Process-Time-Ms` headers for lightweight request tracing
- expanded saved-project comparison contracts with executive summaries, warning severity, overlap sections, and comparison highlights
- added `GET /readyz` for runtime readiness checks with `503` on degraded dependencies
- added workspace export/import APIs and UI actions for project/history backup and restore
- added saved-project revision history across create, update, and workspace import flows
- added `GET /api/v1/projects/{project_id}/revisions` plus frontend restore of older payload revisions
- added SQLite schema version reporting plus configurable journal mode, synchronous mode, and busy-timeout diagnostics
- added structured backend logging with configurable plain/json output
- added config validation for invalid ports and broken LLM retry/backoff settings
- expanded CI to also verify the repo on Windows and to check generated API docs
- added workspace backup roundtrip verification to the local/CI verify path
- added optional API token auth for `/api/v1/*`, `/readyz`, and local API docs
- added frontend bearer-token support through `VITE_API_TOKEN` at that stage; this path was later superseded by browser-session tokens
- added optional read-only API token support for safe runtime requests while keeping mutations behind the write token
- hardened Docker packaging with build-time frontend token injection, runtime defaults, container healthchecks, and secure compose verification; the build-time token path was later removed
- added workspace backup integrity manifests with entity counts and SHA-256 checksum validation on import
- added `POST /api/v1/workspace/validate` so workspace bundles can be preflight-checked before SQLite writes begin
- added structured API error payloads with `error_code`, `status_code`, `request_id`, and `X-Error-Code`
- added in-memory runtime request/error counters to diagnostics for lightweight observability
- extended diagnostics and readiness with SQLite write-probe, db-size, parent-path, and free-disk reporting

### Documentation and packaging

- added architecture, API, and rules documentation
- aligned the Python verify entrypoint with the Windows batch verify flow, including generated API docs and optional Playwright E2E
- added benchmark script and Docker packaging
- consolidated docs and demo assets for README-driven walkthroughs
- added `docs/RUNBOOK.md` and `docs/RELEASE_CHECKLIST.md` for local operations and release hygiene
- added documented backup roundtrip drill for SQLite workspace restore verification
- added GitHub Actions verification and refreshed smoke/demo automation around the sample import payload
- added a runnable Playwright E2E command, backend launcher, CI browser step, and a few extra statistical boundary regressions

## Earlier milestones

- local SQLite project CRUD, export, history, and comparison flows
- combined `POST /api/v1/analyze`
- local smoke test coverage against the backend-served frontend
- OpenAPI-generated frontend contracts and one-command verification
