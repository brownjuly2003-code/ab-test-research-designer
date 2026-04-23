# BCG Implementation Plan: AB Test Research Designer

**Дата:** 12 апреля 2026  
**Основание:** BCG Audit Report (`BCG_audit.md`)  
**Горизонт:** 12 недель (4 фазы)  
**Целевая оценка:** 6.8 → 8.5 / 10  

---

## Принципы выполнения

1. **Тесты ДО рефакторинга** — ни одна строка production-кода не меняется без покрывающего теста
2. **Один PR — одна задача** — атомарные, reviewable изменения
3. **Verify each step** — каждая задача содержит критерий проверки
4. **Не ломать текущий функционал** — все существующие 17 backend-тестов и 8 frontend-тестов должны проходить на каждом шаге

---

## Фаза 1: Foundation Fix (недели 1-3)

**Цель:** Устранить технический долг фронтенда, блокирующий всю дальнейшую работу.  
**Метрика входа:** Frontend architecture score 4.0/10  
**Метрика выхода:** Frontend architecture score 7.0/10  

### 1.1 Страховочная сеть: фронтенд-тесты для критических хуков

Перед любым рефакторингом — зафиксировать текущее поведение тестами.

- [x] **1.1.1** Тесты для `useAnalysis` (179 строк, 0 тестов) → `useAnalysis.test.tsx` (replaced by `analysisStore.test.ts`; landed in 8413328e)
  - Покрыть: `runAnalysis` happy path, `clearAnalysis`, `invalidateResults`, `validateDraft` с ошибками, `showStatus`/`showError` toggle
  - Verify: `npx vitest run src/hooks/useAnalysis.test.tsx` — 5+ тестов, все зелёные

- [x] **1.1.2** Тесты для `useProjectManager` (850 строк, 0 тестов) → `useProjectManager.test.tsx` (replaced by `projectStore.test.ts`; landed in 8413328e)
  - Покрыть: `refreshBackendState`, `saveProject` (new + update), `loadProject`, `archiveProject`/`restoreProject`, `markDraftChanged`/`hasUnsavedChanges`, `persistAnalysisSnapshot`
  - Mock: все функции из `lib/api.ts` (уже протестированы отдельно в `api.test.ts`)
  - Verify: `npx vitest run src/hooks/useProjectManager.test.tsx` — 8+ тестов

- [x] **1.1.3** Тесты для `useDraftPersistence` (163 строки, 0 тестов) → `useDraftPersistence.test.tsx` (replaced by `draftStore.test.ts`; landed in 8413328e)
  - Покрыть: `readDraftBootstrap` (localStorage пустой / с данными / corrupted), `replaceDraft`, `resetDraft`, `parseImportedDraftText` (valid / invalid JSON), `draftStorageWarning` при quota exceeded
  - Verify: `npx vitest run src/hooks/useDraftPersistence.test.tsx` — 6+ тестов

- [x] **1.1.4** Snapshot-тесты для `WizardPanel` и `WizardReviewStep` (landed in 8413328e)
  - Рендер с типовыми пропсами, snapshot для регрессии
  - Verify: `npx vitest run` — все существующие + новые тесты зелёные

### 1.2 State management: Zustand

Устранение God Component паттерна. `App.tsx` (478 строк) → тонкий shell.

- [x] **1.2.1** Установить Zustand: `npm i zustand` (landed in 8413328e)
  - Verify: `package.json` содержит `"zustand"`, `npm ls zustand` без ошибок

- [x] **1.2.2** Создать `src/stores/themeStore.ts` (landed in 8413328e)
  - Перенести: `theme` state, `setTheme`, localStorage sync (строки 44-47, 72-85 в `App.tsx`)
  - Интерфейс: `useThemeStore()` → `{ theme, setTheme }`
  - Verify: theme toggle работает, localStorage пишется, dark mode применяется

- [x] **1.2.3** Создать `src/stores/wizardStore.ts` (landed in 8413328e)
  - Перенести: `step`, `showOnboarding`, `importingDraft`, `openWizard()` (строки 48-50, 97-100)
  - Интерфейс: `useWizardStore()` → `{ step, setStep, showOnboarding, setShowOnboarding, importingDraft, setImportingDraft, openWizard }`
  - Verify: wizard navigation (Next/Back/Step click) работает, onboarding показывается для новых пользователей

