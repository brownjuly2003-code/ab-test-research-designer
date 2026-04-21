# AB Test Research Designer — Комплексная оценка и рекомендации

> Дата оценки: 2026-04-04
> Версия: текущий main (eb06592)

---

## Сводная таблица оценок

| Направление | Оценка | Комментарий |
|---|---|---|
| **Продукт** | 8.0 / 10 | Чёткий фокус, решает реальную задачу, но узкая аудитория и ограниченный growth path |
| **Дизайн (визуал)** | 6.5 / 10 | Чистая типографика, но утилитарный визуал без эмоциональной составляющей |
| **UX** | 7.5 / 10 | Логичный wizard-flow, но перегружен сайдбар и нет onboarding |
| **UI** | 7.0 / 10 | Консистентные компоненты, но отсутствует дизайн-система и ряд паттернов |
| **Код** | 8.5 / 10 | Зрелая архитектура, строгая типизация, но есть структурные и security-пробелы |
| **Общая** | **7.5 / 10** | Зрелый инструмент с сильным бэкендом и слабым продуктовым/дизайн-слоем |

---

## 1. Продукт

### Сильные стороны

- **Чёткий problem-solution fit.** Инструмент решает конкретную задачу: проектирование A/B-теста с детерминированным расчётом sample size, duration, Bonferroni-коррекцией — без зависимости от SaaS-платформ.
- **Local-first архитектура.** Все данные хранятся локально (SQLite), нет внешних зависимостей для core-функций. Это правильный выбор для инструмента, работающего с чувствительными бизнес-данными.
- **Полный lifecycle.** От ввода параметров до экспорта отчёта (Markdown/HTML) — пользователь получает готовый артефакт, а не просто число.
- **Опциональный AI.** LLM-адвайзер не заменяет математику, а дополняет. Инструмент полностью функционален без LLM.
- **Workspace backup/restore.** SHA-256 + опциональный HMAC — редкий уровень data integrity для локального инструмента.

### Слабые стороны и рекомендации

| # | Проблема | Влияние | Рекомендация |
|---|---|---|---|
| P1 | **Нет чёткого позиционирования.** README описывает "что", но не "для кого" и "почему не X". Нет сравнения с Evan Miller, Optimizely, VWO calculators. | Пользователь не понимает, зачем ему этот инструмент вместо онлайн-калькулятора | Добавить секцию "Why this tool" с явным сравнением и value proposition |
| P2 | **Нет collaborative workflow.** Single-user, нет шаринга, нет ролей. Дизайн A/B-тестов — командный процесс (PM + аналитик + разработчик). | Ограничивает adoption в командах | Рассмотреть экспорт отчётов с deep-link на проект, или shared workspace через общий volume |
| P3 | **Нет интеграции с данными.** Пользователь вводит baseline conversion rate, traffic вручную. Нет подключения к GA, Amplitude, или CSV-импорта. | Увеличивает friction при каждом новом тесте | Добавить CSV/JSON импорт исторических метрик как минимум |
| P4 | **9 предупреждений-правил — закрытый набор.** Нет кастомных правил или плагинов. | Продвинутые пользователи упираются в ceiling | Рассмотреть YAML-конфигурируемый каталог правил |
| P5 | **Нет tracking результатов эксперимента.** Инструмент помогает спроектировать тест, но не отслеживать его результаты post-launch. | Неполный lifecycle — пользователь уходит в другой инструмент после запуска теста | Добавить хотя бы ручной ввод результатов и расчёт significance |

---

## 2. Дизайн (визуал)

### Сильные стороны

- **Типографика.** Inter + JetBrains Mono — профессиональная пара. Tabular numbers (`tnum`) включены для числовых значений. Fluid typography через `clamp()`.
- **Цветовая палитра.** Сдержанная нейтральная база (off-white, soft gray) с teal-акцентом. Семантические статусные цвета (зелёный = online, amber = warning, красный = error).
- **Stat-карточки.** Крупные числа (146 642, 293 284, 41 days) с чёткой типографической иерархией — хороший dashboard-паттерн.

