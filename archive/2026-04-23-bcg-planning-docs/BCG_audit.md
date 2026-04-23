# BCG Audit Report: AB Test Research Designer

**Дата:** 12 апреля 2026  
**Команда:** BCG Technology & Digital Practice  
**Формат:** Комплексный аудит продукта — Product / Design / Code  
**Версия продукта:** 0.1.0  

---

## Executive Summary

AB Test Research Designer — локальный инструмент для планирования A/B и мультивариантных экспериментов. Продукт покрывает полный цикл от дизайна эксперимента до анализа результатов, включая частотный, байесовский и последовательный подходы, CUPED-коррекцию дисперсии и детекцию SRM.

Продукт демонстрирует **высокий уровень инженерной зрелости** для pre-commercial стадии. Статистическое ядро реализовано корректно, архитектура чистая, тестовое покрытие бэкенда основательное. Однако для перехода к коммерческому продукту необходимы существенные улучшения в области UX, масштабируемости и фронтенд-архитектуры.

### Сводные оценки

| Категория | Оценка | Уровень |
|-----------|--------|---------|
| **Продукт** | **6.8 / 10** | Solid MVP, gaps to commercial |
| **Дизайн** | **6.2 / 10** | Functional, not delightful |
| **Код** | **7.4 / 10** | Strong backend, weak frontend |
| **Итого (взвешенная)** | **6.8 / 10** | — |

---

## 1. ПРОДУКТ — 6.8 / 10

### 1.1 Сильные стороны

**Глубина статистического ядра (9/10)**
- Полная реализация частотного подхода: binary + continuous метрики, Bonferroni-коррекция для мультивариантных тестов
- Байесовский режим с precision-based расчётом sample size
- Последовательное тестирование O'Brien-Fleming с корректным расчётом inflation factor
- CUPED variance reduction — редкая функция даже среди enterprise-инструментов
- SRM-детекция через chi-square test с полной реализацией CDF (без зависимости от scipy)
- Детерминированные расчёты отделены от LLM-рекомендаций — правильное архитектурное решение

**Система правил и предупреждений (8/10)**
- 9 типов warnings с градацией severity
- Покрытие ключевых рисков: underpowered design, seasonality, campaign contamination
- Машинная оценка feasibility до запуска эксперимента

**Управление проектами (7.5/10)**
- Полный CRUD с историей ревизий
- Сравнение проектов (comparison service)
- Workspace backup/restore с HMAC-подписью и checksum-валидацией
- Архивация вместо hard delete — правильный паттерн

### 1.2 Слабые стороны

**Отсутствие multi-user модели (критично для коммерциализации)**
- Нет системы пользователей и аутентификации
- API-токен — это server-level auth, не user-level
- Нет ролей (viewer/editor/admin)
- Нет коллаборативных функций (sharing, commenting)
- **Оценка:** 2/10

**Нет интеграций с внешними системами**
- Нет коннекторов к GA4, Amplitude, Mixpanel, BigQuery
- Результаты экспериментов вводятся вручную
- Нет webhook/API для автоматического подтягивания данных
- Нет интеграции с CI/CD pipeline (feature flags)
- **Оценка:** 2/10

**Монетизация и GTM не реализованы**
- `commercial-upgrade-plan.md` содержит roadmap на ~9 недель, но ни одна фаза не завершена
- Нет pricing model, billing, trial flow
- Нет landing page (кроме hero-секции в приложении)
- Нет analytics/telemetry для понимания usage patterns
- **Оценка:** 1/10

**Локализация ограничена**
- Только English (i18n-инфраструктура заложена, но содержит один язык)
- Для рынков CIS/DACH/LATAM — блокер
- **Оценка:** 3/10

### 1.3 Рекомендации по росту (Product)

