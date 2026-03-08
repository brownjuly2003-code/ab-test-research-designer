# Implementation Spec

## 1. Goal
Построить локальный веб-сервис, который помогает пользователю спроектировать A/B тест и получить:
- математически рассчитанные параметры эксперимента,
- структурированный экспериментальный дизайн,
- список рисков,
- контекстные рекомендации от LLM.

## 2. MVP scope

### In scope
- Многошаговая форма ввода
- Валидация пользовательских данных
- Расчет sample size и estimated duration
- Поддержка бинарных и непрерывных метрик
- Rules engine для warning'ов
- Генерация experiment design report
- Интеграция с локальным оркестратором для LLM-советов
- Локальное сохранение проектов
- Экспорт в Markdown и HTML

### Out of scope
- Интеграции с продуктовой аналитикой
- Реальный запуск тестов
- Импорт live-данных
- Автоматическое SRM по фактическим логам
- Bayesian engine
- Sequential testing engine
- Multi-user collaboration

## 3. Core modules

### 3.1 Frontend app
Отвечает за:
- form wizard
- inline validation
- results page
- export actions
- saved projects list

### 3.2 Backend API
Отвечает за:
- прием запросов
- orchestration
- storage
- расчетные и LLM endpoints

### 3.3 Statistical engine
Отвечает за:
- binary metrics calculations
- continuous metrics calculations
- duration estimation
- practical feasibility checks

### 3.4 Rules engine
Отвечает за warning'и и эвристики.

### 3.5 Design composer
Собирает итоговый structured report из:
- user input
- calculations
- warnings
- LLM advice

### 3.6 LLM adapter
Инкапсулирует вызов локального оркестратора в `D:\Perplexity_Orchestrator2`.

### 3.7 Storage
Локальное хранение экспериментов и результатов.

## 4. Functional requirements

### FR-1. Project form
Пользователь может заполнить поля:
- project_name
- domain
- product_type
- platform
- market
- project_description

### FR-2. Hypothesis form
Поля:
- change_description
- target_audience
- business_problem
- hypothesis_statement
- what_to_validate
- desired_result

### FR-3. Experiment setup form
Поля:
- experiment_type
- randomization_unit
- traffic_split
- expected_daily_traffic
- audience_share_in_test
- variants_count
- inclusion_criteria
- exclusion_criteria

### FR-4. Metrics form
Поля:
- primary_metric_name
- metric_type
- baseline_value
- expected_uplift_pct
- mde_pct
- alpha
- power
- std_dev optional
- guardrail_metrics optional
- secondary_metrics optional

### FR-5. Constraints form
Поля:
- seasonality_present
- active_campaigns_present
- returning_users_present
- interference_risk
- technical_constraints
- legal_or_ethics_constraints
- known_risks
- deadline_pressure
- long_test_possible

### FR-6. Additional context form
Свободный текст для LLM.

### FR-7. Calculations
Сервис считает:
- required sample size per variant
- total sample size
- estimated duration in days
- notes on assumptions

### FR-8. Warnings
Сервис выдает warning'и минимум для таких случаев:
- unrealistic duration
- too small traffic
- missing variance for continuous metric
- mismatch of randomization unit and metric level
- many variants with insufficient traffic
- seasonality risk
- campaign contamination risk
- underpowered design

### FR-9. Report generation
Сервис формирует sections:
- executive_summary
- calculations
- experiment_design
- metrics_plan
- risks
- recommendations
- open_questions

### FR-10. LLM advice generation
LLM получает structured payload и возвращает:
- brief_assessment
- key_risks
- design_improvements
- metric_recommendations
- interpretation_pitfalls
- additional_checks

### FR-11. Local save/load
Пользователь может:
- сохранить эксперимент
- открыть ранее сохраненный
- обновить его
- экспортировать результат

## 5. Non-functional requirements

### NFR-1. Local first
Приложение работает локально на Windows.

### NFR-2. Explainability
UI должен явно разделять:
- deterministic calculations
- heuristic warnings
- AI advice

### NFR-3. Validation
Некорректные поля блокируют отправку формы.

### NFR-4. Resilience
Если LLM недоступна, core functionality продолжает работать.

### NFR-5. Performance
- calculations: normally under 1 second
- report composition: normally under 1 second
- LLM step may be slower but should timeout gracefully

## 6. Statistical scope for MVP

### Binary metrics
Поддержать расчеты для conversion/rate-like метрик.

Minimum output:
- baseline rate
- mde in relative and absolute form
- sample size per arm
- total sample size
- estimated duration

### Continuous metrics
Поддержать расчеты при наличии std_dev.

Minimum output:
- baseline mean
- std_dev
- mde
- sample size per arm
- total sample size
- estimated duration

## 7. Rules engine minimum set

Rule examples:
- If estimated duration > 56 days => high severity warning
- If traffic_split is not balanced and user did not justify it => medium warning
- If variants_count > 2 and daily traffic is low => high warning
- If randomization_unit = session and primary metric is user-level => high warning
- If continuous metric without std_dev => high warning
- If seasonality_present = true => recommend at least full-week coverage
- If active_campaigns_present = true => warn about contamination
- If long_test_possible = false and required duration is long => recommend redesign

## 8. Report structure

### 8.1 Executive summary
1-2 short paragraphs.

### 8.2 Calculations
Table-like section with assumptions.

### 8.3 Experiment design
- variants
- randomization
- audience
- duration
- traffic allocation
- inclusion / exclusion
- stopping rules

### 8.4 Metrics plan
- primary
- secondary
- guardrail
- diagnostic

### 8.5 Risks
Split into:
- statistical
- product
- technical
- operational

### 8.6 Recommendations
Split into:
- before launch
- during test
- after test

### 8.7 Open questions
List missing information or weak assumptions.

## 9. Integration requirement for LLM adapter

The backend must not hardcode any external SaaS-specific provider flow.
It must expose an adapter layer so the app can call a local orchestrator process or local HTTP endpoint.

The adapter must support:
- configurable base path / endpoint
- configurable timeout
- graceful failure
- structured prompt input
- structured response parsing

The current deployment assumption is local orchestrator at:
`D:\Perplexity_Orchestrator2`

Codex should inspect that project before deciding the exact integration strategy.

## 10. Acceptance criteria for MVP

MVP is done when:
- app can be started locally
- user can fill the full form
- calculations work for binary metric
- calculations work for continuous metric with std_dev
- warning engine returns meaningful warnings
- report is generated deterministically even without LLM
- if LLM is available, report includes contextual advice
- experiments can be saved locally
- report can be exported to Markdown and HTML