- [x] **1.2.4** Создать `src/stores/analysisStore.ts` (landed in 8413328e)
  - Перенести всю логику из `useAnalysis.ts` (179 строк): `results`, `isAnalyzing`, `analysisError`, `statusMessage`, `validationErrors`
  - Перенести: `runAnalysis`, `clearAnalysis`, `invalidateResults`, `showStatus`, `showError`, `clearFeedback`, `validateDraft`, `ensureValidForm`, `linkResultToProject`, `getPersistableAnalysis`
  - Verify: `npx vitest run` — тесты 1.1.1 проходят на store вместо hook

- [x] **1.2.5** Создать `src/stores/projectStore.ts` (landed in 8413328e)
  - Перенести всю логику из `useProjectManager.ts` (850 строк): проекты, health, diagnostics, history, revisions, comparison, API token
  - Интерфейс: `useProjectStore()` → все поля и методы, которые сейчас в `projectManager`
  - Verify: `npx vitest run` — тесты 1.1.2 проходят на store

- [x] **1.2.6** Создать `src/stores/draftStore.ts` (landed in 8413328e)
  - Перенести логику из `useDraftPersistence.ts` (163 строки)
  - Verify: `npx vitest run` — тесты 1.1.3 проходят на store

- [x] **1.2.7** Рефакторинг `App.tsx`: заменить hooks на stores (landed in 8413328e)
  - Удалить: `useState` для theme/step/onboarding/importingDraft
  - Удалить: `useAnalysis()`, `useProjectManager()`, `useDraftPersistence()`
  - Заменить на: `useThemeStore()`, `useWizardStore()`, `useAnalysisStore()`, `useProjectStore()`, `useDraftStore()`
  - Удалить: объекты `wizardPanelProps` (30+ props) и `sidebarPanelProps` (50+ props) — дочерние компоненты читают stores напрямую
  - **Целевой размер App.tsx:** <120 строк (layout + роутинг + keyboard shortcuts)
  - Verify: `npx vitest run` — все тесты зелёные, ручная проверка: новый проект → заполнить → Run analysis → Save → Load → Archive → Restore

- [x] **1.2.8** Упростить `WizardPanel.tsx` и `SidebarPanel.tsx` (landed in 8413328e)
  - Убрать prop drilling — компоненты читают из stores напрямую
  - `WizardPanel`: убрать ~30 входных пропсов, оставить только UI-специфичные
  - `SidebarPanel` (994 строки): убрать ~50 входных пропсов
  - Verify: полный e2e flow работает

### 1.3 Декомпозиция ResultsPanel (1914 строк → 10-12 модулей)

- [x] **1.3.1** Выделить `src/components/results/SensitivitySection.tsx` (landed in 8413328e)
  - Перенести: sensitivity form, fetch logic, `SensitivityTable` рендеринг
  - ~200 строк из ResultsPanel
  - Verify: sensitivity table загружается, MDE/Power сетка отображается

- [x] **1.3.2** Выделить `src/components/results/PowerCurveSection.tsx` (landed in 8413328e)
  - Перенести: lazy-loaded `PowerCurveChart`, Suspense wrapper
  - ~50 строк
  - Verify: power curve chart рендерится с данными анализа

- [x] **1.3.3** Выделить `src/components/results/SrmCheckSection.tsx` (landed in 8413328e)
  - Перенести: SRM form state (`srmForm`, `srmResult`), fetch, UI
  - ~120 строк
  - Verify: SRM check с 2 и 3 вариантами, корректный p-value

- [x] **1.3.4** Выделить `src/components/results/ObservedResultsSection.tsx` (landed in 8413328e)
  - Перенести: `BinaryResultsForm`/`ContinuousResultsForm`, `buildResultsRequest`, `ForestPlot`
  - ~250 строк
  - Verify: binary и continuous results формы, CI отображается

- [x] **1.3.5** Выделить `src/components/results/SequentialDesignSection.tsx` (landed in 8413328e)
  - Перенести: sequential boundaries table, interim analysis details
  - ~80 строк
  - Verify: O'Brien-Fleming таблица с корректными z-boundaries

