# CX Task: Property-based tests для statистических движков (hypothesis)

## Goal
Добавить property-based тесты в `D:\AB_TEST\app\backend\tests\` для `stats/binary.py`, `stats/continuous.py`, `stats/srm.py`, `stats/sequential.py`, `stats/bayesian.py`. Использовать `hypothesis` библиотеку для генерации валидных inputs, проверять математические инварианты и границы. Закрыть edge-case-пробелы, которые example-based тесты не поймут.

## Context
- Репо: `D:\AB_TEST\`, `main`, HEAD после `4099f73c`. Не ветка, не push.
- Verify зелёный: 177 backend tests, 197 frontend.
- `.hypothesis/unicode_data/` в репо уже есть — кэш hypothesis; значит `hypothesis` пакет запускался раньше, но в `requirements.txt` его нет — добавить.
- Существующие тесты:
  - `test_calculations.py`, `test_stats_edge_cases.py` — example-based.
  - `test_bayesian.py`, `test_sequential.py`, `test_srm.py` — example-based.
- Целевые инварианты, которые property-тесты должны ловить:
  - **Monotonicity:** увеличение MDE → уменьшение sample size. Увеличение alpha → уменьшение sample size. Увеличение power → увеличение sample size.
  - **Symmetry:** for `analyze_results`, swap control↔treatment → effect меняет знак, p-value тот же.
  - **Boundedness:** sample_size > 0; p-value ∈ [0, 1]; posterior std ≥ 0.
  - **Round-trip:** вычислить sample_size для данных MDE, затем backcalculate детектируемое MDE — должно совпасть до tolerance.
  - **No NaN / Inf:** для любых валидных inputs — результаты finite.
  - **Dimensionality:** для multi-variant (≥ 2), sample_size_per_variant одинаков при equal split; monotonно растёт с bonferroni correction.

## Deliverables
1. **Dependency:**
   - `app/backend/requirements.txt` — добавить `hypothesis==6.x.x` (latest stable).
   - `pytest.ini` — если нужно, указать `filterwarnings` для deprecation-warnings из hypothesis.

2. **Property tests:**
   - `app/backend/tests/test_binary_properties.py`:
     - `@given(baseline=floats(0.01, 0.99), mde_pct=floats(0.5, 50), alpha=floats(0.001, 0.2), power=floats(0.5, 0.99))` — sample_size > 0, finite, monotonous в MDE.
     - Observed effect symmetry swap.
     - Bonferroni: N-variants → sample_size увеличен относительно 2-variant.
   - `app/backend/tests/test_continuous_properties.py`:
     - Analog для continuous.
   - `app/backend/tests/test_srm_properties.py`:
     - Equal observed = expected → chi_square ≈ 0, p > 0.95, not SRM.
     - Random perturbation within tolerance → not SRM.
     - Sum of observed_counts preserves sample_size.
   - `app/backend/tests/test_sequential_properties.py`:
     - Alpha spending monotonously ≤ alpha across looks.
     - Sequential adjusted_sample_size ≥ fixed-horizon sample_size для того же MDE/power.
     - Boundaries симметричны around 0 для two-sided.
   - `app/backend/tests/test_bayesian_properties.py`:
     - Posterior mean ∈ (prior_mean - 3σ, prior_mean + 3σ) для слабого prior.
     - Credibility interval covers posterior_mean.
     - Bayesian sample_size > 0, finite.

3. **Shrinking-friendly strategies:**
   - Использовать `hypothesis.strategies` (`floats`, `integers`, `lists`, `composite`) с разумными bounds.
   - Для `floats` — `allow_nan=False, allow_infinity=False, min_value=..., max_value=...`.
   - Для multi-variant — `lists(integers(1, 8), min_size=2, max_size=8)` с дополнительной проверкой sum > 0.
   - `@settings(max_examples=50, deadline=5000)` — баланс покрытия и CI-времени.

4. **Example database commitment:**
   - `.hypothesis/` — уже в `.gitignore` (проверь); если нет — добавить.
   - Если есть shared examples (hypothesis их пишет) — остаются локально.

5. **CI compat:**
   - Убедиться что новые property-тесты проходят в <30 сек total.
   - Backend suite должен оставаться < 90 сек.

6. **Один коммит:**
   ```
   test: property-based invariants for stats engines via hypothesis
   ```

7. **Отчёт `docs/plans/2026-04-22-property-tests-report.md`:**
   - Список проверенных инвариантов per-file.
   - Любые баги/edge cases, которые нашлись (если нашлись — fix в той же PR, report отмечает).
   - Итоговый runtime prop-suite.

## Acceptance
- `scripts\verify_all.cmd` = exit 0.
- `python -m pytest app/backend/tests -q` = все green; +30–80 новых property тестов (каждый case считается за один test, но hypothesis crunches много внутренних examples).
- Backend suite total runtime < 90 сек.
- `app/backend/requirements.txt` содержит `hypothesis==...`.
- `.gitignore` покрывает `.hypothesis/` (должен уже).
- Commit subject уникальный, `Co-Authored-By: Codex <noreply@anthropic.com>`.
- Этот CX-файл стадж в свой коммит.
- `git status --short` = пусто.

## How
1. Baseline: `git status --short` = пусто, verify = 0.
2. `pip install hypothesis` в том же venv что используется для тестов; добавить в requirements.
3. Написать property-тесты по одному файлу на стат-модуль. Старт с binary (наиболее проверенный).
4. Если какой-то инвариант падает — это настоящий баг. Разобраться в коде, исправить (в той же PR), зафиксировать в отчёте.
5. Если hypothesis находит flaky example — `@example` pin'нуть reproduction.
6. Настроить `@settings(max_examples=50, deadline=5000)` на каждом тесте для предсказуемого CI времени.
7. Commit + verify + report.

## Notes
- **CX-файл hygiene:** staging этого файла.
- **Commit subject hygiene:** проверка на дубль.
- **НЕ** использовать `hypothesis.strategies.from_type(Pydantic_Model)` — pydantic модели уже покрыты example тестами; цель — математические инварианты, не parsing.
- **НЕ** замедлять suite выше 90 сек. Если тест > 3 сек на один — уменьшить `max_examples`.
- **Edge cases для shrinking:** hypothesis автоматически shrinks failing examples; при падении смотреть reproduction и проверять ли это реально баг. Часто это бага в тесте (невалидный assumption), не в коде.
- **Float comparison:** использовать `math.isclose(a, b, rel_tol=1e-6)` для real-valued инвариантов; не `a == b`.
- **БЕЗ новых deps кроме hypothesis.**
- Backend `test_performance` может флапнуть — перезапустить один раз.
- **НЕ** пушить на remote.

## Out of scope
- Fuzzing API endpoints (schemathesis / atheris) — отдельный таск если понадобится
- Mutation testing (mutmut / cosmic-ray)
- Frontend property tests
- Statistical simulation verification via Monte Carlo