### Слабые стороны и рекомендации

| # | Проблема | Влияние | Рекомендация |
|---|---|---|---|
| D1 | **Утилитарный визуал.** UI выглядит как internal tool / admin panel, а не как продукт. Нет визуальной "подписи", нет illustrations, нет микроанимаций. | Первое впечатление: "ещё один серый инструмент". Снижает perceived value. | Добавить: 1) hero-иллюстрацию или иконографику на пустых состояниях; 2) subtle gradient или brand-color на хэдере; 3) skeleton loading вместо Spinner |
| D2 | **Плоская визуальная иерархия.** Sidebar, wizard, results — всё на одном "слое". Нет теней, elevation, разделения глубиной. | Трудно сканировать взглядом, особенно на review-step с 5 секциями | Добавить subtle elevation (box-shadow) для карточек, section-разделители, или background-tint для секций |
| D3 | **Монотонность teal.** Единственный акцентный цвет используется для кнопок, табов, статусов и бэджей. Нет secondary/tertiary accent. | Нет визуального различия между action (Run analysis) и navigation (tab) | Ввести вторичный accent (например, indigo для navigation), оставив teal для primary actions |
| D4 | **Иконки (12 штук, inline SVG).** Минимальный набор, нет визуальной согласованности стиля (stroke weight, grid). | Выглядит как набор из разных источников | Перейти на единую иконочную систему (Lucide, Phosphor, или Heroicons) с единым optical size |
| D5 | **Dark mode не показан в demo.** Реализован через `prefers-color-scheme`, но нет контроля пользователя и нет скриншотов. | Пользователь не знает о фиче; нет возможности переключить вручную | Добавить toggle в UI (3 состояния: light/dark/system). Обновить demo-скриншоты с dark mode |
| D6 | **Нет data visualization.** Числовые результаты показаны текстом, нет графиков (power curve, sample size vs. duration, confidence interval). | Снижает data storytelling — пользователь видит числа, но не видит trade-offs визуально | Добавить хотя бы 1-2 графика: power curve, sensitivity chart (MDE vs sample size) |

---

## 3. UX (пользовательский опыт)

### Сильные стороны

- **6-шаговый wizard.** Чёткая линейная навигация: Project → Hypothesis → Setup → Metrics → Constraints → Review. Прогрессивное раскрытие сложности.
- **Autosave в localStorage.** Draft сохраняется на каждое изменение. При перезагрузке — всё на месте. Обработаны ошибки квоты.
- **Review перед запуском.** Шаг 6 показывает все введённые данные в read-only виде перед расчётом — правильный confirmation gate.
- **Read-only mode.** При readonly-токене мутации отключены на уровне UI — fail-closed.
- **Workspace status board.** Даёт snapshot здоровья данных (проекты, экспорты, ревизии).

### Слабые стороны и рекомендации

