# План: от internal tool до коммерческого продукта

> Цель: довести AB Test Research Designer до уровня, конкурентоспособного с Statsig Power Calculator, Eppo Planning, VWO SmartStats — но с фокусом на local-first, privacy-first, open-source позиционирование.

---

## Контекст: что говорит рынок (2025–2026)

**Table-stakes фичи, без которых инструмент не воспринимается серьёзно:**
1. Live-updating calculations (слайдеры MDE/power/alpha → мгновенный пересчёт)
2. Duration estimation с конкретными датами, не только sample size
3. Мульти-метрика (primary + guardrail metrics в одном эксперименте)
4. Shareable результаты (ссылка / PDF / экспорт для стейкхолдеров)
5. Progressive disclosure (Simple → Advanced mode)

**Дифференцирующие фичи коммерческих инструментов:**
1. Warehouse-native power analysis (подключение к реальным данным)
2. Sequential testing + CUPED/variance reduction
3. SRM detection (Sample Ratio Mismatch)
4. AI-powered experiment review (pre-flight checks)
5. Forest plot + time-series визуализации

**Наша дифференциация (competitive moat):**
- Local-first, zero-cloud, zero-tracking — единственный инструмент, который можно запустить в air-gapped среде
- Детерминированный движок (нет black-box magic как у VWO SmartStats)
- Open-source с прозрачной математикой
- Workspace backup с cryptographic integrity (SHA-256 + HMAC)

---

## Фаза 0: Foundation (1 неделя)

> Техническая база для всех последующих фаз. Без этого дальнейшие изменения будут болезненны.

### 0.1. Дизайн-система и CSS-архитектура
- [ ] Формализовать design tokens: `--space-{1..8}` (4/8/12/16/24/32/48/64px), `--font-size-{xs..2xl}`, `--color-{semantic}` → Verify: токены используются во всех новых компонентах
- [ ] Разбить `App.css` (939 строк) на CSS Modules по компонентам: `WizardPanel.module.css`, `SidebarPanel.module.css`, `ResultsPanel.module.css`, общее — `tokens.css` + `reset.css` → Verify: нет глобальных class-конфликтов, `npm run build` проходит
- [ ] Добавить secondary accent color (indigo `#4f46e5` для navigation, оставив teal для actions) → Verify: tabs и кнопки визуально различаются

### 0.2. Бэкенд-модуляризация
- [ ] Извлечь из `main.py` (1057 строк) APIRouter-модули: `routes/analysis.py`, `routes/projects.py`, `routes/workspace.py`, `routes/export.py` → Verify: все 164 теста проходят, OpenAPI-схема идентична
- [ ] Timing-safe token comparison: `hmac.compare_digest()` вместо `==` → Verify: тест с side-channel assert

### 0.3. Фронтенд-архитектура
- [ ] Рефакторинг `App.tsx` (714 строк): hooks экспортируют high-level actions (`analyzeAndSave()`, `loadProject()`) вместо raw setters → Verify: `App.tsx` < 300 строк, все тесты проходят
- [ ] Разделить `experiment.ts` (700+ строк) → `types.ts`, `validation.ts`, `payload.ts`, `field-config.ts` → Verify: imports обновлены, typecheck проходит

---

## Фаза 1: UX-трансформация (2 недели)

> Превращение из "инструмента для разработчика" в "продукт для аналитика".

### 1.1. Onboarding и информационная архитектура

**Проблема:** Новый пользователь видит пустую форму, а в sidebar — SQLite pragmas, rate limiter stats, runtime counters. Cognitive overload.

