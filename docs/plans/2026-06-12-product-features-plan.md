# План: продуктовые фичи §5.4 (quick wins без execution-слоя)

**Дата:** 2026-06-12
**Источник:** `res_07_06_26.md` §5.4 — дёшево добираемые дифференциаторы для planning-ниши.
**Scope:** три расчётно-планировочные фичи на существующей инфраструктуре. **Не входит** execution-слой (реальное проведение экспериментов) — `res_07_06_26.md` §5.3 явно помечает его как «сюда НЕ идти» (переход MVP→production на недели).

Все три фичи пристраиваются к уже существующим подсистемам без новой инфраструктуры:
- **LLM-модуль** `app/backend/app/llm/` — `LocalOrchestratorAdapter` / `OpenAIAdapter` / `AnthropicAdapter`, общий интерфейс `request_advice(payload)`, выбор провайдера через `pick_adapter()` (заголовки `X-AB-LLM-Provider` / `X-AB-LLM-Token`), `prompt_builder.py` + `parser.py` + graceful `_fallback`.
- **Monte-Carlo** `app/backend/app/services/monte_carlo_service.py` — `simulate_uplift_distribution(...)`, `simulate_comparison(...)` на numpy.
- **Design/расчёт** `app/backend/app/services/{design_service,calculations_service}.py` — `build_experiment_report(...)`, sample sizing в `calculation_result["results"]`.

Каждая фича следует устоявшемуся вертикальному срезу проекта: `schemas/api.py` (Pydantic in/out) → `services/*` или `stats/*` → `routes/analysis.py` (эндпоинт + auth) → перегенерация контракта (`scripts/generate_frontend_api_types.py`) и доков (`scripts/generate_api_docs.py`) → frontend (`lib/` клиент + компонент + `public/locales/*` ×7) → тесты (unit + property + route + vitest) → `verify_all.py`.

---

## Фича 1 — AI hypothesis generation

**Зачем:** закрывает нишевый разрыв с Opal/Copilot — ideation ДО того, как у пользователя есть гипотеза. Сейчас LLM вызывается только для advice по уже введённому эксперименту (`_build_llm_advice_payload` в `routes/analysis.py:57`).

**Суть:** по введённым `domain` / `product_type` / `baseline` / `traffic` / краткому описанию проблемы LLM генерирует 3–5 кандидатов-гипотез (изменение → ожидаемый эффект → метрика → краткое обоснование), которые пользователь может выбрать и догрузить в визард.

**Изменения:**
- `schemas/api.py`: `HypothesisIdeationRequest` (context-поля, переиспользуют существующие из `ExperimentInput`) + `HypothesisIdeationResponse` (`list[HypothesisCandidate]`, поля `change`, `rationale`, `primary_metric`, `expected_direction`).
- `llm/prompt_builder.py`: новая функция сборки ideation-промпта (отдельно от advice-промпта).
- `llm/parser.py`: парсер ответа в `list[HypothesisCandidate]` с тем же `_fallback`-паттерном (пустой список + error_code при сбое/невалидном JSON).
- `routes/analysis.py`: `POST /api/v1/hypotheses/generate`, `require_write_auth`, через `pick_adapter()` (тот же multi-provider контракт).
- frontend: кнопка «Сгенерировать гипотезы» на шаге гипотезы визарда, список кандидатов, «применить» → заполняет поля; `public/locales/*` ×7.
- тесты: parser unit (валид/мусор/fallback), route с замоканным адаптером (детерминизм — без реального LLM), vitest на компонент.

**Объём:** дни (1 разработчик). **Риск:** низкий — инфраструктура адаптеров и fallback уже есть; главное держать детерминизм тестов (мок-адаптер, не реальный провайдер).

**Открытый вопрос (за пользователем):** дефолтный провайдер для ideation — local orchestrator или требовать пользовательский токен (как у advice). Рекомендация: тот же `pick_adapter()`-контракт, без нового дефолта.

---

## Фича 2 — Holdout / mutual-exclusion в планировщике

**Зачем:** holdout (глобальная контрольная доля, не участвующая в тесте) и взаимоисключающие эксперименты — table-stakes для зрелого planning-инструмента. Чисто расчётная опция, без runtime-аллокации.