- [x] **1.3.6** Выделить `src/components/results/WarningsSection.tsx` (landed in 8413328e)
  - Перенести: warnings list с severity styling
  - ~60 строк
  - Verify: warnings отображаются с корректными иконками/цветами по severity

- [x] **1.3.7** Выделить `src/components/results/ExperimentDesignSection.tsx` (landed in 8413328e)
  - Перенести: design details, variants, assumptions
  - ~100 строк

- [x] **1.3.8** Выделить `src/components/results/MetricsPlanSection.tsx` (landed in 8413328e)
  - Перенести: primary/secondary/guardrail metrics display
  - ~80 строк

- [x] **1.3.9** Выделить `src/components/results/RisksSection.tsx` (landed in 8413328e)
  - Перенести: statistical/product/technical/operational risks
  - ~60 строк

- [x] **1.3.10** Выделить `src/components/results/AiAdviceSection.tsx` (landed in 8413328e)
  - Перенести: LLM recommendations display
  - ~60 строк

- [x] **1.3.11** Выделить `src/components/results/ComparisonSection.tsx` (landed in 8413328e)
  - Перенести: project comparison view, delta display
  - ~80 строк

- [x] **1.3.12** Собрать новый `ResultsPanel.tsx` — тонкий orchestrator (landed in 8413328e)
  - Импортирует 11 секций, рендерит через `Accordion`
  - **Целевой размер:** <150 строк
  - Verify: `npx vitest run` — все тесты, ручная проверка полного results view

### 1.4 Error Boundaries

- [x] **1.4.1** Создать `src/components/ErrorBoundary.tsx` (landed in 8413328e)
  - Class component с `componentDidCatch`
  - Fallback UI: иконка + «Something went wrong» + кнопка Retry
  - Props: `fallback?: ReactNode`, `onError?: (error: Error) => void`
  - Verify: бросить ошибку в тестовом компоненте — fallback отображается

- [x] **1.4.2** Создать `src/components/ChartErrorBoundary.tsx` (landed in 8413328e)
  - Специфичный fallback для Recharts/ForestPlot: «Chart unavailable» + raw data в `<pre>`
  - Verify: ошибка в PowerCurveChart → fallback, остальные секции работают

- [x] **1.4.3** Обернуть layout в `App.tsx`: `<ErrorBoundary>` вокруг `<WizardPanel>` и `<SidebarPanel>` (landed in 8413328e)
  - Обернуть каждый chart-компонент в `<ChartErrorBoundary>`
  - Verify: crash в sidebar не роняет wizard, crash в chart не роняет results

### 1.5 CSS-архитектура: унификация

- [x] **1.5.1** Аудит глобальных классов в `App.css` (214 строк) (landed in 8413328e)
  - Разделить на: `src/styles/layout.css` (`.page`, `.shell`, `.grid`), `src/styles/components.css` (`.btn`, `.field`, `.card`, `.toast-*`), `src/styles/utilities.css` (`.muted`, `.pill`, `.icon`)
  - Verify: визуально без изменений, все стили применяются

- [x] **1.5.2** Перевести компоненты без CSS Modules на модули (landed in 8413328e)
  - `EmptyState`, `ToastSystem`, `Accordion`, `MetricCard`, `SliderInput`, `Spinner`, `Skeleton`, `ProgressBar`, `StatusDot`, `Tooltip`, `InlineConfirmButton`
  - Verify: `npx vitest run`, визуальная проверка каждого компонента

### 1.6 Type safety

- [x] **1.6.1** Заменить string-based status на enum (landed in 8413328e)
  - Создать `type ToastType = "success" | "error" | "warning" | "info"` (уже есть)
  - Заменить `resolveStatusToastType()` (string matching по содержимому) на явную передачу типа из вызывающего кода
  - Заменить `draft.draftStorageWarning.startsWith("Storage full")` → `type StorageWarningLevel = "full" | "nearFull" | "cleared"` в `draftStore`
  - Verify: `npx tsc --noEmit` — 0 ошибок

- [x] **1.6.2** Убрать type assertions (landed in 8413328e)
  - `sampleProject as Parameters<typeof hydrateLoadedPayload>[0]` → типизировать `sample-project.json` через `satisfies`
  - Verify: `npx tsc --noEmit` — 0 ошибок

