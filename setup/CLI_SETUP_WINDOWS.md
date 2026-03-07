# Codex CLI — Basic Windows Setup

Ниже не исчерпывающий reference, а практический минимальный набор для старта.

## 1. Что проверить сначала

- Установлен Git
- Установлен Python 3.11+
- Установлен Node.js LTS
- Есть отдельная папка проекта, не внутри системных каталогов
- Есть доступ к Codex CLI и вход выполнен в нужный аккаунт

Codex CLI — локальный coding agent в терминале; конфиг обычно читается из `~/.codex/config.toml`, а модель можно выбрать и через флаг командной строки. Это описано в официальной документации OpenAI. citeturn0search0turn0search2turn0search14

## 2. Базовая структура папок на Windows

Рекомендуемо:

```text
D:\Projects\ab-test-research-designer
D:\Projects\ab-test-research-designer\docs
D:\Projects\ab-test-research-designer\backend
D:\Projects\ab-test-research-designer\frontend
```

Оркестратор держать отдельно:

```text
D:\Perplexity_Orchestrator2
```

## 3. Практические настройки для экономии токенов

### Делай короткие, фазовые сессии
Не открывай одну гигантскую сессию на весь проект. Лучше:
- отдельная сессия на изучение проекта,
- отдельная на backend,
- отдельная на frontend,
- отдельная на bugfix.

### Всегда давай Codex фиксированный набор документов
На старте каждой новой сессии указывай:
- `docs/IMPLEMENTATION_SPEC.md`
- `docs/DATA_CONTRACTS.md`
- `docs/AGENT_INSTRUCTIONS.md`
- `docs/BUILD_PLAN.md`

### Не проси сразу “сделай всё”
Codex лучше работает от одной фазы к следующей. OpenAI прямо описывает Codex CLI как агент, который читает и меняет код в выбранной директории; он особенно полезен, когда стартует от спецификации или задачи, а затем выполняет шаги по репозиторию. citeturn0search0turn0search1turn0search6

## 4. Рекомендуемый режим модели

Для кодинга в Codex доступны coding-oriented модели и general-purpose модели. В документации OpenAI указаны, например, `gpt-5.4` и `gpt-5.3-codex`, которые можно выбирать в CLI при старте новой сессии. citeturn0search14turn0search13

Практически:
- для реализации кода: coding-oriented модель внутри Codex
- для архитектурных объяснений: general-purpose модель при необходимости

## 5. Минимальная дисциплина по сессиям

### Session A
Изучение проекта и документов.

### Session B
Skeleton и backend.

### Session C
Stat engine + tests.

### Session D
LLM adapter.

### Session E
Frontend.

Так контекст меньше раздувается.

## 6. Что настроить в репозитории сразу

- `.gitignore`
- `docs/progress.md`
- `README.md`
- `.env`
- `.env.example` или текстовый шаблон
- отдельные `backend/` и `frontend/`

## 7. Безопасность и приватность

OpenAI указывает, что для individual services, включая Codex, контент может использоваться для улучшения моделей, если не отключена соответствующая настройка; можно opt out через Data Controls / privacy controls. Проверь это до работы с чувствительными данными проекта. citeturn0search11

## 8. Команды старта

Примерно так:

```bash
codex
```

или с выбором модели:

```bash
codex --model gpt-5.4
```

Модель также можно переопределять при запуске новой сессии; OpenAI отдельно документирует выбор модели и конфигурацию через CLI и `config.toml`. citeturn0search2turn0search14

## 9. Чего не делать

- не запускать Codex из слишком широкой папки вроде всего диска D
- не смешивать оркестратор и новый продукт в одном репозитории
- не хранить API keys в markdown-файлах
- не просить в одной сессии и проектирование, и реализацию, и рефакторинг всего проекта сразу
