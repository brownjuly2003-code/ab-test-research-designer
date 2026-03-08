# Рекомендации по проекту AB_TEST

Дата аудита: 2026-03-08

## Общая оценка

Полностью функциональный MVP, построенный за один день (27 коммитов, 7 марта). Архитектура грамотная: детерминированные расчёты отделены от LLM, модули компактные (<100 строк), API типизирован через Pydantic. Статистические формулы корректны. Проект готов к демонстрации, но для production нужна доработка.

| Критерий | Оценка | Комментарий |
|---|---|---|
| Архитектура | 7/10 | Хорошая модульность, но дублирование типов Python↔TypeScript |
| Качество кода | 7/10 | Типизировано, но App.tsx монолитный (648 строк) |
| Статистика | 8/10 | Формулы верны, Bonferroni есть, но слишком консервативна при >2 вариантах |
| Безопасность | 7/10 | XSS защита есть, SQL параметризован, но CORS `["*"]` |
| Тесты | 6/10 | 10 файлов backend + 3 frontend, но нет граничных случаев |
| Production-readiness | 5/10 | Локальный инструмент, не рассчитан на нагрузку |

---

## MUST — критично

### 1. Закоммитить или откатить незакоммиченные изменения

`git diff --stat` показывает +353/-7 строк в repository.py, schemas/api.py, main.py и тестах. Это расширение activity metadata, висящее в воздухе. Либо закоммитить с тестами, либо `git checkout -- .`

### 2. Убрать мусор из корня проекта

10 папок `pytest-cache-files-*` засоряют корень. Удалить и добавить в .gitignore:
```
pytest-cache-files-*/
```

### 3. CORS — убрать wildcard

```python
# main.py:85 — сейчас:
allow_methods=["*"],
allow_headers=["*"],

# Рекомендация:
allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
allow_headers=["Content-Type", "Accept"],
```

### 4. Граничные тесты для статистики

Отсутствуют тесты для:
- `baseline_rate` близкий к 0 или 1 (binary)
- `mde_pct` = 0 или отрицательный
- `std_dev` = 0 (continuous)
- `variants_count` = 1 или >10
- `daily_traffic` = 0

Это критично, т.к. статистика — ядро продукта.

---

## SHOULD — важно

### 5. Bonferroni коррекция слишком консервативна

`binary.py:28`, `continuous.py:27`:
```python
comparison_count = max(1, variants_count - 1)
adjusted_alpha = alpha / comparison_count
```
При 5 вариантах alpha делится на 4, что даёт сильно завышенный sample size. Для A/B тестов с multiple treatments стандарт — Dunnett's test или Holm-Bonferroni. Как минимум, нужно документировать это допущение и предупреждать пользователя.

### 6. App.tsx — разбить на компоненты

648 строк, 15+ useState — классический God Component. Рекомендация:
- Извлечь custom hooks: `useProjectManager`, `useDraftPersistence`, `useAnalysis`
- CSS вынести в отдельный файл (93 строки CSS внутри JS)
- Использовать `useReducer` или Zustand для сложного стейта

### 7. Дублирование типов Python ↔ TypeScript

`MetricType`, `ProjectContext`, `ExperimentInput` определены в обеих кодовых базах. При изменении нужно обновлять оба места. Решения:
- Генерировать TypeScript типы из OpenAPI схемы FastAPI (`/openapi.json`)
- Или хотя бы добавить интеграционный тест на совместимость схем

### 8. Magic number 56 в Rules Engine

`catalog.py`: `"Estimated duration exceeds 56 days"` — откуда 56? Нет документации. Вынести в константу с пояснением:
```python
MAX_RECOMMENDED_DURATION_DAYS = 56  # 8 weeks — standard sprint cycle limit
```

### 9. Error handling в main.py

Перехватывается только `ValueError`:
```python
except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```
`KeyError`, `TypeError`, `ZeroDivisionError` пролетят как 500. Добавить общий exception handler.

### 10. LLM adapter — exponential backoff

Один запрос, один таймаут, один ответ. При flaky оркестраторе нет retry с backoff. Для production нужен хотя бы простой retry (2-3 попытки с увеличивающейся задержкой).

---

## NICE TO HAVE — при наличии времени

### 11. Документация — сократить

12 файлов документации на 1600 строк кода — избыточно. Объединить:
- `docs/BUILD_PLAN.md` + `progress.md` → один файл
- `docs/PROJECT_CONTEXT.md` + `docs/IMPLEMENTATION_SPEC.md` → один файл
- `AGENT_INSTRUCTIONS.md` + `prompts/PROMPTS.md` → удалить (артефакты Codex)
- `setup/` → секция в README.md

### 12. env-example.md → .env.example

Markdown-файл для примера окружения — нестандартно. Переименовать в `.env.example` без markdown-разметки.

### 13. Frontend оптимизация

- `React.memo` для компонентов, не зависящих от parent state
- localStorage: обработать `QuotaExceededError` (сейчас `catch {}` молча глотает)
- `SaveProjectResponse.payload` может быть `undefined`, но код не проверяет

### 14. SELECT * в repository.py

```python
connection.execute("SELECT * FROM projects WHERE id = ?", ...)
```
Лучше явно указать колонки — исключить тяжёлые `payload_json`, `last_analysis_json` где они не нужны (например, в `list_projects`).

### 15. CSS — вынести из JS

93 строки inline CSS в App.tsx. Вынести в `App.css` или использовать CSS modules.

---

## Порядок в репозитории

Рекомендуемые немедленные действия:
```bash
# 1. Удалить pytest cache
rm -rf pytest-cache-files-*/

# 2. Закоммитить или откатить незакоммиченные изменения
git diff --stat  # проверить что висит
git add -A && git commit -m "Complete activity metadata tracking"
# или: git checkout -- .

# 3. Обновить .gitignore
echo "pytest-cache-files-*/" >> .gitignore
```