**Checkpoint Фаза 1:** `npx vitest run` — все тесты, `npx tsc --noEmit` — 0 ошибок, `App.tsx` < 120 строк, `ResultsPanel.tsx` < 150 строк, 5 Zustand stores работают.

---

## Фаза 2: UX Transformation (недели 4-6)

**Цель:** Time-to-First-Value с ~15 мин до ~3 мин. Cognitive load на results page -50%.  
**Метрика входа:** Design score 6.2/10  
**Метрика выхода:** Design score 7.8/10  

### 2.1 Onboarding и discoverability

- [ ] **2.1.1** Product tour (5 шагов) (partial: onboarding exists, but no 5-step tour flow)
  - Библиотека: `react-joyride` или кастомный spotlight на Floating UI (уже в зависимостях)
  - Шаги: (1) Hero — что это за инструмент, (2) Wizard — заполните контекст, (3) Metrics — настройте метрику, (4) Run Analysis — запустите расчёт, (5) Results — изучите результаты
  - Показывать: при первом визите ИЛИ по кнопке «?» в hero
  - Сохранять состояние: `localStorage` ключ `ab-test:tour-completed:v1`
  - Verify: первый визит → tour показывается, повторный визит → нет, кнопка «?» → tour заново

- [ ] **2.1.2** Contextual tooltips для статистических терминов (partial: `Tooltip` primitive exists, but no glossary/integration)
  - Создать `src/data/glossary.ts` — словарь из 15-20 терминов: MDE, Power, Alpha, CUPED, SRM, Bonferroni, Sequential Testing, Bayesian, Credibility Interval, Sample Size, Baseline Rate, Variance, Effect Size, Confidence Interval, P-value
  - Каждый термин: 1-2 предложения + формула (если применимо)
  - Компонент `<GlossaryTerm term="mde">` — обёртка со стилизованным `<Tooltip>`
  - Применить в: `WizardDraftStep` (labels полей), `ResultsPanel` секции (заголовки)
  - Verify: hover на «MDE» → tooltip с объяснением, не перекрывает другие элементы

- [x] **2.1.3** Template library (5 пресетов) (landed in 319820a0)
  - Создать `src/data/templates.ts`:
    - **E-commerce Checkout** — baseline_rate: 0.032, mde: 5%, daily_traffic: 50000
    - **SaaS Trial-to-Paid** — baseline_rate: 0.12, mde: 10%, daily_traffic: 5000
    - **Media Engagement** — metric_type: continuous, mean: 4.2, std_dev: 2.1, daily_traffic: 200000
    - **Search Relevance** — metric_type: continuous, mean: 0.35, std_dev: 0.15, daily_traffic: 100000
    - **Pricing Page** — baseline_rate: 0.045, mde: 8%, daily_traffic: 15000
  - UI: grid карточек в `EmptyState` + dropdown «Load template» в wizard header
  - Verify: клик на шаблон → форма заполняется, validation проходит, Run Analysis → корректные числа

### 2.2 Sidebar restructure

- [x] **2.2.1** Переработать `SidebarPanel` (994 строки → 3 подкомпонента) (implemented via tabs/filters/status sections; landed by 7eac8f59)
  - **Primary tab «Projects»** — список проектов + поиск (уже есть, оставить)
  - **Secondary tab «System»** — health, diagnostics, API token (свернуть в `SystemPanel.tsx`)
  - **Tertiary tab «Workspace»** — backup, import, status board (свернуть в `WorkspacePanel.tsx`)
  - History/Revisions/Comparison — перенести в модалку, открывается из карточки проекта
  - Verify: sidebar компактный, проекты видны без скролла, system info доступна в 1 клик

- [ ] **2.2.2** Responsive sidebar: drawer на mobile (partial: responsive single-column layout exists, but no overlay drawer)
  - На `<768px`: sidebar скрыт, кнопка-гамбургер открывает overlay drawer
  - Drawer: slide-in справа, backdrop с blur
  - Verify: на 375px экране sidebar открывается/закрывается, не перекрывает контент

### 2.3 Results progressive disclosure