- [ ] **Empty state с guided start.** Вместо пустого wizard'а — hero-экран с 3 опциями: "Новый эксперимент", "Загрузить пример", "Импортировать проект". Кнопка "Загрузить пример" подгружает `sample-project.json` в один клик → Verify: новый пользователь за < 10 секунд видит заполненную форму и может нажать "Run analysis"
- [ ] **Sidebar redesign — 2 вкладки.** Tab 1: "Проекты" (список проектов, active project info, history). Tab 2: "Система" (backend health, diagnostics, API token, workspace). По умолчанию открыта "Проекты". Убрать "How this UI is split" — это dev-documentation, не user-facing content → Verify: 80% площади sidebar занимает полезный контент
- [ ] **Убрать runtime diagnostics из default view.** SQLite pragmas, rate limiter counters, response time p95 — скрыть за `<details>` или перенести в `/diagnostics` route → Verify: sidebar не содержит технического жаргона без explicit expand

### 1.2. Контекстная помощь

**Проблема:** Поля baseline_rate, mde, std_dev, traffic_split требуют статистических знаний, но нет пояснений.

- [ ] **Tooltips на каждом числовом поле.** Формат: название + 1 строка описания + пример значения. Данные для tooltips:
  - `baseline_rate`: "Текущий показатель метрики до эксперимента. Пример: 3.5% для конверсии в покупку"
  - `mde`: "Минимальный эффект, который вы хотите обнаружить. Пример: 0.5 п.п. для 3.5% → 4.0%"
  - `std_dev`: "Стандартное отклонение метрики (для continuous). Пример: 12.5 для среднего чека"
  - `traffic_split`: "Доля трафика на каждый вариант. Пример: 50,50 для двух равных групп"
  - `daily_traffic`: "Среднее число пользователей/сессий в день. Пример: 10000"
  → Verify: hover на каждом поле показывает tooltip с примером
- [ ] **Tooltip-компонент: переписать на portal-based.** Текущий CSS `::after` обрезается у краёв экрана. Использовать Floating UI (`@floating-ui/react-dom`, ~3KB gzip) → Verify: tooltip у правого края sidebar позиционируется корректно

### 1.3. Live-updating calculations (killer feature)

**Проблема:** Сейчас цикл: заполни 6 шагов → нажми "Run analysis" → жди результат. У конкурентов — мгновенный пересчёт.

- [ ] **Добавить real-time preview panel.** На шагах Setup (3) и Metrics (4) — боковая панель с live-расчётом sample size и duration. При изменении любого числового поля — debounced (300ms) вызов `/api/v1/calculate` → Verify: изменение MDE с 0.5 на 1.0 обновляет preview за < 500ms
- [ ] **Slider для MDE.** Заменить число-input на range slider + число-input (dual control). Диапазон: 0.1% — 20% для binary, 0.1 — 50 для continuous. Шаг: 0.1 → Verify: перетаскивание слайдера обновляет preview в реальном времени
- [ ] **Slider для Power.** Range: 0.7 — 0.99, шаг 0.01. Default: 0.8. Показывать label "80% power" → Verify: увеличение power увеличивает required sample size в preview

### 1.4. Inline validation и UX-улучшения

- [ ] **onBlur validation.** Каждое числовое поле валидируется при потере фокуса. Красная иконка + tooltip с ошибкой. Таб-кнопки wizard'а показывают dot-indicator если на шаге есть ошибки → Verify: ввод отрицательного MDE → красная рамка + сообщение при blur
- [ ] **Toast notification system.** Реализовать стек toast'ов (success/error/warning) с auto-dismiss (5 секунд для success, persistent для errors). Использовать для: save success, export success, import success, validation errors → Verify: "Save project" → зелёный toast "Проект сохранён"
- [ ] **Заменить `window.confirm()` на inline confirmation.** Кнопка "Удалить" → "Точно удалить? (3...2...1)" с обратным отсчётом → Verify: нет нативных browser-диалогов
- [ ] **Keyboard shortcuts.** `Ctrl+S` — save, `Ctrl+Enter` — run analysis, `Ctrl+E` — export, `←/→` — wizard steps → Verify: shortcuts работают, показаны в tooltips на кнопках

---

## Фаза 2: Визуальная трансформация (1.5 недели)

> Из "admin panel" в "modern analytics tool".

### 2.1. Dashboard-grade data visualization

