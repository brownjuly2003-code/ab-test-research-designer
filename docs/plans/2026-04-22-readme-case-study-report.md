# README case study report

## Script output

```markdown
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

Full inputs and outputs: [docs/case-studies/checkout-redesign.json](docs/case-studies/checkout-redesign.json). Rerun with `python scripts/generate_case_study_numbers.py`.
```

## Files changed or created

- `scripts/generate_case_study_numbers.py`
- `docs/case-studies/checkout-redesign.json`
- `docs/case-studies/README.md`
- `README.md`
- `CHANGELOG.md`
- `docs/plans/2026-04-22-readme-case-study-report.md`

## Verification

- `python scripts/generate_case_study_numbers.py` -> `0`
- `python -m pytest app/backend/tests/test_bayesian.py app/backend/tests/test_results_service.py -q` -> `10 passed`
- `python -m json.tool < docs/case-studies/checkout-redesign.json` -> `0`
- `cmd /c scripts\verify_all.cmd --with-e2e` -> `0`

## Known limitations

- Bayesian posterior uses an explicit `Beta(1,1)` uniform prior and records the posterior parameters in `docs/case-studies/checkout-redesign.json`.
- The requested interim snapshot is `16,000` users per arm, which is `35.2%` of the planned per-variant sample under the current sizing output, so the README text describes it as an early interim snapshot instead of claiming a literal 50% read.
- The repository was already dirty before this task started, so `git status --short` cannot be empty after staging only the files that belong to this case-study task.