- [x] **2.3.1** Summary card (3 hero-метрики) (implemented via results hero metric cards; landed in 5ea60181)
  - Вверху Results: три больших `MetricCard` — Sample Size, Duration, Power
  - Размер шрифта value: `--font-size-3xl`, остальные секции — свёрнуты
  - Verify: после Run Analysis первое что видит пользователь — 3 ключевые цифры

- [x] **2.3.2** Accordion для secondary секций (landed in 5ea60181)
  - Все остальные секции (warnings, design, metrics, risks, AI) — в `<Accordion>` по умолчанию свёрнуты
  - Warnings: развёрнут по умолчанию, если есть high severity
  - Verify: только summary видна, клик раскрывает секцию, анимация 200ms

- [ ] **2.3.3** Deep dive: модальное окно для sensitivity/observed results (partial: sections are disclosed inline via accordion, not modal)
  - Sensitivity table и Observed Results — сложные интерактивные формы
  - Перенести в modal (full-width, slide-up) — не загромождать основной view
  - Кнопки «Run sensitivity analysis» и «Analyze observed results» в summary
  - Verify: modal открывается, форма работает, результаты отображаются внутри modal

### 2.4 Visual hierarchy и micro-interactions

- [x] **2.4.1** Дифференцировать визуальный вес карточек (landed in 5ea60181)
  - Hero metrics: `box-shadow: var(--shadow-lg)`, `padding: var(--space-6)`, border-left 3px accent
  - Secondary cards: `box-shadow: var(--shadow-sm)`, `padding: var(--space-4)`
  - Tertiary (collapsed accordion): no shadow, `border: 1px solid var(--color-border-soft)`
  - Verify: визуальная иерархия очевидна — взгляд сначала на hero, потом secondary

- [ ] **2.4.2** Sparklines в MetricCard
  - Добавить optional prop `trend?: number[]` в `MetricCard`
  - Рендер: SVG sparkline (polyline) 60x20px, цвет по тону (зелёный/красный)
  - Применить: для MetricCard в comparison view — показывать тренд sample size по ревизиям
  - Verify: sparkline рендерится, responsive, не ломает layout

- [ ] **2.4.3** Animated number transitions
  - При появлении hero-метрик — count-up анимация (0 → target за 600ms, easeOut)
  - Реализация: `requestAnimationFrame` без библиотек
  - Respect `prefers-reduced-motion`
  - Verify: числа анимируются, с `reduce-motion` — мгновенно

### 2.5 Responsive design

- [ ] **2.5.1** Четыре breakpoint'а вместо одного (partial: responsive grid/autofit layout landed, but not 4 explicit breakpoints)
  - `480px` — phone portrait (1 column, компактный spacing)
  - `768px` — phone landscape / small tablet (sidebar → drawer)
  - `1024px` — tablet (grid 1fr, sidebar под wizard)
  - `1280px` — desktop (текущий grid `1.25fr 0.75fr`)
  - Verify: проверить на 375px, 768px, 1024px, 1440px — layout корректный

- [ ] **2.5.2** Touch targets минимум 44x44px
  - `.btn` → `min-height: 44px`, `padding: 12px 20px`
  - `.theme-toggle-button` → `min-height: 44px`
  - Все interactive элементы в sidebar
  - Verify: Lighthouse Accessibility score ≥ 90

### 2.6 Font и performance

- [ ] **2.6.1** Self-host Inter и JetBrains Mono
  - Скачать Inter Variable (woff2, ~100KB) и JetBrains Mono (woff2, weights 400-600, ~80KB)
  - Положить в `src/assets/fonts/`
  - `@font-face` в `tokens.css` с `font-display: swap`
  - Убрать `<link>` на Google Fonts из `index.html`
  - Verify: `npm run build`, fonts в bundle, нет запросов к fonts.googleapis.com, FOIT отсутствует

- [x] **2.6.2** Lazy load Recharts (implemented via lazy `PowerCurveChart`; landed in 5ea60181)
  - `PowerCurveChart` уже lazy (строка 27 ResultsPanel) — распространить на `ForestPlot`, `SensitivityTable`
  - Verify: initial bundle не содержит recharts, chart загружается при открытии секции

### 2.7 Accessibility

