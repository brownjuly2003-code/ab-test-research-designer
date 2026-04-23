# CX Task: Optional OpenAI / Anthropic LLM adapter с browser-session token

## Goal
Сейчас LLM-дополнения (hypothesis suggestions, metric recommendations) идут через `LocalOrchestratorAdapter` в `app/backend/app/llm/adapter.py` — локальный fallback с заранее запеченными паттернами. Добавить опциональный путь через OpenAI / Anthropic API, где API-token хранится **только в памяти браузера** (session storage), передаётся в каждый запрос через header, **никогда** не записывается в SQLite / backend logs / env / snapshot — чтобы demo на HF Spaces мог использовать реальный LLM без рисков для юзера. Tier 2 roadmap #4.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `f4178dd3`.
- **Текущий LLM слой.**
  - `app/backend/app/llm/adapter.py` — `class LocalOrchestratorAdapter` с `__init__`, возвращает `{"provider": "local_orchestrator", ...}`.
  - `app/backend/app/llm/prompt_builder.py` — формирует промпты.
  - `app/backend/app/llm/parser.py` — парсит ответы.
  - `app/backend/tests/test_llm_adapter.py` — 1 файл тестов.
- **Config / env.** `AB_LLM_TIMEOUT_SECONDS`, `AB_LLM_MAX_ATTEMPTS` — существующие. НЕ добавлять `AB_OPENAI_KEY` / `AB_ANTHROPIC_KEY` в env — это противоречит цели задачи (не хранить ключи на бэкенде).
- **Security contract.**
  - Токен живёт в `sessionStorage` браузера (не `localStorage` — stronger transient).
  - Токен передаётся в backend через HTTP header `X-AB-LLM-Token` + `X-AB-LLM-Provider` (значение: `openai` / `anthropic`).
  - Backend использует токен для одного запроса и **не персистит его** никуда — ни в логи (mask через `***`), ни в SQLite, ни в exception messages, ни в trace.
  - На `/api/v1/workspace/backup` и snapshot flow — токен не попадает (он никогда не достигает storage).
- **UX.**
  - В Wizard / Settings modal — необязательная секция "LLM provider", где юзер выбирает `Local (default)` / `OpenAI` / `Anthropic`, вводит token один раз в текущей сессии.
  - Token не персистится между перезагрузками страницы (sessionStorage авто-cleanup при закрытии вкладки).
  - Если провайдер OpenAI/Anthropic выбран, но token не задан → fallback на `Local` с warning toast "Token required — falling back to local suggestions".
- **Не трогать** snapshot_service, mkdocs site, i18n, smoke, CI workflow.

## Deliverables

### Backend

1. **Новые adapter'ы в `app/backend/app/llm/`:**
   - `openai_adapter.py` — `class OpenAIAdapter(LocalOrchestratorAdapter)`:
     - `async def suggest(prompt: str, *, token: str) -> dict` — POST `https://api.openai.com/v1/chat/completions`, model `gpt-4o-mini` (дешевле для demo), temperature 0.4, `Authorization: Bearer <token>`, timeout из `AB_LLM_TIMEOUT_SECONDS`.
     - Парсит ответ через существующий `parser.py`.
     - Возвращает `{"provider": "openai", "model": "gpt-4o-mini", ...}`.
     - При 401/403 → raise `LLMAuthError` (новый exception class, **не включающий** сам token в message).
     - При timeout / 5xx → raise `LLMTransientError`, backend ответит 503 c hint "try again or switch to local".
   - `anthropic_adapter.py` — `class AnthropicAdapter(LocalOrchestratorAdapter)`:
     - Аналогично, POST `https://api.anthropic.com/v1/messages`, model `claude-haiku-4-5-20251001` (дешёвый Haiku для demo), header `x-api-key: <token>` + `anthropic-version: 2023-06-01`.
     - Парсинг + exception-ы такие же.

2. **Adapter factory / routing.** Найти место, где сейчас используется `LocalOrchestratorAdapter` в routes (`app/backend/app/routes/*.py`). Рефакторить:
   ```python
   def pick_adapter(request: Request) -> LLMAdapter:
       provider = request.headers.get("X-AB-LLM-Provider", "").lower()
       token = request.headers.get("X-AB-LLM-Token", "")
       if provider == "openai" and token:
           return OpenAIAdapter()
       if provider == "anthropic" and token:
           return AnthropicAdapter()
       return LocalOrchestratorAdapter()
   ```
   Прокидывать token как параметр при вызове adapter, не через global state.

3. **Masking в логах.** Найти существующий logging middleware / logger configuration. Убедиться, что при логе input request'а header `X-AB-LLM-Token` маскируется (`X-AB-LLM-Token: ***`). Если current logger просто `logger.info(request.headers)` — написать фильтр на `logging.Filter` или sanitize функцию.