| # | Проблема | Влияние | Рекомендация |
|---|---|---|---|
| U1 | **Нет onboarding.** Новый пользователь видит пустую форму и sidebar с runtime diagnostics, SQLite pragmas, и rate limiter stats. | Огромный cognitive load при первом контакте. Непонятно, что делать. | 1) Empty state с call-to-action ("Создайте первый эксперимент" / "Импортируйте пример"); 2) Скрыть технические детали сайдбара за advanced-toggle; 3) Добавить sample project в один клик |
| U2 | **Перегруженный sidebar.** В sidebar одновременно: объяснение архитектуры, backend status, API token, runtime diagnostics (15+ строк), workspace board, current draft, project history. | Sidebar конкурирует с основным контентом. 70% информации в sidebar нужна только при дебаге. | Разделить на вкладки: "Проекты" (default) и "Система" (diagnostics, tokens, health). Или collapsible секции с closed-by-default для технических данных |
| U3 | **Нет контекстной помощи.** Поля формы (baseline rate, MDE, traffic split, std_dev) требуют статистических знаний, но нет tooltips с объяснениями или примерами. | Пользователь без stat-бэкграунда не знает, что вводить | Добавить `<Tooltip>` с пояснением и примером для каждого числового поля. Например: "Baseline conversion rate — текущий % конверсии (например, 3.5%)" |
| U4 | **`window.confirm()` для destructive actions.** Архивация/удаление используют нативный browser confirm. | Разрыв UX — нативный диалог выглядит чужеродно и не кастомизируется | Заменить на inline confirmation pattern (кнопка → "Точно удалить?" с таймером) или modal dialog |
| U5 | **Нет undo/redo.** Удаление проекта — необратимо. Нет корзины. | Пользователь может потерять данные одним кликом | Soft delete с trash (30 дней) вместо hard delete. Или хотя бы undo-toast на 5 секунд |
| U6 | **Нет keyboard shortcuts.** Wizard навигация, запуск анализа, сохранение — только мышью. | Снижает скорость для power users | Добавить: Ctrl+S (save), Ctrl+Enter (run analysis), ←/→ (wizard steps), Ctrl+E (export) |
| U7 | **Pagination "Load more" без индикации total.** История показывает 5 записей + кнопка "Show more". Нет "показано 5 из 23". | Пользователь не знает масштаб истории | Добавить total count в ответ API и показывать "5 из 23" |
| U8 | **Нет real-time validation.** Ошибки валидации показываются только при попытке перейти дальше или запустить анализ. | Пользователь заполняет 6 шагов, потом получает список ошибок | Добавить inline validation (onBlur для полей, визуальный индикатор на табах с ошибками) |

---

## 4. UI (компоненты и интерфейс)

### Сильные стороны

- **Консистентные компоненты.** Accordion, MetricCard, Icon, ProgressBar, Spinner, StatusDot, Tooltip — все с единообразным API.
- **Accessibility baseline.** `aria-hidden` на декоративных элементах, `aria-label` на icon-only buttons, `sr-only` spans, `htmlFor`/`id` на label/input.
- **Responsive layout.** Breakpoint на 900px, `auto-fit`/`minmax` grid, fluid typography через `clamp()`.
- **CSS-only dark mode.** Полная реализация через custom properties и `prefers-color-scheme`.

### Слабые стороны и рекомендации

| # | Проблема | Влияние | Рекомендация |
|---|---|---|---|
| I1 | **939 строк в одном App.css.** Нет CSS modules, styled-components, или CSS-in-JS. Все стили глобальные. | Нет scope isolation — имена классов могут конфликтовать; трудно рефакторить | Перейти на CSS Modules (`.module.css`) или Tailwind. Как минимум — разбить на файлы по компонентам |
| I2 | **Нет дизайн-токенов.** CSS custom properties есть, но нет формализованной системы (spacing scale, color palette, typography scale). | Inconsistency при добавлении новых компонентов | Определить токены: `--space-1..8`, `--color-primary/secondary/danger`, `--font-size-xs..2xl`, `--radius-sm/md/lg` |
| I3 | **Accordion без `aria-expanded`.** Toggle-кнопка не объявляет состояние screen reader'у. Нет `aria-controls`. | A11y-нарушение: WCAG 4.1.2 (Name, Role, Value) | Добавить `aria-expanded={open}` на кнопку и `aria-controls={panelId}` + `id={panelId}` на body |
| I4 | **Нет focus management в wizard.** При переходе между шагами фокус не переносится на новый контент. | Screen reader / keyboard users теряются при навигации | При смене шага — `focus()` на заголовок нового шага или первое поле |
| I5 | **`max-height: 2200px` в accordion.** Hardcoded max-height для CSS transition. | Визуальные артефакты при контенте короче/длиннее 2200px (ускорение/замедление animation). При очень длинном контенте — обрезка. | Использовать `grid-template-rows: 0fr/1fr` transition (современный подход) или JS-измерение `scrollHeight` |
| I6 | **Нет skeleton/placeholder loading.** Используется только Spinner для loading states. | CLS (Cumulative Layout Shift) при загрузке контента; нет preview структуры | Добавить skeleton screens для карточек проектов и результатов анализа |
| I7 | **Нет toast/notification system.** Ошибки показываются inline в компонентах, success — не показывается вообще (кроме изменения текста кнопки). | Пользователь не получает подтверждения успешных действий; множественные ошибки в разных местах | Реализовать toast-notification stack (success/error/warning) с auto-dismiss |
| I8 | **Компонент Tooltip реализован через CSS `::after`.** Нет позиционирования относительно viewport, нет collision detection. | Tooltip обрезается у краёв экрана, особенно в sidebar | Использовать portal-based tooltip (Floating UI / @radix-ui/react-tooltip) или хотя бы CSS `position: fixed` с JS-координатами |