**Проблема:** Все результаты — текст и числа. Нет графиков, нет visual storytelling.

- [ ] **Power curve chart.** По оси X — MDE (от 0.1% до 5×текущий MDE), по оси Y — Power (0–1). Горизонтальная линия на 0.8. Вертикальная линия на текущем MDE. Точка пересечения = текущая конфигурация. Библиотека: Recharts (~45KB gzip, React-native, responsive) → Verify: график рендерится в ResultsPanel, responsive на мобильных
- [ ] **Sensitivity table (MDE vs Duration).** Матрица: строки — MDE (5 значений вокруг текущего), столбцы — Power (0.7, 0.8, 0.9, 0.95). Ячейки — duration в днях. Текущая конфигурация подсвечена. Паттерн: как у Statsig "Week-by-Week Power Preview" → Verify: таблица показывает 20 ячеек, текущая конфигурация выделена цветом
- [ ] **Sample size breakdown bar.** Горизонтальный stacked bar: control + каждый variant, пропорционально traffic_split. Показывает, сколько пользователей нужно в каждой группе → Verify: для 3 вариантов (33/33/34) — 3 цветных сегмента с числами
- [ ] **Эндпоинт `/api/v1/sensitivity`.** Принимает те же параметры + `mde_range` и `power_levels`, возвращает матрицу `{mde, power, sample_size, duration_days}[]` → Verify: curl возвращает массив из 20 записей

### 2.2. Визуальная полировка

- [ ] **Elevation и depth.** Добавить `box-shadow` на карточки метрик (subtle, 0 2px 8px rgba(0,0,0,0.06)). Wizard panel и sidebar — на разных "уровнях" (sidebar чуть утоплен или приподнят) → Verify: видна визуальная глубина между элементами
- [ ] **Empty state illustrations.** SVG-иллюстрации для: "Нет проектов" (telescope/compass), "Нет результатов" (chart placeholder), "Backend offline" (plug/socket). Стиль: line art, teal accent → Verify: каждый empty state имеет иллюстрацию
- [ ] **Skeleton loading.** Заменить Spinner на skeleton screens для: project list cards, results panel, metric cards. CSS-only (`background: linear-gradient` animation) → Verify: при загрузке видны skeleton-прямоугольники вместо spinner'а
- [ ] **Micro-interactions.** Кнопки: scale(0.98) on :active. Cards: subtle lift (translateY(-1px)) on hover. Success states: checkmark animation (CSS only) → Verify: визуальный feedback при клике на каждую кнопку
- [ ] **Dark mode toggle.** Три состояния: Light / Dark / System. Переключатель в header'е. Сохранение в localStorage → Verify: переключение работает без перезагрузки, preference сохраняется

### 2.3. Иконочная система

