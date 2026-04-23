# CX Task: Дополнить template gallery до 10 индустриальных пресетов

## Goal
Сейчас в `app/backend/templates/` 5 YAML-шаблонов (`checkout_conversion`, `feature_adoption`, `latency_impact`, `onboarding_completion`, `pricing_sensitivity`). Tier 2 roadmap требует 10. Добавить 5 новых пресетов, покрывающих разные индустрии / метрические паттерны, так чтобы пользователь, переходящий с HF demo / docs site, увидел разнообразную галерею "с чего начать". Добавить на фронте удобный entry-point через existing Wizard template picker.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `f4178dd3`.
- **Существующая архитектура.**
  - YAML файлы в `app/backend/templates/`, грузятся через `app/backend/app/services/template_service.py` (посмотреть, как именно — scan directory vs. explicit registry).
  - API surface: `app/backend/app/routes/templates.py` + `app/backend/app/schemas/template.py`.
  - Frontend Wizard имеет template picker (точный путь найти через `grep -rn "templates" app/frontend/src/`).
- **Сuществующая структура YAML** (пример из `checkout_conversion.yaml`):
  ```yaml
  name: Checkout Conversion
  category: Revenue
  description: Test checkout flow changes against purchase conversion with standard revenue guardrails.
  tags: [binary, revenue, checkout]
  payload:
    project: {project_name, domain, product_type, platform, market, project_description}
    hypothesis: {change_description, target_audience, business_problem, hypothesis_statement, what_to_validate, desired_result}
    setup: {experiment_type, randomization_unit, traffic_split, expected_daily_traffic, audience_share_in_test, variants_count, inclusion_criteria, exclusion_criteria}
    metrics: {primary_metric_name, metric_type, baseline_value, expected_uplift_pct, mde_pct, alpha, ...}
    guardrails: [...]
  ```
- **Не трогать** существующие 5 шаблонов, smoke, snapshot_service, i18n locales, CI workflow.

## Deliverables

1. **5 новых YAML в `app/backend/templates/`** (по одному пресету на файл):
   - `email_campaign.yaml` — **Marketing.** A/B тест subject line'а email-кампании. Primary metric: email-to-click binary conversion. Baseline `0.038`, MDE `10%`, audience sample ~500k users.
   - `push_notification_reactivation.yaml` — **Mobile.** Push A/B на reactivation sleeping mobile users. Primary: reactivation binary, baseline `0.012`, MDE `15%`, 30d window.
   - `trial_to_paid.yaml` — **SaaS B2B.** Test trial onboarding length: 14d vs 7d. Primary: paid conversion continuous (MRR per trial), revenue guardrail ARPU, secondary activation rate.
   - `search_ranking_ctr.yaml` — **Content / Search.** Change rank fusion weights. Primary: SERP CTR binary, baseline `0.22`, MDE `3%`, high daily traffic 5M+ searches.
   - `app_onboarding_drop_off.yaml` — **Mobile onboarding.** New 3-step onboarding vs legacy 5-step. Primary: activation binary (reached key event within 24h), baseline `0.41`, MDE `5%`, audience 20k new installs/day.

   Каждый YAML заполнить **все те же поля**, что и в `checkout_conversion.yaml` (project / hypothesis / setup / metrics / guardrails). Значения — реалистичные для индустрии (не копировать числа от другого шаблона). Категории — уникальные, не дублировать `Revenue` / `Engagement`.

2. **Проверка, что шаблоны реально загружаются.**
   - Локально: `curl http://127.0.0.1:8008/api/v1/templates` после `uvicorn` → в ответе 10 шаблонов, включая 5 новых.
   - Если template_service использует explicit registry (не scan directory) — дополнить registry.

3. **Backend тесты.**
   - Добавить в `app/backend/tests/test_template_service.py` (или создать если нет) параметризованный тест, который для каждого из 10 YAML'ов:
     - Успешно парсится в `Template` schema.
     - Поля `name`, `category`, `description`, `tags`, `payload.project.project_name` непустые (кроме `project_name`, он placeholder `""`).
     - `metrics.baseline_value` > 0, `metrics.mde_pct` > 0, `metrics.alpha` в диапазоне 0.01-0.1.
     - `setup.traffic_split` суммируется в 100.
   - Пусть тест пробегает по `app/backend/templates/*.yaml` через glob — тогда добавление 11-го шаблона в будущем не потребует правки теста.

4. **Frontend template picker.**
   - Найти компонент Wizard, который показывает список шаблонов (возможно `app/frontend/src/components/Wizard/TemplatePicker.tsx` или похоже — разобраться через grep).
   - Новые шаблоны автоматически подхватятся через API — визуально ничего дополнительно делать не нужно, **если** picker уже перебирает ответ `/api/v1/templates`.
   - **Добавить группировку по `category`**, если сейчас список плоский — 10 элементов уже неудобно смотреть одной колонкой. Использовать `<details>` / `<section>` grouping или existing design primitives (найти через grep на другие category groupings в проекте).

5. **Frontend unit-тест.**
   - В `app/frontend/src/components/Wizard/*.test.tsx` (или эквивалент) добавить тест "Wizard template picker renders at least 10 templates grouped by category" — через мокнутый API-ответ с 10 пресетами.

6. **Documentation.**
   - В `docs-site/features/wizard.md` упомянуть gallery из 10 пресетов с одной строкой описания каждого.
   - В `docs-site/getting-started/quickstart.md` показать как выбрать template при первом запуске (1-2 строки).
   - **Не** писать отдельную "Templates" страницу — это лишнее.

## Acceptance
- `ls app/backend/templates/*.yaml | wc -l` = 10.
- `python -m pytest app/backend/tests/test_template_service.py -v` → все 10 пресетов zipпроходят.
- `npm --prefix app/frontend run test -- Wizard` → новый тест зелёный, старые не сломались.
- `scripts/verify_all.py --with-e2e --skip-build` → exit 0.
- `curl http://127.0.0.1:8008/api/v1/templates | jq '. | length'` = 10.
- Визуально (ручной прогон через `npm run dev`): Wizard template picker показывает 10 шаблонов, сгруппированных по category'и, без horizontal scroll.
- mkdocs-site `features/wizard.md` отражает новую gallery.
- Один коммит: `feat(templates): extend gallery to 10 industry presets`.

## Notes
- **Числа в пресетах реалистичные, не placeholder.** Например baseline 0.22 для SERP CTR — типичный indexщ, 0.012 для push reactivation — тоже. Не писать `0.5` / `100` "от балды". Если сомневаешься — возьми порядки из открытых ресурсов (Wiser / Optimizely / Evan Miller blog posts).
- **Не добавлять 11-й шаблон на всякий случай.** Scope чётко — 5 новых, итого 10. Template gallery не фиктивный — каждая presets должна иметь своё место.
- Отчёт (15-20 строк): список 5 новых шаблонов с категорией и primary metric, API response length, screenshot picker'а (или описание).
