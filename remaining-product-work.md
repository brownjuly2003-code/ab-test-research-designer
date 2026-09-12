# Remaining product work

## Goal

Complete D-02 and D-04 from real pilot evidence, then execute E/F/G only if the documented reuse gate opens.

## Tasks

- [x] Generalize `trialmark run` from the ASOS-only loader to a strict one-row binary aggregate CSV profile. → Verified by `test_binary_aggregate_pipeline.py`: a real-shaped pilot CSV publishes a valid, fully lineaged `.tmk`; row-level or malformed inputs are rejected.
- [x] Define a privacy-safe pilot record contract and validator for `docs/pilots/<date>-<anon>.md`. → Verified by `test_pilot_records.py`: malformed timestamps, missing denominators, raw identifiers, and unsupported outcomes fail.
- [x] Add a pilot-session command that creates and validates anonymized records without copying source rows. → Verified by `test_pilot_records.py`: a temporary record round-trips and the command rejects a bundle outside the declared privacy/lineage contract.
- [ ] Add deterministic Gate 3 aggregation over validated pilot records. → Verify: zero, incomplete, passing, and no-reuse cohorts produce the expected denominators and verdicts.
- [ ] Run three 30-minute sessions with external practitioners and record real `source_ready_at`, `bundle_ready_at`, bundle census, and second-run events. → Verify: three independently attributable anonymized records validate; simulated/public fixtures do not count.
- [ ] Generate `docs/gates/gate3_<date>.md` from the real cohort and commit D-02/D-04 evidence. → Verify: every threshold has a numerator/denominator and the verdict follows the recorded data.
- [ ] If and only if at least two practitioners return for a second run, implement E (versioned DSSE trust policy), F (durable worker/ops), and G (format/conformance interoperability) as separate red-green slices. → Verify: each phase meets its architecture acceptance tests and the prior phase remains green.
- [ ] Run final scoped and project gates; run container acceptance on the Mac only. → Verify: Ruff, strict mypy, relevant backend/frontend suites, artifact checks, and attached Mac command ending in `DONE` pass.

## Done When

- [ ] D-02/D-04 contain real, privacy-auditable evidence and a reproducible Gate 3 verdict; conditional E/F/G are either verified or explicitly closed by the measured stop criterion.

## Notes

No synthetic run, ASOS benchmark, or local repeat may be represented as external adoption. Publishing, recruiting, push, and other external actions retain their explicit target-specific gates.

Next code slice: add the deterministic Gate 3 aggregator and generator with red-green coverage for zero, incomplete, passing, no-reuse, duplicate, and non-pilot cohorts. No unfinished Gate 3 code is retained in the worktree.