- [ ] Заменить 12 inline SVG иконок на [Lucide React](https://lucide.dev/) (~tree-shakeable, consistent 24px grid, 1.5px stroke). Нужные иконки: Activity, Check, ChevronRight, Clock, Code, Download, FileText, Info, Plus, Search, Trash2, AlertTriangle, Settings, Moon, Sun, Monitor, BarChart3, TrendingUp, Shield, Sliders → Verify: `npm run build` проходит, bundle size увеличился < 5KB

---

## Фаза 3: Product-grade фичи (2 недели)

> Фичи, которые превращают калькулятор в продукт.

### 3.1. Multi-metric experiments

**Проблема:** Сейчас — одна метрика на эксперимент. В реальности аналитик отслеживает primary metric + 2-3 guardrail metrics.

- [ ] **UI: секция "Guardrail metrics" на шаге Metrics.** До 3 дополнительных метрик (name, type, baseline, MDE) с пометкой "guardrail — не влияет на sample size, но мониторится" → Verify: можно добавить 3 guardrail metrics и они появляются в review
- [ ] **Backend: guardrail metrics в payload.** Новое поле `guardrail_metrics: list[MetricInput]` в `ExperimentInput`. Расчёт sample size — только по primary. Guardrails включаются в report как отдельная секция → Verify: `/api/v1/analyze` с guardrails возвращает секцию "Guardrail metrics" в отчёте
- [ ] **Sensitivity table для guardrails.** Для каждой guardrail metric — row в sensitivity table с минимальным MDE, которую этот тест сможет обнаружить при текущем sample size → Verify: guardrail с MDE=0.1% при N=10000 показывает "Detectable MDE: 0.8%"

### 3.2. SRM Detection (Sample Ratio Mismatch)

**Проблема:** Ни один open-source калькулятор не проверяет корректность рандомизации. Это low-hanging fruit для дифференциации.

- [ ] **Новое правило `SRM_DETECTED`.** Chi-square тест: ожидаемое распределение (traffic_split) vs фактическое (введённое пользователем). Severity: high. Пороговый p-value: 0.001 → Verify: split [50,50] с actual [4800, 5200] → SRM warning
- [ ] **UI: SRM checker.** На шаге Review или в Results — мини-форма "Введите фактические числа по группам" → chi-square → визуальный индикатор (green/red) → Verify: ввод [5000, 5000] → зелёная галка, ввод [4500, 5500] → красный alert
- [ ] **Backend: `/api/v1/srm-check`.** Принимает expected_split + actual_counts, возвращает chi_square, p_value, verdict → Verify: curl с actual [4800, 5200] и expected [50,50] → p_value < 0.001

### 3.3. Post-experiment results tracker

**Проблема:** Инструмент помогает спроектировать тест, но не завершить цикл (ввести результаты → получить вывод).

- [ ] **UI: новая секция "Результаты эксперимента" в проекте.** Поля: actual_control_rate, actual_treatment_rate (для binary) или actual_control_mean/std, actual_treatment_mean/std (для continuous), actual_sample_per_group → Verify: после заполнения — расчёт observed effect, z-statistic, p-value, confidence interval
- [ ] **Backend: `/api/v1/results`.** Принимает observed data, возвращает: observed_effect, confidence_interval_95, p_value, is_significant, power_achieved → Verify: curl с rates [3.5%, 4.0%] и N=50000 → p_value, CI, significance verdict
- [ ] **Визуализация: forest plot.** Горизонтальная линия с точкой (observed effect) и whiskers (95% CI). Вертикальная нулевая линия. Подпись: "Effect: +0.5 pp [0.2, 0.8], p=0.003" → Verify: plot рендерится, zero-line видна

### 3.4. Shareable reports

**Проблема:** Экспорт есть (Markdown/HTML), но нет "ссылки для стейкхолдера".

- [ ] **Self-contained HTML report.** `/api/v1/export/html-standalone` — полный HTML-файл с inline CSS, inline Recharts (pre-rendered SVG), print-optimized layout. Стейкхолдер открывает файл в браузере — видит dashboard с графиками → Verify: HTML-файл открывается offline, содержит power curve и sensitivity table
- [ ] **PDF-ready print styles.** `@media print` в report CSS: hide navigation, single-column, page breaks between sections → Verify: Ctrl+P из HTML report генерирует чистый PDF

---

## Фаза 4: Advanced статистика (1.5 недели)

> Дифференциация от Evan Miller и базовых калькуляторов.

### 4.1. Sequential testing support

**Проблема:** Текущий движок — только fixed-horizon. Sequential testing позволяет "подглядывать" в результаты без inflating Type I error.

- [ ] **Backend: spending function approach.** Реализовать O'Brien-Fleming alpha spending для group sequential design. Параметр: `n_looks` (количество промежуточных проверок, default 1 = fixed horizon). При n_looks > 1 — пересчёт adjusted alpha для каждого look → Verify: n_looks=5, alpha=0.05 → spending [0.0001, 0.004, 0.019, 0.043, 0.05] (O'Brien-Fleming boundaries)
- [ ] **UI: "Interim looks" field на шаге Constraints.** Number input, range 1–10. При > 1 — показать таблицу: look number, cumulative sample, adjusted alpha → Verify: n_looks=3 → таблица с 3 строками
- [ ] **Warning rule: `INTERIM_LOOKS_INCREASE_SAMPLE`.** Когда n_looks > 1 — предупреждение: "Sequential design увеличивает required sample size на ~X% для сохранения общего alpha" → Verify: n_looks=5 увеличивает sample size на ~25-30%