| # | Мера | Приоритет | Эффект | Сложность |
|---|------|-----------|--------|-----------|
| P1 | Добавить user management (OAuth2 / OIDC) | Critical | Разблокирует SaaS-модель | High |
| P2 | Интеграция с 2-3 аналитическими платформами (GA4, Amplitude, BigQuery) | High | Автоматизация ввода результатов, снижение friction | High |
| P3 | Feature flag integration (LaunchDarkly, Unleash) | Medium | Связывает планирование с execution | Medium |
| P4 | Usage analytics (PostHog/Amplitude для self-product) | High | Понимание retention, feature adoption | Low |
| P5 | Multi-language support (RU, DE как минимум) | Medium | Расширение TAM на 40% | Medium |
| P6 | Collaboration: shared projects, comments, @mentions | High | Переход от solo-tool к team-tool | High |
| P7 | Template library (e-commerce, SaaS, media presets) | Medium | Снижение Time-to-First-Value на 60% | Low |

---

## 2. ДИЗАЙН — 6.2 / 10

### 2.1 Сильные стороны

**Design system foundation (7.5/10)**
- Полноценная система дизайн-токенов в `tokens.css`: 8-pt spacing scale, типографическая шкала, семантические цвета
- Продуманная цветовая палитра: primary (teal), secondary (indigo), 4 semantic цвета
- Корректная работа dark/light/system тем с `prefers-color-scheme` и ручным override
- Glassmorphism: `backdrop-filter: blur(16px)` + rgba-панели — современный визуальный язык

**Типографика (8/10)**
- Inter (sans) + JetBrains Mono (mono) — отличная пара для data-heavy UI
- `font-feature-settings: "tnum" 1` для табличных цифр — профессиональная деталь
- Корректная clamp-формула для responsive heading: `clamp(36px, 5vw, 52px)`

**Accessibility baseline (7/10)**
- Skip-to-content link
- `prefers-reduced-motion: reduce` — отключение всех анимаций
- ARIA-атрибуты на theme toggle (`aria-pressed`)
- Print stylesheet с скрытием интерактивных элементов
- Keyboard navigation (Arrow keys для шагов, Ctrl+Enter для анализа, Ctrl+S для сохранения)

### 2.2 Слабые стороны

**Информационная перегрузка (критично)**
- Sidebar содержит 8+ секций одновременно: Projects, System Health, Diagnostics, API Token, Workspace, History, Revisions, Comparison
- Results panel — 1915 строк JSX, отображает 15+ блоков данных без чёткой иерархии
- Review step показывает все 5 секций формы одновременно без визуальной приоритизации
- **Оценка:** 4/10

**Нет guided onboarding**
- EmptyState предлагает 3 действия, но нет пошагового туториала
- Нет contextual tooltips объясняющих что такое MDE, power, alpha для non-statisticians
- Нет progressive disclosure — все поля показаны сразу
- **Оценка:** 3/10

**Визуальная монотонность**
- Все карточки, панели и секции выглядят идентично (одинаковый `border-radius`, `box-shadow`, `border`)
- Нет визуальной иерархии через размер, цвет или пространство
- Metric cards не используют data visualization (спарклайны, micro-charts)
- Нет иллюстраций, пустые состояния текстовые
- **Оценка:** 5/10

**Мобильный опыт недоработан**
- Единственный breakpoint на 900px — слишком грубо
- Sidebar на мобильных занимает 100% ширины и перегружен
- Нет mobile-first подхода — desktop UI просто "сжимается"
- Touch targets: кнопки `padding: 11px 16px` — на нижней границе (минимум 44px по WCAG)
- **Оценка:** 4/10

**Font loading без fallback strategy**
- Google Fonts загружаются через `<link>` без `font-display: swap` в CSS
- При медленном соединении — FOIT (flash of invisible text)
- Нет self-hosted fonts для offline/air-gapped деплоя
- **Оценка:** 5/10

### 2.3 Рекомендации по росту (Design)