- [x] **2.7.1** WCAG AA contrast audit (landed in 9882d079)
  - Проверить все пары text/bg в light и dark mode через axe-core
  - Критичные: `--color-text-secondary` (#64748b) на `--color-bg` (#f8fafc) — ratio 4.48:1 (AA pass для large text, fail для small)
  - Исправить: `--color-text-secondary: #546478` (ratio ≥ 4.5:1)
  - Verify: `npx axe-core` или Lighthouse Accessibility ≥ 95

**Checkpoint Фаза 2:** Lighthouse Performance ≥ 85, Accessibility ≥ 95, SUS score ≥ 75 (user testing с 3 участниками), sidebar компактный, results readable.

---

## Фаза 3: Commercial Readiness (недели 7-10)

**Цель:** Первый платящий пользователь. Продукт работает как multi-user SaaS.  
**Метрика входа:** Product score 6.8/10  
**Метрика выхода:** Product score 8.0/10  

### 3.1 Backend: PostgreSQL option

- [ ] **3.1.1** Абстракция storage layer
  - Создать `app/backend/app/storage/base.py` — abstract base class `StorageBackend`
  - Методы: `save_project`, `load_project`, `list_projects`, `archive_project`, `restore_project`, `save_analysis_run`, `load_analysis_history`, `export_workspace`, `import_workspace`
  - Verify: интерфейс определён, mypy clean

- [ ] **3.1.2** Перенести SQLite logic в `app/backend/app/storage/sqlite_backend.py`
  - Вынести из `repository.py` (1201 строк) в реализацию `StorageBackend`
  - `repository.py` становится thin facade, делегирует в выбранный backend
  - Verify: все 17 backend-тестов проходят без изменений

- [ ] **3.1.3** PostgreSQL backend: `app/backend/app/storage/postgres_backend.py`
  - Зависимость: `asyncpg` или `psycopg[binary]`
  - Конфигурация: `AB_DB_ENGINE=postgres`, `AB_DATABASE_URL=postgresql://...`
  - Verify: `docker-compose -f docker-compose.pg.yml up` — все эндпоинты работают с Postgres

- [ ] **3.1.4** Database migrations с Alembic
  - `alembic init app/backend/migrations`
  - Initial migration из текущей SQLite-схемы
  - `alembic upgrade head` в Docker entrypoint
  - Verify: `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` — без ошибок

### 3.2 User authentication

- [ ] **3.2.1** Auth provider: Clerk или Auth0
  - Критерии: OAuth2/OIDC, social logins (Google, GitHub), free tier ≥ 5000 MAU
  - Добавить: `AB_AUTH_PROVIDER=clerk`, `AB_AUTH_SECRET_KEY`, `AB_AUTH_PUBLISHABLE_KEY`
  - Verify: env vars читаются, fallback на текущий token-auth при отсутствии

- [ ] **3.2.2** Backend auth middleware (partial: dual API-token auth and rate limiting exist, but no JWT/user context)
  - JWT verification middleware для FastAPI
  - Извлечение `user_id` из токена, привязка к request context
  - Backward compatible: если `AB_AUTH_PROVIDER` не задан — работает текущий API token auth
  - Verify: запрос с валидным JWT → 200, без токена → 401, expired → 401

- [ ] **3.2.3** Multi-tenant data isolation
  - Добавить `user_id TEXT NOT NULL` и `workspace_id TEXT NOT NULL` в таблицу `projects`
  - Все queries фильтруются по `user_id` / `workspace_id`
  - Migration: существующие проекты получают `user_id = "legacy"`, `workspace_id = "default"`
  - Verify: user A не видит проекты user B

- [ ] **3.2.4** Frontend auth flow (partial: browser-session API token UI exists, but no login/session flow)
  - Login page: `/login` с OAuth buttons
  - Protected routes: redirect на login если нет session
  - User menu: avatar + email + logout
  - Verify: Google login → redirect в app → проекты пользователя видны

### 3.3 Team workspaces

- [ ] **3.3.1** Workspace model
  - Таблица `workspaces`: id, name, owner_id, created_at
  - Таблица `workspace_members`: workspace_id, user_id, role (owner/editor/viewer)
  - Verify: CRUD для workspaces, добавление/удаление members

- [ ] **3.3.2** Role-based access control
  - **Owner:** всё
  - **Editor:** CRUD проектов, запуск анализа, экспорт
  - **Viewer:** чтение проектов и результатов, без мутаций
  - Verify: viewer не может Save/Archive/Run Analysis (403)

- [ ] **3.3.3** Project sharing
  - Share link: `/workspace/{id}/project/{id}` — доступ для members
  - Invite по email — отправка через Clerk/Auth0 invite API
  - Verify: invite → accept → проект доступен в workspace нового пользователя

### 3.4 Billing (Stripe)

- [ ] **3.4.1** Pricing model
  - **Free:** 3 проекта, 1 пользователь, no exports, no LLM advice
  - **Pro ($29/mo):** unlimited проекты, 1 пользователь, all features
  - **Team ($19/user/mo, min 3):** unlimited проекты, workspace, roles, priority support
  - Verify: pricing page отображает 3 тарифа

- [ ] **3.4.2** Stripe integration
  - `stripe` SDK в backend, webhook handler для `checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`
  - Frontend: Stripe Checkout redirect (не embedded form — проще, PCI compliant)
  - Verify: тестовый Stripe checkout → подписка активна → features разблокированы

- [ ] **3.4.3** Feature gating
  - Middleware: проверка `subscription.plan` перед мутациями
  - Free → enforce limits (3 projects max, block export, block LLM)
  - Verify: Free user → 4-й проект → 403 с сообщением «Upgrade to Pro»

### 3.5 Landing page

- [ ] **3.5.1** Отдельная landing page (React или Astro)
  - Hero: value proposition + CTA (Start Free)
  - Features: 6 карточек (Sample Size Calculator, Bayesian, Sequential, CUPED, SRM, Self-hosted)
  - Comparison table: vs Statsig, GrowthBook, Eppo
  - Pricing section
  - Demo video/GIF (screen recording)
  - Verify: Lighthouse Performance ≥ 90, responsive, CTA работает

### 3.6 Product analytics

- [ ] **3.6.1** PostHog integration
  - Frontend: `posthog-js`, track events: `analysis_run`, `project_saved`, `export_report`, `template_loaded`, `wizard_step_completed`
  - Backend: server-side events: `analysis_duration_ms`, `llm_advice_requested`, `workspace_exported`
  - Verify: events видны в PostHog dashboard, no PII в events

**Checkpoint Фаза 3:** Первый пользователь может: зарегистрироваться → создать workspace → пригласить коллегу → создать проект → Run Analysis → Export → оплатить Pro.

---

## Фаза 4: Growth & Differentiation (недели 11-12)

**Цель:** Интеграции и i18n для расширения TAM.  
**Метрика входа:** Product score 8.0/10  
**Метрика выхода:** Product score 8.5/10  

### 4.1 Integrations

- [ ] **4.1.1** Google Analytics 4 connector
  - Backend: `app/backend/app/integrations/ga4.py`
  - OAuth2 flow для GA4 Data API
  - Pull: event counts, conversion rates по date range
  - UI: «Import from GA4» в observed results form
  - Verify: подключить тестовый GA4 property → данные подтягиваются

- [ ] **4.1.2** BigQuery connector
  - Backend: `app/backend/app/integrations/bigquery.py`
  - Service account auth
  - SQL query builder для experiment results tables
  - UI: SQL editor с подсказками, preview результатов
  - Verify: select из тестовой таблицы → данные в observed results

- [ ] **4.1.3** Webhook API для push результатов (partial: generic `/api/v1/results` endpoint exists, but no project-scoped push webhook)
  - Endpoint: `POST /api/v1/projects/{id}/results`
  - Auth: project-scoped API key
  - Payload: `{ control: { users, conversions }, treatment: { users, conversions } }`
  - Auto-run analysis при получении данных
  - Verify: `curl -X POST .../results` → analysis run создаётся автоматически

### 4.2 i18n

- [ ] **4.2.1** i18n framework: `react-i18next` (partial: deps, `en.json`, and isolated i18n test exist, but app-wide integration is incomplete)
  - Уже есть `src/i18n/index.ts` и `en.json` — расширить
  - Все строки из компонентов → в translation keys
  - Backend: заголовок `Accept-Language` → язык отчёта
  - Verify: переключение языка в UI, все строки переведены

- [ ] **4.2.2** Русский перевод (`ru.json`)
  - Все UI-строки + glossary tooltips + error messages
  - Verify: переключить на RU → все элементы на русском, layout не ломается

- [ ] **4.2.3** Немецкий перевод (`de.json`)
  - Verify: аналогично RU

### 4.3 Advanced visualizations

- [x] **4.3.1** Bayesian posterior plot (landed in 87147d35)
  - Компонент: `PosteriorPlot.tsx`
  - Отображает: prior distribution, posterior distribution, credibility interval (shaded area)
  - Библиотека: Recharts (уже в зависимостях)
  - Verify: при Bayesian mode → posterior plot рендерится с корректными данными

- [x] **4.3.2** Sequential boundary chart (landed in 87147d35)
  - Компонент: `SequentialBoundaryChart.tsx`
  - Отображает: upper/lower O'Brien-Fleming boundaries по interim looks
  - Verify: при sequential mode → boundary chart с 2-10 looks

### 4.4 Developer API

- [ ] **4.4.1** Public API документация (partial: `/docs`/`/redoc`, token auth, and global rate limits exist, but no API-key management or per-key limits)
  - OpenAPI spec → Redoc/Swagger UI на `/docs`
  - API keys management в user settings
  - Rate limits per API key
  - Verify: `/docs` показывает все endpoints, API key auth работает

- [ ] **4.4.2** SDK generation
  - `openapi-generator` → TypeScript и Python SDK
  - Publish: npm + PyPI
  - Verify: `pip install ab-test-designer && python -c "from ab_test_designer import Client"` работает

**Checkpoint Фаза 4:** 2+ интеграции работают, 3 языка, Bayesian/Sequential визуализации, публичный API с SDK.

---

## Матрица зависимостей

```
1.1 (тесты) ──────→ 1.2 (Zustand) ──────→ 1.3 (Results split) → 2.x (UX)
                          │                       │
                          ↓                       ↓
                     1.4 (ErrorBoundary)    1.5 (CSS unify)
                                                  │
                                                  ↓
                                            1.6 (type safety)
                                                  │
2.1-2.7 (UX) ─────────────────────────────────────┘
     │
     ↓
3.1 (Postgres) ──→ 3.2 (Auth) ──→ 3.3 (Teams) ──→ 3.4 (Billing) ──→ 3.5 (Landing)
                                                         │
                                                         ↓
                                                   3.6 (Analytics)
                                                         │
4.1 (Integrations) ←────────────────────────────────────┘
4.2 (i18n)          ← параллельно с 4.1
4.3 (Visualizations) ← параллельно с 4.1
4.4 (API/SDK)       ← после 4.1
```

## Ресурсы и сроки

| Фаза | Недели | FTE | Фокус |
|-------|--------|-----|-------|
| 1. Foundation Fix | 1-3 | 1 fullstack | Frontend architecture |
| 2. UX Transformation | 4-6 | 1 frontend + 0.5 designer | Design + UX |
| 3. Commercial Readiness | 7-10 | 1 fullstack + 0.5 backend | Auth, billing, Postgres |
| 4. Growth | 11-12 | 1 fullstack | Integrations, i18n |
| **Итого** | **12** | **~1.5 FTE avg** | |

## Критерии успеха

| Метрика | Сейчас | После Ф1 | После Ф2 | После Ф3 | После Ф4 |
|---------|--------|----------|----------|----------|----------|
| Product score | 6.8 | 6.8 | 7.5 | 8.0 | 8.5 |
| Design score | 6.2 | 6.2 | 7.8 | 7.8 | 8.2 |
| Code score | 7.4 | 8.2 | 8.4 | 8.8 | 9.0 |
| Frontend arch | 4.0 | 7.0 | 7.5 | 7.5 | 8.0 |
| Frontend tests | 8 files | 15 files | 18 files | 20 files | 22 files |
| Lighthouse Perf | ~70 | ~75 | ≥85 | ≥85 | ≥90 |
| Lighthouse A11y | ~80 | ~85 | ≥95 | ≥95 | ≥95 |
| Users | 1 | 1 | 1 (beta) | 10+ | 30+ |
| MRR | $0 | $0 | $0 | >$0 | >$500 |

---

*BCG Technology & Digital Practice*  
*Plan version 1.0 — 12 апреля 2026*