### 4.2. CUPED (Controlled-experiment Using Pre-Experiment Data) estimation

- [ ] **Backend: CUPED variance reduction estimator.** Если пользователь предоставляет `pre_experiment_variance` и `covariance_with_outcome` — рассчитать reduced variance и показать "CUPED-adjusted sample size" рядом с naive → Verify: CUPED с correlation 0.5 уменьшает sample size на ~25%
- [ ] **UI: optional "CUPED" toggle на шаге Metrics.** При включении — дополнительные поля: pre_experiment_std, correlation. Preview показывает savings → Verify: toggle On → два дополнительных поля, preview показывает "Экономия: -30% sample size"

### 4.3. Bayesian power analysis (optional mode)

- [ ] **Backend: Bayesian sample size calculator.** Credible interval width targeting: "найти N, при котором posterior 95% credible interval уже чем X". Используем нормальное приближение (не MCMC) → Verify: Bayesian N ≈ Frequentist N ± 15% для типичных параметров
- [ ] **UI: radio "Frequentist / Bayesian" на шаге Constraints.** При Bayesian — заменить alpha/power на "desired precision" (ширина credible interval) → Verify: переключение меняет набор полей

---

## Фаза 5: Polish и go-to-market (1 неделя)

### 5.1. Landing page и позиционирование

- [ ] **Landing page (`/` без авторизации).** Hero: "Plan experiments with confidence. Local-first. Open-source. Zero tracking." + 3 feature cards + screenshot + "Get Started" → Verify: `/` показывает landing, `/app` — приложение
- [ ] **"Why this tool" comparison table.** Строки: Local-first, Open-source, Deterministic math, Sequential testing, SRM detection, Workspace encryption, Zero cloud dependency. Столбцы: This tool, Evan Miller, Statsig, VWO → Verify: таблица корректна, checkmarks/crosses верны
- [ ] **README rewrite.** Вместо dev-focused docs — product-focused: problem → solution → quick start → screenshots → comparison → contributing → Verify: README читается за 2 минуты и отвечает на "зачем мне это"

### 5.2. Accessibility и i18n readiness

- [ ] **A11y audit.** Accordion: `aria-expanded`, `aria-controls`. Wizard: focus management при смене шагов. Skip-to-content link. Color contrast check (WCAG AA) → Verify: axe-core audit — 0 critical violations
- [ ] **i18n infrastructure.** Вынести все строки в `src/i18n/en.json`. Не переводить сейчас, но обеспечить infrastructure для будущих переводов → Verify: ни одна user-facing строка не hardcoded в JSX

### 5.3. Performance и bundle

- [ ] **Bundle analysis.** Recharts tree-shaking, Lucide tree-shaking, Floating UI tree-shaking. Target: < 150KB gzip total JS → Verify: `vite-bundle-visualizer` показывает < 150KB
- [ ] **Lighthouse audit.** Target: Performance > 95, Accessibility > 95, Best Practices > 95, SEO > 90 → Verify: Lighthouse CI в GitHub Actions

---

## Зависимости между фазами

```
Фаза 0 (Foundation) ──┬── Фаза 1 (UX) ──── Фаза 3.3 (Results tracker)
                       │                  │
                       ├── Фаза 2 (Visual) ── Фаза 3.4 (Shareable reports)
                       │
                       └── Фаза 3.1-3.2 (Multi-metric, SRM)
                                          │
                                          └── Фаза 4 (Advanced stats)
                                                        │
                                                        └── Фаза 5 (Polish)
```