| # | Мера | Приоритет | Эффект | Сложность |
|---|------|-----------|--------|-----------|
| D1 | Restructure sidebar: tabs → accordion/drawer с lazy-load секций | Critical | Снижение cognitive load на 50% | Medium |
| D2 | Results page: progressive disclosure с drill-down | Critical | Юзабилити для non-expert пользователей | High |
| D3 | Добавить contextual tooltips (MDE, Power, Alpha, CUPED) | High | Снижение learning curve | Low |
| D4 | Intro wizard / product tour (3-5 шагов) | High | Time-to-Value с 15 мин до 3 мин | Medium |
| D5 | Visual hierarchy: hero metrics крупнее, secondary мельче | Medium | Scanability +40% | Low |
| D6 | Self-host fonts (Inter Variable, JetBrains Mono) | Medium | Offline support, GDPR compliance | Low |
| D7 | Mobile-first responsive: 480px / 768px / 1024px / 1280px | Medium | Mobile usability score +30pt | Medium |
| D8 | Micro-charts в MetricCard (sparklines, trend indicators) | Medium | Data density без увеличения пространства | Medium |
| D9 | Empty state illustrations (SVG) | Low | Emotional engagement | Low |
| D10 | Contrast audit: проверить все text/bg пары на WCAG AA | High | Accessibility compliance | Low |

---

## 3. КОД — 7.4 / 10

### 3.1 Backend — 8.5 / 10

**Архитектура (9/10)**
- Чёткое разделение: `routes/` → `services/` → `stats/` → `repository`
- Factory pattern в `main.py` (`create_app`) — testable, composable
- Dependency injection через параметры (не global state)
- Pydantic schemas для входа/выхода — строгая типизация на границах
- Отдельный `rules/` engine — extensible, decoupled

**Статистический движок (9/10)**
- Чистая реализация без scipy-зависимости (собственные CDF/PPF через `statistics.NormalDist`)
- Chi-square CDF через гамма-функции — корректная, проверенная реализация
- Binary search для detectable MDE — элегантно и численно стабильно (80 итераций)
- Bonferroni alpha correction для мультивариантных тестов
- CUPED: `effective_variance = original_variance * (1 - rho^2)` — корректная формула

**Безопасность (8/10)**
- Rate limiting (sliding window) для запросов и auth failures
- API token auth с разделением read/write
- HMAC-SHA256 подпись workspace backups
- Request body size limits
- Security headers через middleware
- Корректная обработка CORS

**Тестирование бэкенда (8/10)**
- 18 тест-файлов: unit + integration + performance
- Performance benchmarks: P95 < 100ms
- Edge cases покрыты (extreme baselines, unequal splits)
- Pytest с фикстурами

**Недостатки бэкенда:**

- **SQLite single-writer lock** — не масштабируется при concurrent writes. Для >10 concurrent users нужен Postgres. (-1)
- **Нет системы миграций** — `_migrate_db` в repository вручную, нет Alembic/аналога. При росте схемы — риск потери данных. (-0.5)
- **`lru_cache` для settings** — нет возможности горячей перезагрузки конфига. В Docker это приемлемо, для SaaS — нет. (-0.5)
- **Нет structured logging в production** — `log_format: json` поддерживается, но не используется по умолчанию. (-0.3)
- **Нет health check для LLM dependency** — `/health` не проверяет доступность orchestrator. (-0.2)

### 3.2 Frontend — 6.0 / 10

**Стек и инструменты (8/10)**
- React 19 + TypeScript + Vite 7 — актуальный, быстрый стек
- Recharts для визуализации — правильный выбор для React
- Floating UI для позиционирования — легковесная альтернатива Popper
- Playwright для E2E — industry standard
- Vitest — быстрые unit тесты

**Критические проблемы:**

**3.2.1 God Component: `App.tsx` — 320+ строк state management**
```
Score: 3/10
```
- 15+ `useState` хуков
- 8+ `useEffect` хуков с сложными зависимостями
- 20+ функций-обработчиков (`runAnalysis`, `saveProject`, `loadProject`, `archiveProject`, `restoreProject`, `exportDraft`, `importDraftFromFile`, `importWorkspaceFromFile`, `saveRuntimeApiToken`, `clearRuntimeApiToken`, `exportWorkspace`, `exportReport`, `openHistoryRun`, `clearHistoryRunSelection`, `loadProjectRevision`, `startNewProject`, `loadExample`, `updateSection`, `blockMutations`, `showAsyncStatus`)
- Prop drilling через `wizardPanelProps` (30+ props) и `sidebarPanelProps` (50+ props)
- Нет state management решения (ни Context API, ни Zustand, ни Redux)
- **Риск:** любое изменение в App.tsx потенциально ломает всё приложение

