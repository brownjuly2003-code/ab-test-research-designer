# CX Task: Hypothesis property tests — расширить edge cases

## Goal
Расширить существующий `hypothesis==6.152.1` property-test suite (37 invariants из `6d2c7d3f`) дополнительными edge cases вокруг численной стабильности, degenerate inputs и robustness под extreme parameters. Цель — выявить скрытые `AssertionError` / `ZeroDivisionError` / `OverflowError` которые deterministic тесты не ловят.

## Context
- **Repo.** `D:\AB_TEST\`, `main`, HEAD `906ec9ce` (или новее).
- **Existing property tests.** `app/backend/tests/test_property_*.py` (если единый файл) или разбросано — найти через `grep -l "hypothesis" app/backend/tests/`. 37 инвариантов по binary / continuous / SRM / sequential / bayesian.
- **Services под тестом:**
  - `app/backend/app/services/calculations_service.py` — frequentist / Bayesian / SRM.
  - `app/backend/app/services/comparison_service.py` — multi-project compare.
  - `app/backend/app/services/monte_carlo_service.py` — MC bootstrap (новый, из `68c355bf`).
- **Invariants уже покрытые (baseline):** p-value ∈ [0,1], power ∈ [0,1], confidence interval contains point estimate, sample size монотонно растёт с MDE↓ / power↑, srm p-value симметричный относительно swap variants, posterior mean между prior и observed для Bayesian.

## Deliverables

1. **Numerical edge cases.**
   - `sample_size = 1` (degenerate): должен raise ValidationError с понятным msg, не NaN в output.
   - `mde = 0` / `mde = 1`: first — valid "no effect to detect" (power = alpha), second — extreme (sample size stays sane или raises).
   - `alpha = 0.0001` (ultra-strict): sample sizes растут, не overflow.
   - `alpha = 0.5` (no test at all): power = 1 - beta if mde != 0.
   - `power = 0.5` (coin flip): sample size sane.
   - `baseline_conversion ∈ {0, 1}` (degenerate proportions): raise ValidationError.
   - `baseline_conversion ∈ (0, 1e-6)` и `(1-1e-6, 1)`: numerical stability, не loses precision.
   - `std ≈ 0` для continuous: raise ValidationError (zero-variance).
   - `std = sys.float_info.max / 2` (extreme): не overflow.

2. **Bayesian edge cases.**
   - Prior std → 0 (point prior): posterior should collapse to prior ± epsilon.
   - Prior std → ∞ (uninformative): posterior ≈ observed.
   - Observed stats = prior stats exactly: posterior close to either.
   - Credibility interval width ≥ posterior std * quantile factor (sanity).

3. **SRM edge cases.**
   - Perfect balance (0.5 / 0.5 assignment) → p-value близок к 1.
   - Extreme imbalance (0.99 / 0.01) с большим n → p-value ≈ 0.
   - n = 0 в одной группе → specific error, не NaN.

4. **Sequential testing edge cases.**
   - 1 look (trivial sequential) → результат ≈ fixed design.
   - 100 looks (extreme) → boundaries не degenerate.
   - information_fraction = [0, 0.5, 1] vs [0.01, 0.5, 0.99] — boundaries monotone.

5. **Monte-Carlo edge cases (новое от `68c355bf`).**
   - `num_simulations = 1000` (minimum cap): distribution shape sane.
   - `num_simulations = 50000` (max cap): не timeout, percentiles stable.
   - `observed_conversion = baseline`: `probability_uplift_positive` ∈ [0.45, 0.55].
   - `sample_size_a ≪ sample_size_b` (e.g. 10 vs 10000): MC handles без крэша.
   - Seed=42 two runs: bit-exact match (уже есть, но extend на more inputs).

6. **Structure.**
   - Добавить в существующий test-module или создать `test_property_edge_cases.py`.
   - Prefer `@hypothesis.given(st.floats(...))` с явными `min_value` / `max_value` / `allow_nan=False` / `allow_infinity=False`.
   - Use `assume(...)` для degenerate input filtering.
   - `@hypothesis.settings(max_examples=100)` на тяжёлых тестах, `50` на очень тяжёлых.

7. **Если тест находит баг.**
   - Записать minimal-reproducing example в отдельный deterministic test (`test_regression_<descriptive_name>.py`).
   - Fix'ить root cause в service (validation / numerical stability guard).
   - В commit message ссылка на issue или reproducing case.

8. **Коммит:**
   - Один коммит если всё clean: `test(hypothesis): edge-case property tests for numerical stability and Monte-Carlo cap`.
   - Два если найден bug: выше + `fix(<service>): handle degenerate <X> input` (первым).

9. **Report `docs/plans/2026-04-23-hypothesis-edge-cases-report.md`:**
   - Number of new properties added per category.
   - Any bugs uncovered + their fixes.
   - Total Hypothesis runtime.

## Acceptance
- `python -m pytest -p no:schemathesis app/backend/tests/ -k "property" -v` зелёный.
- `scripts\verify_all.cmd --with-e2e` = 0.
- Bug'и (если найдены) fix'нуты и покрыты regression test'ом.
- CI `Tests` зелёный на main.

## Notes
- **НЕ** ослаблять existing invariants — новые добавлять additive.
- **Runtime budget.** Hypothesis max_examples=100 x N tests не должен превысить 60 секунд суммарно для этого suite — иначе CI будет раздуваться.
- **Shrinking.** Если Hypothesis падает на сложном input — воспроизводить в deterministic test, не полагаться только на shrink.
- **НЕ** mock'ать numpy / scipy — тестируем реальные вычисления.

## Out of scope
- Mutation testing.
- Fuzzing внешнего API через Schemathesis (отдельно).
- Performance benchmarks (benchmark_backend.py отдельный).
- Integration tests (unit / property only).