- Фаза 0 — обязательный prereq для всех остальных
- Фазы 1, 2, 3.1-3.2 могут идти параллельно после Фазы 0
- Фаза 4 зависит от Фазы 3 (multi-metric infrastructure)
- Фаза 5 — финальная, после всех остальных

---

## Технологические решения

| Решение | Выбор | Почему |
|---|---|---|
| Charts | [Recharts](https://recharts.org/) | React-native, tree-shakeable, responsive, ~45KB gzip, active maintenance |
| Icons | [Lucide React](https://lucide.dev/) | Tree-shakeable, consistent 24px grid, 1.5px stroke, MIT |
| Tooltips | [@floating-ui/react-dom](https://floating-ui.com/) | Minimal (~3KB), handles positioning/collision, no headless UI overhead |
| CSS approach | CSS Modules | Zero runtime, co-located with components, works with Vite out of the box |
| State management | Existing hooks (refactored) | Нет нужды в Redux/Zustand для single-page app с < 30 state vars |
| Sequential testing math | O'Brien-Fleming spending function | Standard in clinical trials, well-understood, no external library needed |
| Bayesian | Normal approximation | Sufficient for planning (not analysis), avoids MCMC complexity |

### Принципиальные отказы

| Отвергнуто | Почему |
|---|---|
| Tailwind CSS | Не обоснован для 15 компонентов; CSS Modules проще и не добавляют build dependency |
| Zustand/Jotai | Over-engineering для single-page app без shared state across routes |
| D3.js | Слишком низкоуровневый; Recharts даёт нужные chart types из коробки |
| Radix UI | Только для tooltip нужен @floating-ui; полная headless UI — overhead |
| SciPy (backend) | Python stdlib `math` + формулы достаточны для z/t-test и chi-square; SciPy — 30MB dependency |

---

## Метрики успеха

| Метрика | Текущее | Цель |
|---|---|---|
| Time to first analysis (new user) | > 3 min (заполнить 6 шагов вручную) | < 30 sec (загрузить пример → Run) |
| Понятность для non-statistician | Низкая (нет tooltips, tech jargon в sidebar) | Высокая (tooltips, progressive disclosure) |
| Visual appeal (субъективно) | 6.5/10 (утилитарный) | 8.5/10 (modern analytics tool) |
| Feature parity vs Evan Miller | Выше (duration, multivariant, rules) | Значительно выше (sequential, SRM, multi-metric, viz) |
| Feature parity vs Statsig | Ниже (нет viz, нет live calc, нет multi-metric) | Comparable (кроме warehouse-native) |
| Bundle size (JS) | ~80KB gzip | < 150KB gzip (с charts и icons) |
| Lighthouse Accessibility | Не измерено | > 95 |
| Test coverage (backend) | 100 tests | 130+ tests (workspace, auth, rate limit, SRM, sequential) |

---

## Общая оценка трудоёмкости

| Фаза | Длительность | FTE |
|---|---|---|
| 0. Foundation | 1 неделя | 1 dev |
| 1. UX-трансформация | 2 недели | 1 dev |
| 2. Visual | 1.5 недели | 1 dev (+ дизайнер для illustrations) |
| 3. Product features | 2 недели | 1 dev |
| 4. Advanced stats | 1.5 недели | 1 dev (с stat background) |
| 5. Polish | 1 неделя | 1 dev |
| **Итого** | **~9 недель** | **1 fullstack dev** |

Параллельные фазы (1+2, или 3.1+3.2) могут сократить timeline до ~6-7 недель при 2 dev.

---

*Исследованы: Evan Miller, Optimizely Stats Engine + AI Agents, VWO SmartStats + ROPE, Statsig Power Calculator + Week-by-Week Preview, Eppo Progress Bar + Precision Stopping, AB Tasty Evi + S-SRM, LaunchDarkly Sequential, PostHog SQL-first, GrowthBook open-source. Decision: адаптировать лучшие паттерны, сохранив local-first дифференциацию.*