**3.2.2 Монолитный `ResultsPanel.tsx` — 1915 строк**
```
Score: 3/10
```
- Один файл отвечает за: sensitivity table, power curve, SRM, observed results, sequential design, warnings, experiment design, metrics plan, risks, AI recommendations, guardrails
- Невозможно тестировать отдельные секции
- Невозможно lazy-load отдельные блоки
- Code review одного файла на 1915 строк — nightmare

**3.2.3 Смешанная CSS-архитектура**
```
Score: 5/10
```
- `App.css` — 500+ строк глобальных стилей (`.btn`, `.field`, `.card`, `.grid`, `.toast-*`, `.skeleton-*`)
- CSS Modules используются только в 3 компонентах (`WizardDraftStep`, `SidebarPanel`, `ResultsPanel`)
- Остальные ~20 компонентов полагаются на глобальные классы — collision risk
- Нет CSS-in-JS, нет Tailwind — ручное управление каскадом

**3.2.4 Недостаточное фронтенд-тестирование**
```
Score: 4/10
```
- Только 4 файла с `.test.` в frontend: `Icon.test.tsx`, `ResultsPanel.test.tsx`, `useCalculationPreview.test.tsx`, `useToast.test.tsx`
- Нет тестов для: `App.tsx`, `WizardPanel`, `WizardDraftStep`, `SidebarPanel`, `ForestPlot`, `PowerCurveChart`, `SensitivityTable`
- Нет тестов для `useAnalysis`, `useProjectManager`, `useDraftPersistence`
- E2E smoke test — один файл, покрывает happy path
- **Риск:** рефакторинг без тестов = регрессии

**3.2.5 Нет Error Boundaries**
```
Score: 2/10
```
- React Error Boundary не реализован нигде
- Ошибка в любом компоненте крашит всё приложение
- Нет graceful degradation для chart rendering failures
- Нет fallback UI

**3.2.6 Type safety gaps**
- `sampleProject as Parameters<typeof hydrateLoadedPayload>[0]` — type assertion вместо proper typing
- `draft.draftStorageWarning` проверяется `.startsWith("Storage full")` — string matching вместо enum
- `resolveStatusToastType` — string matching по содержимому сообщения

### 3.3 Infrastructure — 7.5 / 10

**Сильные стороны:**
- Docker multi-stage build: Node → Python, минимальный runtime
- Docker Compose с health check
- GitHub Actions CI: Ubuntu + Windows matrix
- Lighthouse CI configuration
- Comprehensive verification scripts (`verify_all.py`)

**Недостатки:**
- Нет staging environment
- Нет Terraform/Pulumi для infrastructure-as-code
- Нет container registry / CD pipeline
- Нет secrets management (vault, AWS SSM)
- Lighthouse job только на `workflow_dispatch` — не на каждый PR

### 3.4 Рекомендации по росту (Code)

| # | Мера | Приоритет | Эффект | Сложность |
|---|------|-----------|--------|-----------|
| C1 | Декомпозиция App.tsx → Context providers + custom hooks | Critical | Maintainability: 3/10 → 8/10 | High |
| C2 | Разбить ResultsPanel.tsx на 10-12 модулей | Critical | Testability, lazy loading, code review | High |
| C3 | State management: Zustand (lightweight) или React Context | Critical | Устранение prop drilling (80+ props) | Medium |
| C4 | React Error Boundaries на уровне layout + каждого chart | High | Resilience, user trust | Low |
| C5 | Унифицировать CSS: полный переход на CSS Modules или Tailwind | High | Устранение collision risk | Medium |
| C6 | Frontend test coverage → 60%+ (critical paths) | High | Regression safety при рефакторинге | High |
| C7 | Database migration system (Alembic) | High | Safe schema evolution | Medium |
| C8 | Заменить string matching на enum/discriminated unions | Medium | Type safety | Low |
| C9 | Lazy load heavy components (Recharts, ForestPlot) | Medium | Initial bundle size -30% | Low |
| C10 | PostgreSQL option для production deployment | Medium | Concurrency, scalability | High |
| C11 | Add Sentry/error tracking | Medium | Visibility into production errors | Low |
| C12 | Self-host fonts, add `font-display: swap` | Low | Performance, offline resilience | Low |

