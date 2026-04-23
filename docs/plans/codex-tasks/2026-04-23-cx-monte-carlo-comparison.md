# CX Task: Monte-Carlo и permutation overlays в comparison dashboard

## Goal
Comparison dashboard (сравнение 2-5 saved projects) сейчас показывает deterministic metrics: point estimates, observed uplift, simple power curves. Добавить опциональный Monte-Carlo / permutation layer, дающий distribution-based risk view: "в 10k symulations — variant B даёт uplift > 3% в 62% симуляций, variant A — только в 34%". Нужно для честного сравнения scenarios, где aggregate numbers маскируют tail risk. Tier 3 roadmap #1.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `f4178dd3`.
- **Текущий backend.**
  - `app/backend/app/services/comparison_service.py` — `_build_sensitivity`, `_saved_observed_results`, основной endpoint `POST /api/v1/projects/compare`.
  - `app/backend/app/services/calculations_service.py` — frequentist / Bayesian / SRM.
  - `hypothesis==6.152.1` уже в requirements — **не использовать** его для MC (Hypothesis это property-testing для тестов, не numerical MC). Numpy уже присутствует через matplotlib.
- **Текущий frontend.**
  - `app/frontend/src/components/ComparisonDashboard.tsx` — главный UI.
  - Power curve + forest plot уже есть. Новый layer — overlay, не замена.
