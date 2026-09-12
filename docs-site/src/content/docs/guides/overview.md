---
title: "Project overview"
editUrl: "https://github.com/brownjuly2003-code/ab-test-research-designer/edit/main/README.md"
---

<!-- docs-site:index:start -->
# Trialmark / AB Test Research Designer

This repository contains two tracks.

**Legacy (stable):** A/B research designer. Published release
[`v1.3.1`](https://github.com/brownjuly2003-code/ab-test-research-designer/releases/tag/v1.3.1)
(tag `v1.3.1`, commit `bb314ae15c86eaf2ade77d3a111a66030b77573e`) in the public
repository [ab-test-research-designer](https://github.com/brownjuly2003-code/ab-test-research-designer).
Seven UI locales. CI is green on the release tag.

**Experimental evidence layer (`evidence-0.1` public preview):** the persisted application,
Workbench, statistical preflight, sequential design, allocation-aware sizing,
independent oracle, method guarantee profile, and DSSE decision statements are
implemented through phase C. External validation remains gated.
**Not a stable release; backward compatibility and external adoption are not
claimed.** Reproduce the public ASOS tamper demo in the
[`evidence-0.1` branch](https://github.com/brownjuly2003-code/ab-test-research-designer/tree/evidence-0.1).

Start with the [documentation map](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/README.md). Target architecture:
[docs/architecture/TRIALMARK_ARCHITECTURE.md](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/architecture/TRIALMARK_ARCHITECTURE.md).
ADRs: [modular monolith](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/adr/0003-evidenceos-modular-monolith.md),
[ABX container](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/adr/0004-abx-container-and-integrity.md),
[Trialmark rename](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/adr/0005-trialmark-rename.md),
[format identifiers](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/adr/0006-abx-format-identifiers.md).

## Legacy baseline

[![Release](https://img.shields.io/github/v/release/brownjuly2003-code/ab-test-research-designer?include_prereleases&display_name=tag)](https://github.com/brownjuly2003-code/ab-test-research-designer/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-24%20LTS-green.svg)](https://nodejs.org/)
[![Tests](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/generated/badges/badges/tests.json)](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/workflows/test.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/generated/badges/badges/coverage.json)](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/workflows/test.yml)
[![Lighthouse](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/generated/badges/badges/lighthouse.json)](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/workflows/test.yml)
[![Docs](https://img.shields.io/badge/docs-astro--starlight-blue)](https://brownjuly2003-code.github.io/ab-test-research-designer/)

Local-first experiment planning tool for A/B and multi-variant tests. Plan sample size and duration from the wizard, review deterministic statistical guidance (SRM, Bayesian, group-sequential, CUPED) plus design-time guardrail-metric recommendations, compare saved experiments side by side, and export reports in the legacy UI in seven languages (English, Russian, German, Spanish, French, Simplified Chinese, Arabic with RTL) — all against a local SQLite workspace with no cloud required.

Built with **FastAPI + React 19 + TypeScript + Vite + SQLite**. The published legacy release is verified end-to-end via `scripts/verify_all.cmd --with-e2e` — backend and frontend unit suites, Playwright E2E, Lighthouse CI, and axe accessibility checks. The Tests / Coverage / Lighthouse badges above report that public `ab-test-research-designer` release, not this fork's HEAD. Backend line coverage is gated at 88%+ in that CI.

It combines:

- deterministic sample size and duration calculation
- heuristic warnings and feasibility checks
- deterministic experiment design output
- optional local LLM recommendations
- SQLite-backed project storage with history and export metadata
- lightweight runtime diagnostics plus request-id / process-time headers
- baseline security headers, API rate limiting, auth-failure throttling, and request-body size guards
- SQLite schema versioning plus configurable WAL/busy-timeout runtime settings
- optional API token protection for runtime and project APIs
- workspace backup and restore for saved projects plus history, integrity counts, checksums, and optional HMAC signatures
- preflight workspace validation before import, plus runtime SQLite write-probe diagnostics
<!-- docs-site:index:end -->

## Project status

**Legacy stable v1.3.1** is the published A/B research designer
(tag `v1.3.1`, commit `bb314ae15c86eaf2ade77d3a111a66030b77573e`). That track is
feature-frozen. Historical/research-plan disposition, preserved local artifacts,
and release evidence (Actions, GHCR) are recorded in
[docs/PROJECT_CLOSURE.md](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/PROJECT_CLOSURE.md).

This repository's HEAD is a fork with the experimental evidence layer; it is
not the published `v1.3.1` tag. The release evidence remains pinned to that tag;
the experimental implementation status is recorded in this README, the
[changelog](/ab-test-research-designer/guides/changelog/), and the
[Trialmark architecture](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/architecture/TRIALMARK_ARCHITECTURE.md).

## Trialmark persisted evidence CLI

The experimental `trialmark` CLI runs a supported frozen YAML protocol against
an aggregate source, persists the completed evidence run, and publishes an
offline-verifiable `.tmk` bundle. It also records append-only human decisions,
lists persisted runs, and writes anonymous external-pilot records.

Questions, reproducibility reports, and requests for a 30-minute aggregate-CSV
pilot are welcome through [GitHub Issues](https://github.com/brownjuly2003-code/ab-test-research-designer/issues/new).

Two source profiles are supported, selected by the single `extensions` key the
protocol declares:

| `extensions` key | Source | Used by |
| --- | --- | --- |
| `trialmark.asos` | aggregate ASOS Parquet | the public benchmark and the demo |
| `trialmark.aggregate-binary` | one-row aggregate CSV | external pilots |

A protocol must declare exactly one of them.

Run commands from the repository root after installing the backend dependencies
described in [Local setup](#local-setup). The repository does not need an
editable install:

```text
python -m app.backend.app.evidence.cli --help
```

To install the shorter console command without changing dependencies:

```text
python -m pip install -e . --no-deps
trialmark --help
```

### Storage configuration

Persisted commands use the application database selected by
`AB_DATABASE_URL`, or by `AB_DB_PATH` when no database URL is set. Artifact
payloads go to `AB_ARTIFACT_ROOT`, which defaults to `.trialmark/artifacts`
relative to the current directory and is resolved to an absolute path once at
startup.

Set both for the whole workflow and no command needs a flag:

```powershell
$env:AB_DB_PATH = "D:\trialmark-data\trialmark.sqlite3"
$env:AB_ARTIFACT_ROOT = "D:\trialmark-data\artifacts"
```

The relative default is fine inside one checkout and wrong as soon as two
processes have different working directories: an API server started from
elsewhere resolves `.trialmark/artifacts` against its own directory and
answers `404` for a run the CLI had just written. `AB_ARTIFACT_ROOT` is the
fix, and `GET /readyz` reports the resolved path and whether it is writable.

`--artifact-root` still overrides it on `run`, `decide`, `runs list` and
`pack --run`, for an operator working across two trees.

### Run, verify, and decide

Create and publish an analysis bundle:

```text
python -m app.backend.app.evidence.cli run --protocol protocol.yaml --source experiment.parquet --actor analyst-01 --out analysis.tmk
```

The JSON result includes `valid`, `run_id`, `bundle_id`, and the verifier
`verdicts`. Save `run_id`; decisions cite the persisted analysis run, not the
archive filename.

Verify the archive without network or source access:

```text
python -m app.backend.app.evidence.cli verify analysis.tmk --offline --policy strict
```

Record a human decision as a new immutable child run and publish its bundle:

```text
python -m app.backend.app.evidence.cli decide --run RUN_ID_FROM_THE_ANALYSIS_RESULT --verdict ship --rationale "The verified evidence meets the frozen decision policy." --actor reviewer-01 --out approved.tmk

python -m app.backend.app.evidence.cli verify approved.tmk --offline --policy strict
```

`--verdict` accepts `ship`, `hold`, or `stop`. If `--actor` is omitted, the
CLI uses `$USER`, then `local-operator`. A decision never overwrites its parent;
another decision creates another child run.

`--role` names the approval role to decide under. It must be one the run's
frozen `decision.approval_policy.roles` lists, or the command exits 1 with
`role_not_permitted`. The recorded decision says where the role came from, in
`decided_by.role_source`:

| Value | Meaning |
| --- | --- |
| `credential` | The authenticated API key carries the role. The only source the service verifies. |
| `asserted` | The caller named it (`--role`). Nothing here checks the claim. |
| `policy_default` | No role was declared; the policy's first approval role applied. |

Issue a key that carries a role with `POST /api/v1/keys` and a `role` field.
A protocol whose `approval_policy.minimum_approvals` is above 1 cannot be
decided at all: recording writes one approval, so the command exits 1 with
`approval_quorum_unmet` rather than publish a decision that claims a quorum it
does not have.

The final decision member is `decision/statement.dsse.json`: an unsigned DSSE
envelope whose payload is an in-toto Statement v1. Its subject SHA-256 is the
parent analysis bundle identity, and its Trialmark decision predicate retains
the reviewed decision record. `verify` reports the statement type, predicate
type, subject, signature count, and whether the subject matches `supersedes`.
An empty signature list provides digest binding, not signer identity; signing
and Sigstore policy are outside this profile.

### External pilot: one aggregate binary metric from a CSV

An external partner never sends user-level rows. The `trialmark.aggregate-binary`
profile accepts exactly one metric and exactly one CSV row with these four
columns, in any order:

```text
control_users,control_conversions,treatment_users,treatment_conversions
1000,100,1200,144
```

The protocol binds that source with an `extensions` block. The
`definition_digest` of the primary metric is the SHA-256 of the canonical JSON
of `metric.definition`, so the metric a partner reports and the metric the
protocol froze cannot drift apart:

```yaml
extensions:
  trialmark.aggregate-binary:
    schema_version: "1"
    source_ref: pilot_source_alpha
    evidence_type: external_pilot
    partner_approved: true
    metric:
      name: Checkout conversion rate
      direction: increase
      unit: proportion
      owner_ref: pilot_growth_team
      definition:
        aggregation: binary_rate
        numerator: converted_subjects
        denominator: assigned_subjects
    observed_telemetry:
      outcome_before_exposure_count: 0
      duplicate_event_count: 0
      unlinked_subject_count: 0
      events_beyond_max_lateness_count: 0
      schema_versions:
        - event_type: aggregate_assignment
          version: pilot-v1
          schema_digest: sha256:4937ce9031149ec2f5cd04a27e51ca296415ff4856ea4e4bf700091dc66ce31b
        - event_type: aggregate_metric_checkpoint
          version: pilot-v1
          schema_digest: sha256:272f65a1c66d17f18ba326a2da6bfe29833422589121cac3c0e14478b7b4c2d3
```

Check the file before spending a session on it. `source validate` runs the
same source checks a `run` would, and nothing else: no database, no run, no
bundle, no writes anywhere.

```text
python -m app.backend.app.evidence.cli source validate --protocol examples/pilot/protocol.yaml --source examples/pilot/aggregate.csv
```

It answers `valid: true` with the metric id, the `definition_digest`, the
columns it found and the four counts it read, or `valid: false` with the
reason stated concretely enough to act on — the expected columns beside the
ones the file actually has, `found 3` rows where one was required, or both
digests when the protocol's metric and the source's definition have drifted
apart. Exit status is 0 for a valid source and 1 otherwise.

A complete, runnable pair lives in [`examples/pilot/`](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/examples/pilot/). It uses
the same `run` / `verify` / `decide` commands as any other protocol:

```text
python -m app.backend.app.evidence.cli run --protocol examples/pilot/protocol.yaml --source examples/pilot/aggregate.csv --actor pilot-operator --out pilot.tmk

python -m app.backend.app.evidence.cli verify pilot.tmk --offline --policy strict
```

The published bundle is aggregate-only: it carries no source path, no partner
identity, and no rows. `observed_telemetry` is recorded as
`telemetry_profile_source: upstream_asserted` — the partner asserts those
counts, Trialmark does not observe them.

### Recording an external pilot session

`pilot-session` writes the anonymous record of one observed session. It reads
the published bundle for its census and accepts no source path and no identity:

```text
python -m app.backend.app.evidence.cli pilot-session create --participant-ref anon_0123456789abcdef --source-ready-at 2026-09-07T10:00:00Z --bundle-ready-at 2026-09-07T10:12:00Z --outcome completed --bundle pilot.tmk --out docs/pilots/2026-09-07-anon_0123456789abcdef.md

python -m app.backend.app.evidence.cli pilot-session validate docs/pilots/2026-09-07-anon_0123456789abcdef.md
```

`--participant-ref` must match `anon_<16 hex>`, and the filename must be exactly
`<session-date>-<participant-ref>.md`, where the session date comes from
`--source-ready-at`. `--outcome incomplete` records a session that produced no
bundle and omits `--bundle`/`--bundle-ready-at`. A second observation of the
same participant is recorded with `--reuse-kind second_run|evidence_reopen` and
`--reuse-at`; both are required together. A record is never overwritten.

### Deciding Gate 3 from the records

`gate3` aggregates a directory of validated pilot records into the Gate 3
decision. It reads nothing else -- no clock, no network, no database -- so the
same cohort always produces the same report and the same `report_digest`:

```text
python -m app.backend.app.evidence.cli gate3 --records docs/pilots --out docs/gates/gate3_2026-09-08.md
```

Every `.md` file under `--records` must be a canonical pilot record. A file
that is not one is an error, not a skip, because quietly dropping an
unparseable record would take a partner out of the denominator and report the
gate as better than it is. Keep notes elsewhere.

Six criteria are reported with the arithmetic behind each verdict:

| Criterion | Threshold |
| --- | --- |
| Completed pilots | at least 3 partner cycles completed protocol → preflight → bundle |
| Repeated partner use | at least 2 partners started a second experiment or reopened evidence |
| Time to first reviewable bundle | partner-session median at or under 900 seconds |
| Preflight detection / harm | detection ≥ 90%, false blocking < 5% |
| Displayed-estimate lineage | 100% of displayed estimates carry complete lineage |
| Bundle privacy | no raw user-level pilot data enters a bundle |

Two counting rules decide what the numbers mean. **One partner is one cycle**:
two records from the same `participant_ref` count once toward completed cycles,
and the second contributes only if it records reuse. **A criterion nobody
measured is never reported as passed**: preflight detection is a property of
the engineering suite rather than of a partner session, so this report always
calls it `unmeasured` and says where it is measured instead. Thresholds stated
as an absolute count can be measured as zero and therefore *fail* on an empty
cohort; thresholds stated as a rate have no denominator to rate and stay
`unmeasured`.

The final verdict is `continue` when every criterion measurable from records
passes, `stop` when no partner completed a cycle at all, and `pivot` in
between. The exit status is 0 for all three: `stop` is a successful
measurement of a disappointing cohort, not a failed command. Read `verdict`,
not `$?`.

List persisted runs and their bundle identities and verifier verdicts:

```text
python -m app.backend.app.evidence.cli runs list
```

All bundle destinations must end in `.tmk`, and the CLI refuses to overwrite
an existing destination. Argument errors exit with status 2. Command or
verification failures emit JSON and exit with status 1; successful commands
exit with status 0.

## Demo

### Trialmark evidence demo in five minutes

For the motivation, exact ASOS scope, observed result, and a repeatable
tamper-demo, see
[Evidence должно пережить вендора](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/article/trialmark-asos-tamper-demo.md).

The short real-product walkthrough below opens the generated MP4. It follows a
persisted blocker through remediation, analysis, bundle review, and a separate
human decision without using a mockup.

[![Trialmark Workbench ASOS walkthrough](/ab-test-research-designer/demo/trialmark-workbench-demo.png)](docs/demo/trialmark-workbench-demo.mp4)

With the development dependencies, Playwright Chromium, and `ffmpeg` available,
regenerate both artifacts from the real local UI with:

```bash
python scripts/record_trialmark_demo.py
```

With the backend dependencies installed, run this from a clean checkout on
macOS or another POSIX shell:

```bash
bash examples/demo/run_demo.sh
```

The script uses the committed aggregate-only ASOS `d53f0e` fixture. It first
proves that a metric-role conflict, injected 90/10 assignment imbalance, and one
late event each produce a specific blocking preflight finding. It then runs the
corrected [frozen protocol](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/examples/demo/protocol.yaml), records an append-only
human decision, verifies the final `.tmk` bundle offline, appends one byte to a
copy, and proves strict verification rejects the changed archive. The JSON
output includes the temporary output directory, both bundle identities, all
three blocker codes, and the expected tamper-verification failure. The
benchmark question and its limitations are recorded in
[examples/demo/question.md](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/examples/demo/question.md).

### Legacy local product demo

The legacy UI demo is the **local seeded product** on a single UI/API port.

First-time setup (creates `.venv`, installs backend deps, builds the frontend):

```bash
python scripts/run_local.py --bootstrap
```

Subsequent runs:

```bash
python scripts/run_local.py
```

Seeded demo workspace (four sample projects with analysis runs and live-experiment data):

```bash
python scripts/run_local.py --seed-demo
```

Then open **http://127.0.0.1:8008**. The seed is idempotent and loads checkout conversion, pricing sensitivity, onboarding completion, and feed ad click-through ratio so the sidebar and history views are populated.

[![GHCR](https://img.shields.io/github/v/tag/brownjuly2003-code/ab-test-research-designer?label=ghcr.io&logo=docker)](https://github.com/brownjuly2003-code/ab-test-research-designer/pkgs/container/ab-test-research-designer)

Container and self-host packaging: [docs/DEPLOY.md](/ab-test-research-designer/guides/deploy/). Legacy stable: **[v1.3.1](https://github.com/brownjuly2003-code/ab-test-research-designer/releases/tag/v1.3.1)** ([release notes](/ab-test-research-designer/guides/release_notes_v1-3-1/); packaging: [fly.toml](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/fly.toml)). Publication and acceptance of that release are GitHub (source, Actions, Pages, Releases, GHCR) plus this local runtime — not a hosted third-party demo.

Sample import payload:

- [docs/demo/sample-project.json](/ab-test-research-designer/demo/sample-project.json)

Current workflow screenshots are generated by the smoke script into `docs/demo/`.
The smoke flow seeds saved demo projects, loads the onboarding example in the wizard,
runs analysis, captures comparison and webhook views, and exports a report:

![Wizard overview](/ab-test-research-designer/demo/wizard-overview.png)
![Review step](/ab-test-research-designer/demo/review-step.png)
![Results dashboard](/ab-test-research-designer/demo/results-dashboard.png)
![Multi-project comparison](/ab-test-research-designer/demo/comparison-dashboard.png)
![Webhook manager](/ab-test-research-designer/demo/webhook-manager.png)

The screenshots follow the legacy product path: wizard overview, review step, and the post-analysis results dashboard.
They then switch to saved-project comparison to show the multi-project power-curve and forest-plot dashboard with seeded snapshots.
The final image shows the admin-side webhook manager with a seeded Slack-style subscription in the sidebar tools area. The Slack App flow adds OAuth installation and `/ab-test` commands alongside the older one-way webhook path.

<!-- docs-site:case-study:start -->
## Case study: Checkout redesign

Retailer testing two checkout variants against control to lift conversion from a 4.2% baseline.

**Setup** - 80k daily visitors, 50% share into test, 3 variants (34/33/33), alpha = 0.05, power = 0.80, two-sided, relative MDE = 10%.

**Sizing (from `POST /api/v1/calculate`).**

| Metric | Value |
| --- | --- |
| Per-variant sample | 45,429 users |
| Total sample | 136,287 users |
| Required duration | 4 days |
| Bonferroni adjustment | 2 treatment-vs-control comparisons, adjusted alpha 0.025 |

**Design guidance (from `POST /api/v1/design`).**
- Primary risk: More than two variants trigger a Bonferroni alpha correction. This is conservative and may overstate the required sample size.
- Key recommendation: Validate tracking and assignment before exposing live traffic.
- Guardrail to monitor: Payment error rate

**Interim check.**
An early snapshot came in after 1.2 test-days, 48,000 visitors, and 3,812 conversions (35.2% of the planned per-variant sample):
- P(variant A > control) = 93.4%
- P(variant B > control) = 99.8%
Variant A is still ambiguous; variant B is the only treatment with a decisive early signal.

**Decision.**
Stop spending exposure on variant A, keep variant B against control until the planned read is complete, and ship B only if payment error rate and refund value stay in range. The value here is that sizing, multivariant correction, design risks, and the Bayesian interim view all come from the same backend run.

Full inputs and outputs: [docs/case-studies/checkout-redesign.json](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/case-studies/checkout-redesign.json). Rerun with `python scripts/generate_case_study_numbers.py`.
<!-- docs-site:case-study:end -->

## Roadmap

Post-v1.1.0 Tier 2/3 roadmap items are all landed as of 2026-04-25.

**Landed:**
- **Portfolio polish.** Local startup seed / demo workspace, product screenshots, case-study section, GHCR Docker publish, dynamic shields.io badges.
- **Product quality.** Locale parity at 940 leaf keys across all shipped legacy UI locales (en/ru/de/es/fr/zh/ar — including the Slack-App admin block), optional OpenAI/Anthropic adapter via browser-session token, Astro Starlight docs site at [brownjuly2003-code.github.io/ab-test-research-designer](https://brownjuly2003-code.github.io/ab-test-research-designer/), 10-template industry gallery.
- **Hardening.** Monte-Carlo distribution overlay with interactive probability slider, French / Simplified-Chinese / Arabic locales (+RTL for Arabic), extended Hypothesis property coverage (numerical stability + Bayesian edges + Monte-Carlo determinism), bundle optimization (main chunk 247 → 122 KB gzip via lazy-load locales + vendor chunks), optional Postgres backend via `AB_DATABASE_URL` with CI matrix coverage, Slack App integration with OAuth install + slash commands + interactive actions.

**Dropped as out-of-scope for a portfolio/demo:** manual NVDA / JAWS audit (automated axe a11y coverage sufficient here).

## Product shape

- Frontend: React 19 + TypeScript + Vite
- Backend: FastAPI + Pydantic
- Storage: SQLite
- Optional AI path: local orchestrator adapter with retry/backoff
- Verification: backend tests, frontend unit tests, typecheck, build, smoke, Playwright E2E
- CI: [.github/workflows/test.yml](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/.github/workflows/test.yml)
- Container image published to GHCR on each tag (`linux/amd64`, `linux/arm64`)
- canonical cross-platform verification entrypoint: [verify_all.py](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/scripts/verify_all.py) and [verify_all.cmd](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/scripts/verify_all.cmd)

## Main capabilities

- wizard-based experiment input with review step
- deterministic calculations for binary and continuous metrics
- twenty-two-analyzer post-hoc results engine spanning independent two-sample, paired within-subject, omnibus (>2 group), and survival (time-to-event) designs across binary, continuous, ratio, count, and categorical metrics (two-proportion z, Fisher's/Boschloo's/Barnard's exact, Welch's t, TOST equivalence, Mann–Whitney U, bootstrap/permutation, quantile treatment effect, Yuen–Welch trimmed t-test, ratio delta method, Poisson rate, chi-square r×c + Cramér's V, G-test, paired t, Wilcoxon signed-rank, McNemar, Welch's ANOVA, Kruskal–Wallis, log-rank, Fleming–Harrington weighted log-rank, Cox proportional hazards) — see [Statistical repertoire](#statistical-repertoire)
- live-experiment monitoring: SRM detection, sequential (O'Brien–Fleming) and always-valid boundaries, Bayesian P(B>A), multi-covariate CUPED, post-stratification, guardrail metrics with non-inferiority margins, holdout cumulative read, ratio delta-method, identity resolution, late/out-of-order event detection, and a bot/fraud filter
- Bonferroni-aware multivariant sizing notes
- warning engine for traffic, duration, seasonality, campaigns, and design quality
- deterministic report with design, metrics plan, risks, and recommendations
- optional AI advice kept separate from the hard-math output
- optional OpenAI and Anthropic adapters via browser-session token, without backend key persistence
- local project save, load, update, archive, restore, compare, history, and export flows
- saved-project revision history with payload restore into the wizard
- richer snapshot comparison with assumption/risk overlap and recommendation highlights
- full workspace export/import for project, analysis, export-history, and revision backup
- workspace import preflight validation with checksum/reference verification before writes begin
- browser draft restore/autosave plus JSON draft import/export
- workspace status board summarizing saved-project coverage, snapshot depth, exports, and current draft sync state
- read-only aware frontend mode that hides write actions for read-only sessions while keeping every stateless calculator available; `AB_PUBLIC_DEMO=true` turns this into an anonymous public-demo entry with a guest landing over the seeded demo projects

## Statistical repertoire

<!-- method-profile-table:start -->
| Supported method | Estimands (test / interval) | Error control | Asymptotic floor | Numeric reference | Determinism / allocation | Oracle evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `binary_pooled_z_newcombe` (`binary_pooled_z_newcombe_v1`) | `risk_difference` / `risk_difference` | fixed horizon; two_sided; α=0.05 (bundle-specific) | n≥30/arm; expected count≥5 | statsmodels 0.14.6; max Δ(z/p/CI)=4.061e-05 / 4.505e-07 / 4.850e-07 | closed form=true; equal allocation required=false | `binary_pooled_z_newcombe` @ `5c65c0d3` |
<!-- method-profile-table:end -->

Post-hoc analysis (`POST /api/v1/results`, plus dedicated `/api/v1/results/ratio`, `/api/v1/results/categorical`, `/api/v1/results/paired`, `/api/v1/results/omnibus` and `/api/v1/results/survival` endpoints) covers twenty-two analyzers across independent two-sample, paired within-subject, omnibus (more-than-two-group), and survival (time-to-event) designs. Each request declares a `metric_type` (or a `test_type` on the dedicated endpoints); the backend validates the matching data shape and rejects mismatches.

| Analyzer | Binary | Continuous | Ratio | Count | Categorical | Survival | `metric_type` / endpoint | Notes |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | --- | --- |
| Two-proportion z-test | ✓ | | | | | | `binary` | Standard proportion significance test |
| Fisher's exact test | ✓ | | | | | | `fisher_exact` | Exact 2×2 test, no normal approximation; capped at 500k total observations |
| Boschloo's exact test | ✓ | | | | | | `boschloo_exact` | Unconditional exact 2×2 test, uniformly at least as powerful as Fisher's; capped at 200 total observations |
| Barnard's exact test | ✓ | | | | | | `barnard_exact` | Unconditional exact 2×2 test ordering tables by the pooled Wald z statistic; capped at 200 total observations |
| Welch's t-test | | ✓ | | | | | `continuous` | Unequal-variance two-sample mean comparison |
| TOST equivalence | | ✓ | | | | | `equivalence` | Two one-sided tests for "no meaningful difference" |
| Mann–Whitney U | | ✓ | | | | | `mann_whitney` | Distribution-free rank test; exact for ≤30 tie-free samples, asymptotic otherwise; reports Hodges–Lehmann shift and rank-biserial effect size |
| Bootstrap / permutation | | ✓ | | | | | `bootstrap` | Resampling test, no distributional assumption; exact enumeration for small samples, fixed-seed Monte Carlo otherwise |
| Quantile treatment effect | | ✓ | | | | | `quantile` | Permutation test on any quantile (default: median), not just the mean |
| Yuen–Welch trimmed t-test | | ✓ | | | | | `trimmed_t` | Robust mean comparison with tail trimming |
| Ratio delta method | | | ✓ | | | | `/results/ratio` | Raw per-user numerator/denominator pairs; reports the delta-method ratio difference with covariance-aware variance |
| Poisson rate | | | | ✓ | | | `count` | Event-rate comparison via a conditional binomial test; capped at 1M events |
| Chi-square r×c + Cramér's V | | | | | ✓ | | `/results/categorical` (`chi_square`) | Independence test across more than two arms/categories; includes a Cochran low-expected-count warning |
| G-test (likelihood-ratio) | | | | | ✓ | | `/results/categorical` (`g_test`) | Likelihood-ratio independence statistic on the same r×c table; shares the chi-square reference distribution and Cramér's V |
| Paired t-test | | ✓ | | | | | `/results/paired` (`paired_t`) | Paired (within-subject) mean comparison on per-pair differences; reports Cohen's dz |
| Wilcoxon signed-rank | | ✓ | | | | | `/results/paired` (`wilcoxon`) | Distribution-free paired test; Hodges–Lehmann pseudomedian and rank-biserial effect size |
| McNemar | ✓ | | | | | | `/results/paired` (`mcnemar`) | Paired binary test on discordant pairs; exact binomial or continuity-corrected chi-square |
| Welch's ANOVA | | ✓ | | | | | `/results/omnibus` (`welch_anova`) | Omnibus mean comparison across more than two groups, robust to unequal variances; reports η² |
| Kruskal–Wallis | | ✓ | | | | | `/results/omnibus` (`kruskal_wallis`) | Distribution-free omnibus across more than two groups; reports ε² |
| Log-rank test | | | | | | ✓ | `/results/survival` (`log_rank`) | k-sample time-to-event comparison (up to 10 arms) with per-arm Kaplan–Meier curves and Greenwood confidence bands |
| Fleming–Harrington weighted log-rank | | | | | | ✓ | `/results/survival` (`fleming_harrington`) | Weighted log-rank w(t) = S(t⁻)^ρ (1 − S(t⁻))^γ; the default (ρ=1, γ=0) emphasizes early differences |
| Cox proportional hazards | | | | | | ✓ | `/results/survival` (`cox`) | Two-arm treatment-effect hazard ratio with Wald confidence interval; HR < 1 means the treatment lowers the event hazard |

The paired and omnibus rows are within-subject and multi-group designs respectively (each with its own dedicated endpoint and `test_type`); the survival rows compare time-to-event data (a duration plus a censoring flag per subject) and return Kaplan–Meier curves alongside the test; the ratio row uses its own endpoint because the delta-method variance needs raw per-user numerator/denominator covariance rather than marginal summaries.

## Local setup

This is the downloadable local product (clone or image on your machine). It is the supported way to run and evaluate the demo.

Zero-config local runs use SQLite and need no secrets. Optional LLM provider tokens are pasted into the UI and remain browser-session-only rather than backend env.

### No Docker, single-port product (recommended)

Prerequisites:

- Python 3.13+ (CI and mypy use Python 3.14)
- Node 24 LTS with npm
- Git

On the first run, opt in to the dependency downloads and locked frontend build:

```bash
python scripts/run_local.py --bootstrap
```

The runner prints every external command before executing it, creates `.venv`,
installs `app/backend/requirements.txt`, runs `npm ci` plus the Vite production
build, and then serves the UI and API together on `http://127.0.0.1:8008`.
It does not copy `.env` or reuse inherited Postgres, remote-snapshot, or
shared-auth secrets.

Subsequent runs do not install or download anything:

```bash
python scripts/run_local.py
```

To populate the local SQLite workspace with the four demo projects:

```bash
python scripts/run_local.py --seed-demo
```

The following commands show the install, build, and manual backend-start steps
only. They do not reproduce the runner's isolated SQLite, single-port, and
inherited-secret-scrubbing environment. For the supported zero-secret local
path, run `python scripts/run_local.py`; add `--bootstrap` on first setup.

```bash
python -m venv .venv
# Activate .venv, then:
python -m pip install -r app/backend/requirements.txt
npm --prefix app/frontend ci
npm --prefix app/frontend run build
python -m uvicorn app.backend.app.main:app --host 127.0.0.1 --port 8008
```

To verify the local runner contract:

```bash
python -m pytest -p no:cacheprovider app/backend/tests/test_run_local_script.py -q
```

### Docker (optional)

If Docker is available, the existing container path remains:

```bash
export GIT_SHA="$(git rev-parse --verify 'HEAD^{commit}')"
```

```bash
docker compose up --build
```

To seed container demo data on startup, set `AB_SEED_DEMO_ON_STARTUP=true`.
For the supported local runner, prefer `python scripts/run_local.py --seed-demo`.

Environment template:

- start from [.env.example](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/.env.example)
- set `AB_API_TOKEN` if you want write-capable `/api/v1/*` routes protected
- optionally set `AB_READONLY_API_TOKEN` for read-only access: diagnostics, readiness, docs, `GET` project routes, and the stateless calculation endpoints
- optionally set `AB_PUBLIC_DEMO=true` to give anonymous visitors that same read-only scope (guest landing + calculators, no mutations) for a self-hosted demo
- optionally set `AB_WORKSPACE_SIGNING_KEY` to HMAC-sign exported workspace backups and require signed imports on that runtime
- rate limiting and auth-failure throttling are enabled by default; tune `AB_RATE_LIMIT_*` and `AB_AUTH_FAILURE_*` for stricter or looser local behavior
- request body guards are enabled by default; tune `AB_MAX_REQUEST_BODY_BYTES` and `AB_MAX_WORKSPACE_BODY_BYTES` if you expect unusually large workspace bundles
- when the backend is protected, paste the token into the frontend "API session token" field; it stays only in the current browser session and is not baked into the build

### Backend

```bash
cd app/backend
python -m pip install -r requirements.txt       # runtime only
# for tests/lint/typecheck: python -m pip install -r requirements-dev.txt
cd ../..                                 # back to repo root
python -m uvicorn app.backend.app.main:app --host 127.0.0.1 --port 8008
```

Health:

```text
http://127.0.0.1:8008/health
```

Diagnostics:

```text
http://127.0.0.1:8008/api/v1/diagnostics
```

Readiness:

```text
http://127.0.0.1:8008/readyz
```

### Frontend

```bash
cd app/frontend
npm ci
npm run dev
```

Vite default:

```text
http://127.0.0.1:5173
```

## Public API access

The runtime now supports two auth modes for external consumers:

- legacy shared tokens via `AB_API_TOKEN` and `AB_READONLY_API_TOKEN`
- managed database-backed API keys created with `AB_ADMIN_TOKEN`

FastAPI documentation pages stay public:

- Swagger UI: `http://127.0.0.1:8008/docs`
- Redoc: `http://127.0.0.1:8008/redoc`
- OpenAPI JSON: `http://127.0.0.1:8008/openapi.json`

Create a scoped key once `AB_ADMIN_TOKEN` is configured:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/keys \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Partner read key","scope":"read","rate_limit_requests":60,"rate_limit_window_seconds":60}'
```

Use the returned plaintext secret against protected routes:

```bash
curl http://127.0.0.1:8008/api/v1/projects \
  -H "X-API-Key: abk_your_plaintext_key"
```

Only the hash is stored in SQLite, and the plaintext key is shown once at creation time. Legacy shared tokens remain available for backward compatibility and should be documented to external consumers as legacy access.

Configure an outbound webhook for audit events:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/webhooks \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Slack alerts","target_url":"https://hooks.slack.com/services/XXX/YYY/ZZZ","secret":"rotate-me","format":"slack","event_filter":["api_key_created","api_key_revoked","analysis_run_created","workspace_imported","project.archive"],"scope":"global"}'
```

Fire a test delivery:

```bash
curl -X POST http://127.0.0.1:8008/api/v1/webhooks/WEBHOOK_ID/test \
  -H "Authorization: Bearer YOUR_AB_ADMIN_TOKEN"
```

Generic endpoints receive JSON plus `X-AB-Signature: sha256=...`; Slack subscriptions receive an incoming-webhook payload without signature validation.

For the two-way Slack App, create an app from `slack/app-manifest.yml`, set `AB_SLACK_CLIENT_ID`, `AB_SLACK_CLIENT_SECRET`, and `AB_SLACK_SIGNING_SECRET`, then open `/slack/install`. The app exposes `/ab-test projects`, `/ab-test status <project_id>`, and `/ab-test run <project_id>`.

## Languages

The **legacy** UI ships with seven locales: **English** (default), **Russian**, **German**, **Spanish**, **French**, **Simplified Chinese**, and **Arabic**. Pick a language from the header switcher (the choice persists to `localStorage` under `ab-test:language`) or set `?lang=fr` on the URL to override auto-detection. Arabic also switches the document into `dir="rtl"` so the shell, panels, toasts, and warning callouts follow the reading direction automatically. The experimental evidence Workbench is English-only.

The backend honors the `Accept-Language` header on export endpoints and localizes the markdown/HTML report headers plus warning and risk strings. Regional tags fall back to their primary language: `fr-CA` -> `fr`, `de-AT` -> `de`, `es-MX` -> `es`, `zh-CN` / `zh-TW` -> `zh`, `ar-SA` / `ar-EG` -> `ar`, and unsupported locales fall back to `en`.

```bash
curl -X POST http://127.0.0.1:8008/api/v1/export/markdown \
  -H "Accept-Language: de" \
  -H "Content-Type: application/json" \
  -d @docs/demo/sample-report.json
```

Unsupported locales fall back to English. For instructions on adding another locale, see [docs/RUNBOOK.md#adding-a-new-locale](/ab-test-research-designer/guides/runbook/).

## Docker

Build and run the full stack through the backend-served frontend:

```powershell
$env:GIT_SHA = (git rev-parse --verify 'HEAD^{commit}').Trim()
```

On macOS/Linux, use `export GIT_SHA="$(git rev-parse --verify 'HEAD^{commit}')"`
instead. Compose requires this exact commit to stamp `BUILD_INFO.json`.

```bash
docker compose up --build
```

Secure local container mode:

```bash
set AB_API_TOKEN=your-secret-token
docker compose up --build
```

Dual-token container mode:

```bash
set AB_API_TOKEN=write-secret-token
set AB_READONLY_API_TOKEN=readonly-secret-token
docker compose up --build
```

Signed-backup container mode:

```bash
set AB_WORKSPACE_SIGNING_KEY=replace-with-a-long-random-secret
docker compose up --build
```

Secure Docker verification:

```bash
cmd /c scripts\verify_all.cmd --with-docker
```

Non-destructive Docker verification:

```bash
python scripts/verify_docker_compose.py --preserve
```

Image publish, registry tagging, rollback, and runtime verification details: [docs/DEPLOY.md](/ab-test-research-designer/guides/deploy/)

Then open:

```text
http://127.0.0.1:8008
```

## Verification

Full local pipeline:

```bash
cmd /c scripts\verify_all.cmd
```

Useful variants:

- `cmd /c scripts\verify_all.cmd --skip-smoke`
- `cmd /c scripts\verify_all.cmd --skip-build`
- `cmd /c scripts\verify_all.cmd --with-e2e`
- `cmd /c scripts\verify_all.cmd --with-e2e --with-lighthouse`
- `cmd /c scripts\verify_all.cmd --with-docker`
- `cmd /c scripts\verify_all.cmd --with-docker-preserve`

The verify pipeline exercises both checksum-only and signed workspace backup roundtrips.
It also covers rate limiting, auth-throttle, request-size enforcement, and workspace checksum/signature regressions through backend tests.

Workspace backup roundtrip drill:

```bash
python scripts/verify_workspace_backup.py --fixture
```

Signed workspace backup roundtrip drill:

```bash
set AB_WORKSPACE_SIGNING_KEY=replace-with-a-long-random-secret
python scripts/verify_workspace_backup.py --fixture
```

Backend calculation benchmark:

```bash
python scripts/benchmark_backend.py --payload binary --assert-ms 100
```

The backend pytest suite also includes an in-repo p95 latency guard for binary and continuous calculations.

Browser E2E:

```bash
cd app/frontend
npm run test:e2e
```

This command builds the frontend if needed and runs Playwright against a temporary backend-served build on a free local port.

## Lighthouse

Build the frontend, start the backend-served dist on port `4174`, and run Lighthouse CI:

```bash
npm --prefix app/frontend run build
python scripts/run_lighthouse_ci.py
```

To include Lighthouse in the full local verification flow:

```bash
cmd /c scripts\verify_all.cmd --with-e2e --with-lighthouse
```

Current Lighthouse thresholds stay strict for accessibility and advisory for other categories:

- performance `>= 0.85` (`warn`)
- accessibility `>= 0.90` (`error`)
- best-practices `>= 0.90` (`warn`)
- seo `>= 0.80` (`warn`)

## Documentation

Use the [documentation map](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/README.md) to choose the right track.

- Trialmark: [target architecture](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/architecture/TRIALMARK_ARCHITECTURE.md),
  [ADRs](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/adr/), and the
  [ASOS tamper walkthrough](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main/docs/article/trialmark-asos-tamper-demo.md).
- Stable legacy product: [architecture](/ab-test-research-designer/guides/architecture/),
  [API](/ab-test-research-designer/guides/api/), [rules](/ab-test-research-designer/guides/rules/), and [runbook](/ab-test-research-designer/guides/runbook/).
- Delivery and history: [deployment](/ab-test-research-designer/guides/deploy/),
  [production operations](/ab-test-research-designer/guides/production/),
  [release checklist](/ab-test-research-designer/guides/release_checklist/),
  [history](/ab-test-research-designer/guides/history/), and [changelog](/ab-test-research-designer/guides/changelog/).

## Notes

- frontend API contracts are generated from FastAPI OpenAPI into `app/frontend/src/lib/generated/api-contract.ts`
- TypeScript strict mode is enabled
- pytest cache artifacts are disabled via `pytest.ini`
- the smoke script updates `docs/demo/` screenshots from a real browser flow
- the smoke flow now verifies the sample import payload before refreshing screenshots
- the Playwright E2E command builds the frontend if needed, starts a temporary backend-served frontend on a free local port, and cleans it up through `scripts/run_frontend_e2e.py`
- LLM adapter timeout/retry behavior can be tuned through `.env.example`
- SQLite busy timeout, journal mode, synchronous mode, and backend log format are configurable through `.env.example`
- optional write-token auth is available through `AB_API_TOKEN`; the frontend can send it as a browser-session token without baking it into the build
- optional read-only auth is available through `AB_READONLY_API_TOKEN` for read-only runtime access (`GET/HEAD/OPTIONS` plus stateless calculation POSTs)
- API responses now include `X-Request-ID` and `X-Process-Time-Ms` headers for lightweight local observability
- responses now also include baseline security headers (`Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`)
- `/api/v1/*` requests now have configurable in-memory rate limiting plus a dedicated auth-failure throttle with `Retry-After` on `429`
- mutating API routes now enforce configurable request-body limits, with a larger dedicated ceiling for workspace import/validate flows
- error responses now also include `error_code`, `status_code`, `request_id`, and `X-Error-Code`
- `GET /readyz` gives a simple readiness view over storage, frontend-dist serving, and runtime config
- `GET /api/v1/diagnostics` now also exposes in-memory runtime counters plus the active guardrail configuration for security headers, rate limiting, auth throttling, and request-body limits
- workspace backup/import now works from the UI and through `GET /api/v1/workspace/export` plus `POST /api/v1/workspace/import`
- workspace backup bundles now include integrity counts and a SHA-256 checksum; when `AB_WORKSPACE_SIGNING_KEY` is configured they also carry an HMAC signature and imports require signature verification on that runtime
- saved projects now retain revision history and can restore older payload snapshots from the UI