**Суть:** пользователь задаёт `holdout_fraction` (доля аудитории вне теста) и/или количество взаимоисключающих экспериментов; расчёт корректирует **эффективный трафик** на тест и, соответственно, `estimated_duration_days`. Mutual-exclusion делит доступный трафик между N экспериментами.

**Изменения:**
- `schemas/api.py`: опциональные поля в `CalculationRequest` — `holdout_fraction: float | None` (validator `0 <= x < 1`), `mutually_exclusive_experiments: int | None` (`>= 1`).
- `services/calculations_service.py` / `stats/*`: при расчёте `effective_daily_traffic` умножать на `(1 - holdout_fraction)` и делить на число mutually-exclusive экспериментов; `estimated_duration_days` пересчитывается из скорректированного трафика. Отразить в `CalculationResponse` (новые поля `effective_traffic_after_holdout`, опционально предупреждение, если holdout раздувает длительность сверх порога).
- `design_service.build_experiment_report`: показать holdout/ME в design-секции отчёта.
- frontend: поля в визарде + отображение скорректированной длительности; `public/locales/*` ×7.
- тесты: property (holdout=0 ≡ текущее поведение; рост holdout монотонно увеличивает длительность), route, vitest.

**Объём:** 1–2 дня. **Риск:** низкий — изолированная корректировка трафика; ключевой инвариант для регрессии — `holdout_fraction=None|0` даёт ровно текущие числа (backward-compat).

---

## Фича 3 — Bandits-калькулятор (Thompson sampling)

**Зачем:** дифференциатор для planning-ниши — сравнить классический фиксированный дизайн с multi-armed bandit по ожидаемому regret / скорости сходимости. Средняя сложность.

**Суть:** симуляция Thompson sampling поверх существующего Monte-Carlo. На вход — baseline-rate'ы вариантов (или baseline + предполагаемые uplift'ы) и горизонт; на выход — ожидаемая аллокация трафика по вариантам во времени, cumulative regret vs равномерный сплит, вероятность выбора лучшего варианта. Это **планировочная симуляция «что если бандит»**, не runtime-аллокатор.

**Изменения:**
- `stats/` или `services/monte_carlo_service.py`: `simulate_thompson_sampling(arm_rates, horizon, num_simulations)` — Beta-Bernoulli обновление на numpy, рядом с `simulate_uplift_distribution`. **Важно:** RNG детерминируется явным seed из payload (паттерн Monte-Carlo сервиса), иначе property/regression-тесты будут флакать.
- `schemas/api.py`: `BanditSimulationRequest` (`arm_rates: list[float]`, `horizon: int`, опц. `seed`) + `BanditSimulationResponse` (per-arm аллокация, regret-кривая, P(best)).
- `routes/analysis.py`: `POST /api/v1/simulate/bandit`, `require_write_auth`.
- frontend: новый блок «Bandit vs fixed» с графиком аллокации/regret (Plotly уже в стеке — см. charts-skill); `public/locales/*` ×7.
- тесты: property (один доминирующий arm → его аллокация → 1 при росте горизонта; regret монотонно неубывающий; seed → воспроизводимость), route, vitest.

**Объём:** средний (несколько дней). **Риск:** средний — численная корректность бандита и детерминизм симуляции; митигируется known-reference тестами (как `test_chi_square_srm_matches_known_reference`) и фиксированным seed.

---

## Рекомендуемая последовательность

1. **Holdout/ME** — самая дешёвая, изолированная, чистый backward-compat инвариант. Хороший разогрев вертикального среза.
2. **AI hypothesis generation** — инфраструктура адаптеров готова, основная работа в prompt/parser + UI; высокая видимая ценность.
3. **Bandits** — самая ёмкая по математике и тестам; делать последней, опираясь на отлаженный Monte-Carlo.

Каждую фичу — отдельной веткой/PR с зелёным `verify_all.py` и обновлёнными контрактом/доками/локалями (×7), как в fable-батче.

## Явные не-цели
- Execution-слой (рандомизация в проде, сбор событий, runtime-аллокация бандита) — §5.3, отдельное продуктовое решение на недели.
- Новые внешние зависимости/инфраструктура — все три фичи на текущем стеке (numpy, существующие LLM-адаптеры, Pydantic, Plotly).