- **Дизайн.**
  - Overlay — toggle'able секция "Distribution view" с disclosure pattern (не сразу раскрытый — expensive compute).
  - При нажатии на toggle — запрос на backend с `num_simulations=10000` (cap'нут). Loading state ~1-3s.
  - Результат: histogram simulated uplift-distribution + "probability of uplift > threshold X" slider.
- **НЕ трогать** point-estimate flow, smoke, i18n keys без нужды, CI workflow, snapshot / HF / mkdocs.

## Deliverables

### Backend

1. **Новый service `app/backend/app/services/monte_carlo_service.py`:**
   - `def simulate_uplift_distribution(baseline_conversion: float, observed_conversion_a: float, sample_size_a: int, observed_conversion_b: float, sample_size_b: int, num_simulations: int = 10000, seed: int | None = 42) -> dict`:
     - Parametric bootstrap: каждую симуляцию — sample Beta posterior для baseline, treatment A, treatment B (Beta(alpha=n_conversions+1, beta=n-n_conversions+1)).
     - Возвращает:
       ```python
       {
         "num_simulations": 10000,
         "percentiles": {"5": -0.001, "25": 0.012, "50": 0.023, "75": 0.035, "95": 0.049},
         "probability_uplift_positive": 0.87,  # treatment > baseline in X% of sims
         "probability_uplift_above_threshold": {"0.01": 0.78, "0.03": 0.45, "0.05": 0.12},
         "simulated_uplifts": [...]  # raw array, length 10k
       }
       ```
     - Seed по default 42 — detrministic для тестов. `None` → stochastic (prod).
   - `def simulate_comparison(projects: list[dict], num_simulations: int = 10000) -> dict`:
     - Для каждого project из `compare` endpoint'а запускает `simulate_uplift_distribution`.
     - Возвращает mapping `project_id → simulation_result`.
   - **Продолжение metric_type:** binary = Beta-Bernoulli (выше), continuous = Normal bootstrap (`np.random.normal(mean, std, size=n)`). Не поддерживать count / ratio в этой первой версии.

2. **Endpoint extension:** `app/backend/app/routes/comparison.py` (или где живёт `/projects/compare`). Добавить query param `?include_monte_carlo=true&monte_carlo_simulations=10000`. Cap `monte_carlo_simulations` в [1000, 50000] (защита от кvадратичного computation).
   - Если `include_monte_carlo=false` (default) — существующий path, ничего не считается MC.
   - Если `true` — добавить поле `monte_carlo_distribution` в response, сериализовать `simulate_comparison`.

3. **Backend тесты.** `test_monte_carlo_service.py`:
   - Deterministic seed: 2 прогона с `seed=42` возвращают identical percentiles.
   - Stochastic: `seed=None` → 2 прогона разные.
   - Edge case: observed_conversion == baseline → `probability_uplift_positive ≈ 0.5`.
   - Edge case: очень маленький sample_size (n=10) → sanity-check, percentiles широкие.
   - Performance: `num_simulations=10000` на binary с 3 variants — должно бежать < 500ms (sanity-check на вашем железе, не CI).

### Frontend

4. **Компонент `DistributionView.tsx`** под `app/frontend/src/components/ComparisonDashboard/`:
   - Toggle "Show distribution view" — disclosure, default collapsed.
   - При первом открытии — запрос с `include_monte_carlo=true`. Cache в local component state, не запрашивать повторно при re-collapse.
   - Histogram: 50 buckets, расчёт на клиенте из `simulated_uplifts` массива. Рендерить через existing recharts setup (см. forest-plot / power-curve).
   - Interactive slider "Probability uplift > X%" с live пересчётом из `probability_uplift_above_threshold` (для discrete значений 0.01, 0.02, ..., 0.10 — server pre-computes; между — client interpolates).
   - Legend под histogram-ом: percentile markers (P5, P25, P50, P75, P95).

5. **UX текст.** В i18n добавить ключи `app.comparison.monteCarlo.*` (title, toggle label, slider label, percentile legend). Перевести en / ru / de / es.

6. **Frontend тесты.**
   - RTL тест: toggle collapsed → открыть → делает fetch с `include_monte_carlo=true`.
   - RTL тест: slider меняет вычисленную probability из массива.
   - Axe a11y тест (следовать a11y-comparison-dashboard паттерну — но НЕ отключать `color-contrast` как quick fix, если будут timeout issues, вынести в CX a11y perf follow-up).

### Documentation

7. **`docs-site/features/comparison.md`** — добавить подсекцию "Distribution view" с:
   - Что это за метод (1-2 параграфа plain language).
   - Screenshot после ручного smoke.
   - Cost note: "compute latency ~200ms per project for 10k simulations".

## Acceptance
- `python -m pytest app/backend/tests/test_monte_carlo_service.py -v` → зелёный.
- `scripts/verify_all.py --with-e2e --skip-build` → exit 0.
- Manual smoke: запустить backend + frontend с 3 saved projects в workspace → открыть compare dashboard → toggle "distribution view" → histogram рисуется < 2s, percentile markers видны, slider меняет показатель без лага.
- `POST /api/v1/projects/compare?include_monte_carlo=true&monte_carlo_simulations=10000` body=JSON с 3 projects → response содержит `monte_carlo_distribution`, каждый project с 10000-элементным `simulated_uplifts` array.
- Default без flag: `POST /api/v1/projects/compare` → response **не содержит** `monte_carlo_distribution` (backward compat).
- Один или два коммита:
  - `feat(stats): Monte-Carlo uplift distribution service`
  - `feat(comparison): distribution view overlay with interactive probability slider`

## Notes
- **Не встраивать MC в default flow.** Это opt-in через query flag. Default users (HF demo) не должны ждать 2 секунды на каждый compare-request.
- **Array of 10k floats per project — это ~80KB JSON per project.** Для 5 projects это 400KB. Allowed (уже делаем большие export'ы), но не бесконечно. Если в будущем хотим 50k simulations — тогда pre-compute histogram buckets на сервере и не отдавать raw array.
- **Determinism важен для тестов.** Обязательно seed=42 default, и в тестах проверять bit-for-bit identity двух прогонов.
- **Не смешивать с Bayesian posterior от `calculations_service.py`** — это разные flow. MC здесь — параметрический bootstrap, Bayesian — conjugate posterior. Названия в API и UI должны чётко разделять.
- **Rate limit / DoS.** `monte_carlo_simulations` cap 50000 — защита от юзера, который попытается DoS-нуть маршрут с `simulations=100M`. Не добавлять rate limit — достаточно cap и timeout из существующей FastAPI конфигурации.
- Отчёт (15-20 строк): latency p95 на стандартном demo workspace, screenshots histogram'а (или описание), tests run duration.