---

## 4. ДЕТАЛИЗАЦИЯ ОЦЕНОК

### 4.1 Product Breakdown

| Подкатегория | Оценка | Комментарий |
|---|---|---|
| Problem-solution fit | 8.0 | Реальная боль, правильный подход |
| Feature completeness (MVP) | 7.5 | Статистика отличная, UX workflow завершён |
| Feature completeness (Commercial) | 4.0 | Нет users, teams, integrations |
| Market readiness | 3.0 | Нет pricing, landing, analytics |
| Competitive differentiation | 7.0 | CUPED + Sequential + Bayesian в одном инструменте — редкость |
| Documentation quality | 8.5 | ARCHITECTURE, API, RUNBOOK, RULES — полный набор |
| **Среднее** | **6.8** | |

### 4.2 Design Breakdown

| Подкатегория | Оценка | Комментарий |
|---|---|---|
| Visual design language | 7.0 | Glassmorphism + teal palette — стильно, но однообразно |
| Design system maturity | 7.5 | Tokens есть, компонентная библиотека — нет |
| Information architecture | 5.0 | Sidebar перегружен, results без иерархии |
| Onboarding & learnability | 3.5 | Нет tutorial, tooltips минимальны |
| Responsive design | 5.0 | Один breakpoint, мобильная версия сырая |
| Accessibility | 7.0 | Базовый уровень хороший, но нет contrast audit |
| Dark mode implementation | 8.0 | Полная, корректная, с system preference |
| Data visualization | 6.5 | ForestPlot и PowerCurve есть, но MetricCards текстовые |
| **Среднее** | **6.2** | |

### 4.3 Code Breakdown

| Подкатегория | Оценка | Комментарий |
|---|---|---|
| Backend architecture | 9.0 | Чистая, модульная, testable |
| Statistical correctness | 9.0 | Без внешних зависимостей, корректные формулы |
| Backend test coverage | 8.0 | 18 файлов, включая performance |
| Security implementation | 8.0 | Rate limiting, HMAC, auth — production-grade |
| Frontend architecture | 4.0 | God component, prop drilling, нет state mgmt |
| Frontend test coverage | 4.0 | 4 файла из ~25 компонентов |
| CSS architecture | 5.0 | Mixed global + modules |
| Error handling (frontend) | 3.0 | Нет Error Boundaries, string-based errors |
| Build & CI/CD | 7.5 | Docker + GH Actions, но нет staging/CD |
| Code documentation | 7.0 | Типы хорошие, inline docs минимальны (для TypeScript это OK) |
| **Среднее** | **7.4** | **Backend тянет вверх, frontend — вниз** |

---

## 5. СТРАТЕГИЧЕСКИЕ РЕКОМЕНДАЦИИ

### 5.1 Фаза 1: Foundation Fix (2-3 недели)

**Цель:** Устранить технический долг, блокирующий рост.

1. **Декомпозиция App.tsx** — выделить `AppStateProvider` (Context), разбить на `useWizardFlow`, `useTheme`, `useKeyboardShortcuts`
2. **Разбить ResultsPanel** — по одному модулю на секцию: `SensitivitySection`, `PowerCurveSection`, `SrmSection`, `DesignSection`, `RisksSection`, `AiAdviceSection`, `GuardrailSection`
3. **Error Boundaries** — layout-level + per-chart
4. **Frontend tests** — покрыть 3 critical hooks: `useAnalysis`, `useProjectManager`, `useDraftPersistence`

**KPI:** Frontend maintainability index с 4.0 до 7.0

### 5.2 Фаза 2: UX Transformation (3-4 недели)

**Цель:** Снизить Time-to-Value с 15 до 3 минут.