4. **Backend тесты:**
   - `test_openai_adapter.py` — мокнутый `httpx.AsyncClient.post`:
     - Happy path: 200, парсится корректно.
     - 401: raises `LLMAuthError`, token **не** попадает в `str(exc)`.
     - Timeout: raises `LLMTransientError`.
     - Rate limit 429: raises `LLMTransientError` с hint "rate limited".
   - `test_anthropic_adapter.py` — аналогично.
   - `test_adapter_routing.py` — mock request headers, проверяет `pick_adapter` возвращает правильный класс.
   - `test_llm_token_not_logged.py` — integration с captured logs, проверяет что real token не уходит в `caplog.records`.

### Frontend

5. **Settings / Wizard UI.** Найти existing "preferences" секцию (возможно `app/frontend/src/components/Settings/` или через i18n keys `app.preferences.*`). Добавить:
   - Dropdown provider selector: Local | OpenAI | Anthropic.
   - Password-type input для token с лейблом "API key (session only, never saved)".
   - Info-блок под input'ом: "Your key stays in browser session storage and is cleared when you close this tab."
   - Кнопка "Use local instead" — очищает sessionStorage.

6. **HTTP layer.** Найти axios / fetch wrapper в `app/frontend/src/lib/api.ts` (или equivalent). Extend так, чтобы перед запросом на `/api/v1/llm/*` endpoints авто-добавлять `X-AB-LLM-Provider` + `X-AB-LLM-Token` из `sessionStorage.getItem('ab_llm_provider')` / `ab_llm_token`, если они заданы.

7. **i18n.** Добавить новые ключи (`app.preferences.llm.*`) в en, ru, de, es locale files. Перевести по уже установленным паттернам (см. `feat(i18n): complete de/es UI translation coverage` коммит).

8. **Frontend тесты:**
   - `app/frontend/src/components/Settings/llm-provider.test.tsx` — RTL:
     - Rendering dropdown + password input.
     - sessionStorage get/set при смене provider / token.
     - Очистка sessionStorage по кнопке "Use local".
     - При `provider=openai` без token → UI показывает warning.
   - `app/frontend/src/lib/api.test.ts` — headers добавляются корректно, token не попадает в URL / body.

### Documentation

9. **`docs-site/features/llm-adapter.md`** (новый файл):
   - Обзор трёх provider'ов.
   - Security: "Your API key never leaves the browser session. The backend does not store, log, or snapshot it."
   - Где получить OpenAI / Anthropic key (ссылки на их дашборды).
   - Cost-oriented note: "Local is free. OpenAI gpt-4o-mini costs ~$0.0002 per suggestion. Anthropic claude-haiku-4-5 is similar."
   - Добавить в `mkdocs.yml` nav под Features.

10. **README.md** — одной строкой упомянуть новый адаптер в секции "Features" / "Roadmap" (заменить "✅ Published" на "✅ Optional LLM adapter" или добавить отдельный bullet).

## Acceptance
- `python -m pytest app/backend/tests/test_*adapter*.py app/backend/tests/test_llm_token_not_logged.py -v` → все тесты зелёные.
- `npm --prefix app/frontend run test -- llm-provider api` → зелёные.
- `scripts/verify_all.py --with-e2e --skip-build` → exit 0.
- Manual smoke: запустить backend + frontend, в Settings выбрать Anthropic, вставить **тестовый** ключ, сделать suggestion request → response содержит `"provider": "anthropic", "model": "claude-haiku-4-5-20251001"`. Перезагрузить tab → provider сбросился на Local, token не сохранился.
- В серверных логах за smoke — `grep -i "sk-\|claude-\|bearer" .ci-artifacts/backend.log` возвращает **0 совпадений** (токен ни в каком виде не попал в логи).
- Docs-site на `features/llm-adapter.md` задеплоился.
- Один или несколько коммитов логическими кусками:
  - `feat(llm): openai and anthropic adapters with browser-session token`
  - `feat(ui): llm provider settings with session-only token storage`
  - `docs(site): document optional llm adapter security model`

## Notes
- **Session storage, не local storage.** Ключ умирает при закрытии вкладки — это **фича**, а не баг. НЕ "улучшать" на localStorage для UX.
- **Token masking — exhaustive.** Проверить также: FastAPI validation errors (они могут включать raw headers), traceback'и, sentry/error reporters (если есть). Любое место, где может оказаться `str(request.headers)` — добавить фильтр.
- **Model choices.** `gpt-4o-mini` для OpenAI и `claude-haiku-4-5-20251001` для Anthropic — это сознательный выбор для demo: низкая стоимость, high rate limits. Не делать configurable model choice в UI — это усложнение без value для demo.
- **Не хранить usage metrics** (tokens consumed, cost) на бэкенде — это потребует persistance + ссылки на юзера. Если юзер хочет видеть usage — он смотрит в свой OpenAI / Anthropic дашборд.
- **Никакого fallback кеширования** ответов LLM на бэкенде (с токеном юзера). Response возвращается прямиком, не сохраняется.
- Отчёт (20-30 строк): какой endpoint'ы переведены на adapter routing, manual smoke steps с Anthropic, grep result для token masking, URL docs-site страницы.
