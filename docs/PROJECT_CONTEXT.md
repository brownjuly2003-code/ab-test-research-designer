# Project Context

## Product name
AB Test Research Designer

## Product idea
Локальный веб-сервис для проектирования A/B тестов.

Пользователь вводит:
- базовые данные по эксперименту,
- контекст проекта,
- что именно он хочет тестировать,
- какую гипотезу проверяет,
- какие результаты ожидает,
- какие ограничения есть.

Сервис возвращает:
- расчеты ключевых метрик и параметров теста,
- оценку реализуемости эксперимента,
- полный дизайн исследования,
- список primary / secondary / guardrail / diagnostic metrics,
- риски и методологические warning'и,
- дополнительные советы, сгенерированные LLM с учетом контекста.

## Hard constraints already decided

1. Продукт должен запускаться локально.
2. Интерфейс — веб.
3. Основной сценарий — single-user local usage.
4. Внешняя LLM в этом проекте не используется напрямую как облачный SaaS внутри продукта.
5. В качестве LLM-слоя будет использоваться Claude Sonnet 4.6 Thinking через локальный оркестратор.
6. Локальный оркестратор находится на диске `D`, папка `Perplexity_Orchestrator2`.
7. Codex должен сначала изучить проект и только потом реализовывать по фазам.
8. Детеминированные расчеты и статистика не должны делегироваться LLM.
9. LLM используется только для:
   - анализа рисков,
   - контекстных советов,
   - улучшения формулировки гипотезы,
   - описания ограничений и угроз валидности,
   - human-readable summary.
10. MVP не должен требовать облачной инфраструктуры.

## Recommended tech stack

### Frontend
- React
- TypeScript
- Vite
- React Hook Form
- Zod
- TanStack Query
- simple CSS or Tailwind

### Backend
- Python 3.11+
- FastAPI
- Pydantic v2
- SciPy / statsmodels / NumPy
- SQLite
- SQLAlchemy optional

### Exports
- Markdown export mandatory
- HTML export mandatory
- PDF export optional for MVP, if low effort

## Main user
Новичок или junior/middle PM/аналитик, которому нужен понятный интерфейс и объяснимый результат.

## Product principles

- explainability first
- deterministic math first
- LLM second
- no hidden assumptions without warnings
- phased delivery
- beginner-friendly UX