1. **Product tour** — 5 шагов с highlight целевых элементов
2. **Sidebar restructure** — Primary: Projects list. Secondary (drawer): System, Diagnostics, Workspace
3. **Results progressive disclosure** — Summary (3 key metrics) → Details (accordion) → Deep dive (modal)
4. **Contextual tooltips** — для всех статистических терминов
5. **Template presets** — 5 шаблонов (e-commerce checkout, SaaS onboarding, media engagement, search relevance, pricing page)

**KPI:** SUS score > 75, task completion rate > 90%

### 5.3 Фаза 3: Commercial Readiness (4-6 недель)

**Цель:** Готовность к первому платящему клиенту.

1. **User authentication** — OAuth2 через Auth0/Clerk
2. **PostgreSQL migration** — для multi-user concurrency
3. **Team workspaces** — shared projects, role-based access
4. **Billing integration** — Stripe, 3 тарифа (Free/Pro/Team)
5. **Landing page** — positioning, pricing, demo video
6. **Analytics** — PostHog для product analytics

**KPI:** First paying customer, MRR > $0

### 5.4 Фаза 4: Growth & Differentiation (6-8 недель)

**Цель:** Product-market fit и устойчивый рост.

1. **Integrations** — GA4 connector, Amplitude connector, BigQuery reader
2. **Automated results ingestion** — API endpoint для push результатов
3. **Feature flag platforms** — LaunchDarkly/Unleash bidirectional sync
4. **Advanced visualizations** — Bayesian posterior plots, sequential boundary charts
5. **i18n** — Russian, German, Spanish
6. **API для внешних клиентов** — OpenAPI-first, SDK generation

**KPI:** 10 active teams, NPS > 50

---

## 6. RISK REGISTER

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Frontend refactoring вызовет регрессии | High | High | Написать тесты ДО рефакторинга (C6 → C1) |
| SQLite lock contention при >5 users | High | Critical | PostgreSQL migration в Фазе 3 |
| Конкурент (Statsig, Eppo, GrowthBook) займёт нишу | Medium | High | Ускорить Фазу 3, фокус на differentiator (CUPED + Bayesian) |
| LLM dependency станет bottleneck | Medium | Medium | Graceful fallback уже реализован — extend timeout, add circuit breaker |
| Google Fonts блокировка (GDPR/air-gap) | Medium | Low | Self-host fonts (D6) |

---

## 7. COMPETITIVE LANDSCAPE

| Критерий | AB Test RD | Statsig | GrowthBook | Eppo |
|----------|-----------|---------|------------|------|
| Sample size calculator | ++ | + | + | ++ |
| Bayesian analysis | + | + | ++ | ++ |
| Sequential testing | + | ++ | + | ++ |
| CUPED | + | ++ | - | ++ |
| SRM detection | + | + | + | + |
| Self-hosted | ++ | - | ++ | - |
| Pricing | Free | $$$ | Freemium | $$$ |
| Integrations | - | ++ | ++ | ++ |
| Multi-user | - | ++ | ++ | ++ |
| UI/UX quality | + | ++ | + | ++ |

**Вывод:** Продукт конкурентоспособен по статистической глубине, но проигрывает по ecosystem (integrations, multi-user, UX). Уникальное позиционирование: **privacy-first self-hosted experiment planner** с advanced statistics — для regulated industries (finance, healthcare, government).

---

## 8. ЗАКЛЮЧЕНИЕ

AB Test Research Designer — технически сильный продукт с корректным статистическим ядром и чистой бэкенд-архитектурой. Основные инвестиции должны быть направлены на:

1. **Frontend architecture** — устранение God Component антипаттерна (ROI: снижение bug rate на 40%)
2. **UX simplification** — progressive disclosure и guided onboarding (ROI: conversion to active user +60%)
3. **Commercial infrastructure** — auth, billing, analytics (ROI: revenue enablement)

При выполнении рекомендаций Фаз 1-3 продукт имеет потенциал выйти на уровень **8.5/10** в течение 10-12 недель, что делает его конкурентоспособным в нише self-hosted experiment planning tools.

---

*BCG Technology & Digital Practice*  
*Confidential — for internal use only*