---

## 5. Код

### Сильные стороны

- **Строгая типизация.** TypeScript `strict: true`, Pydantic `extra="forbid"` на всех request-моделях (кроме LlmAdviceRequest). Auto-generated API contract из OpenAPI.
- **Чистая архитектура бэкенда.** Слои: stats (чистые функции) → rules (каталог + engine) → services (оркестрация) → repository (SQLite) → main (HTTP). Нет circular dependencies.
- **`create_app()` factory pattern.** Всё состояние (repository, rate limiter, counters) в closure — тестируемость через `TestClient(create_app())`.
- **Тестовое покрытие.** 164 теста (100 backend + 64 frontend), performance benchmark с p95 < 100ms assertion, E2E Playwright, workspace roundtrip verification.
- **CI pipeline.** Matrix (Ubuntu + Windows), Docker smoke test с auth/signing, generated contract drift detection.
- **Zero tech debt markers.** Ни одного TODO/FIXME/HACK в кодовой базе.

### Слабые стороны и рекомендации

| # | Проблема | Severity | Рекомендация |
|---|---|---|---|
| C1 | **`main.py` — 1057 строк.** Все route handlers, middleware, auth, rate limiting, frontend serving — в одном файле внутри `create_app()` closure. | Medium | Извлечь APIRouter-модули: `routes/projects.py`, `routes/workspace.py`, `routes/analysis.py`, `routes/export.py`. Middleware — в `middleware.py`. |
| C2 | **`App.tsx` — god component (714 строк, 20+ state variables).** Все 3 hooks возвращают raw setters, которые App вызывает напрямую. | Medium | Перенести orchestration logic в hooks. Hooks должны экспортировать high-level actions (`saveAndAnalyze()`), а не `setLoading` + `setError` + `setResults` по отдельности. |
| C3 | **Token comparison не timing-safe.** `presented_token == settings.api_token` — уязвимость к timing oracle attack. | High (security) | Заменить на `hmac.compare_digest(presented_token, settings.api_token)` |
| C4 | **Rate limiter bucket map растёт unbounded.** `SlidingWindowRateLimiter._events` dict не evict'ит записи для неактивных клиентов. | Low (local tool) | Добавить periodic cleanup: удалять ключи, чьи deque пусты или все записи старше window |
| C5 | **Runtime counters не thread-safe.** Dict increment в `record_runtime_response` не защищён Lock. | Low | Использовать `threading.Lock` или `collections.Counter` с блокировкой |
| C6 | **Нет тестов для workspace endpoints.** Export/validate/import не покрыты тестами через HTTP (только внутренний roundtrip в скрипте). | Medium | Добавить integration tests: export → validate → import через TestClient |
| C7 | **Нет тестов для auth middleware.** Поведение при невалидном/expired/отсутствующем токене не тестируется. | Medium | Добавить test cases: valid token → 200, invalid → 401, no token when required → 401, readonly token on write endpoint → 403 |
| C8 | **Нет тестов для rate limiting и body size limits.** 429 и 413 responses не тестируются. | Medium | Добавить: burst N+1 requests → 429 с Retry-After; oversized body → 413 |
| C9 | **Нет `AbortController` на frontend.** Запросы не отменяются при unmount или при повторном запуске анализа. | Low | Добавить AbortController в `useAnalysis` — отменять предыдущий запрос при новом |
| C10 | **`experiment.ts` — 700+ строк.** Типы, validation, payload builders, field config, review sections — всё в одном файле. | Low | Разделить: `types.ts`, `validation.ts`, `payload.ts`, `field-config.ts` |

---

## 6. Приоритизированный план улучшений

### Tier 1 — Critical (делать первыми)

| # | Задача | Направление | Усилия |
|---|---|---|---|
| C3 | Timing-safe token comparison | Код / Security | 5 мин |
| I3 | `aria-expanded` + `aria-controls` на Accordion | UI / A11y | 15 мин |
| U1 | Onboarding empty state + скрытие tech-details в sidebar | UX | 2-3 ч |
| C6-C8 | Тесты для workspace, auth, rate limiting | Код | 3-4 ч |

### Tier 2 — High Impact (следующий спринт)

| # | Задача | Направление | Усилия |
|---|---|---|---|
| U2 | Sidebar tabs: "Проекты" / "Система" | UX | 2-3 ч |
| U3 | Tooltips с пояснениями на полях формы | UX | 2-3 ч |
| D2 | Elevation и визуальное разделение секций | Дизайн | 2-3 ч |
| I1 | CSS Modules (разбить App.css по компонентам) | UI | 3-4 ч |
| C1 | Извлечь APIRouter-модули из main.py | Код | 3-4 ч |
| I7 | Toast notification system | UI | 2-3 ч |
| U8 | Inline validation (onBlur + tab error indicators) | UX | 4-5 ч |

### Tier 3 — Nice to Have (backlog)

| # | Задача | Направление | Усилия |
|---|---|---|---|
| D1 | Hero illustration, brand identity | Дизайн | 1 день |
| D5 | Dark mode toggle (light/dark/system) | Дизайн | 2-3 ч |
| D6 | Data visualization (power curve, sensitivity chart) | Дизайн | 1-2 дня |
| P1 | "Why this tool" positioning section | Продукт | 2-3 ч |
| P3 | CSV/JSON импорт исторических метрик | Продукт | 1 день |
| P5 | Post-launch results tracking | Продукт | 2-3 дня |
| U5 | Soft delete + trash | UX | 3-4 ч |
| U6 | Keyboard shortcuts | UX | 3-4 ч |
| C2 | Рефакторинг App.tsx → high-level hook actions | Код | 4-5 ч |
| I2 | Формализованные design tokens | UI | 2-3 ч |
| I6 | Skeleton loading screens | UI | 2-3 ч |

---

## 7. Итоговое заключение

**AB Test Research Designer** — это зрелый, хорошо спроектированный инструмент с точки зрения engineering. Бэкенд демонстрирует production-grade подход: строгая типизация, многослойная архитектура, security hardening, comprehensive CI. Фронтенд функционально полон и корректно типизирован, но архитектурно тяготеет к monolithic-подходу (god component, single CSS file).

Главные точки роста лежат не в коде, а в **продуктовом и дизайн-слое**:

1. **Продукт** не объясняет пользователю, зачем он нужен (vs. онлайн-калькуляторы). Нет growth path за пределы single-user сценария.
2. **Дизайн** функционален, но утилитарен — нет эмоциональной составляющей, нет data visualization, нет visual storytelling.
3. **UX** нагружает пользователя техническими деталями с первого экрана (runtime diagnostics, SQLite pragmas) вместо того, чтобы помогать ему решить задачу.

Код можно улучшить инкрементально (извлечение модулей, тесты, a11y-фиксы). Продуктовые и UX-улучшения требуют более принципиальных решений о целевой аудитории и позиционировании.

---

*Оценка выполнена на основе анализа: 33 Python-файла (6 909 строк), 28 TypeScript/TSX-файлов (8 338 строк), 939 строк CSS, 3 UI-скриншота, полной документации (7 docs-файлов), CI/CD pipeline, Docker-конфигурации, и 11 automation-скриптов.*
