# CX Task: Fail-loud diagnostics для compare-smoke

## Goal
Когда compare-smoke падает в CI, лог должен содержать реальное состояние DOM (counts селекторов + outerHTML compare-панели + JSON-дамп найденных чекбоксов), а не только generic Playwright timeout. Без этого каждый новый drift требует локальной репликации, чтобы понять, что именно не нашлось. Цель — turnaround diagnose-fix сократить с 10-15 мин (локальный запуск) до чтения артефакта CI.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `f1316300`.
- **Текущий state.** `scripts/run_local_smoke.py` после fix'а из `117ae639` использует `get_by_role("checkbox", name="Select for comparison")`. Если параллельно будет принят таск `2026-04-23-cx-smoke-data-testid.md` — адаптировать под testid-контракт; если ещё не принят — оставить на текущих локаторах, задача **независима**.
- **CI уже готов принять артефакт.** `.github/workflows/test.yml` (добавлено в `117ae639`):
  ```yaml
  - name: Upload smoke failure dump
    if: failure() && matrix.os == 'ubuntu-latest'
    uses: actions/upload-artifact@v4
    with:
      name: smoke-failure
      path: archive/smoke-runs/
      if-no-files-found: ignore
  ```
  То есть всё, что положим в `archive/smoke-runs/<run_id>/` на момент падения — подхватится как CI artifact. Существующий smoke уже пишет туда трассы других шагов.
- **Справочник** (Playwright Python):
  - `expect(locator).to_be_visible(timeout=...)` — retry-based assertion с таймаутом.
  - `locator.evaluate_all(js_source, arg)` — одна JS-функция применяется ко всем matched-элементам, возвращает JSON-сериализуемый массив.
  - `playwright.sync_api.Error` — базовая ошибка Playwright API (таймауты, navigation и т. д.), наследуется от `Exception`.

## Deliverables

1. **В `scripts/run_local_smoke.py` обернуть compare-блок в try/except.** На `(AssertionError, playwright.sync_api.Error)`:
   - Собрать diagnostics-строку (см. п. 2).
   - Записать в `archive/smoke-runs/<run_id>/compare-diagnostics.txt`. `<run_id>` берётся из существующей логики smoke — если smoke уже создаёт таймстемпнутую подпапку для run-артефактов, использовать её; если нет — `datetime.now().strftime("%Y%m%dT%H%M%S")`. `mkdir(parents=True, exist_ok=True)` обязателен.
   - Ре-raise как `RuntimeError(diagnostics_string) from exc` — полный stack trace + diagnostics в message. Не swallow.

2. **Содержимое diagnostics-файла (каждая секция best-effort, свой try/except — сам дамп не должен падать):**

   **Секция A — URL и timestamp:**
   ```
   Compare smoke selector failure.
   URL: <page.url>
   Timestamp: <ISO8601 UTC>
   ```

   **Секция B — counts по каждому smoke-локатору:**
   ```
   Selector counts:
     [data-testid="project-compare-panel"]:         <count>
     [data-testid="project-compare-checkbox"]:      <count>
     [data-testid="project-compare-submit"]:        <count>
     #compare-selected-projects-button:             <count>
     legacy [role="option"] input[type="checkbox"]: <count>  (drift canary)
     get_by_role("checkbox", name="Select for comparison"): <count>
     generic input[type="checkbox"]:                <count>
   ```
   Каждый lookup в своём try/except — на исключении вместо числа писать `<count failed: {exc!r}>`. "Drift canary" нужен потому, что если он внезапно > 0 — значит кто-то вернул старую ARIA-разметку.

   **Секция C — JSON-дамп первых 10 compare-чекбоксов:**
   Через `page.get_by_test_id("project-compare-checkbox").evaluate_all(js)` (или эквивалент на текущем локаторе, если testid не внедрён). JS-скрипт (inline строкой в Python, escape-ить как положено):
   ```js
   els => els.slice(0, 10).map((el, index) => {
     const input = el.matches('input') ? el : el.querySelector('input');
     const labelTexts = input && input.labels
       ? Array.from(input.labels).map(label => label.innerText.replace(/\s+/g, ' ').trim())
       : [];
     return {
       index,
       tag: el.tagName.toLowerCase(),
       type: el.getAttribute('type'),
       role: el.getAttribute('role'),
       testid: el.getAttribute('data-testid'),
       projectId: el.getAttribute('data-project-id')
         || (input && input.getAttribute('data-project-id')),
       ariaLabel: el.getAttribute('aria-label')
         || (input && input.getAttribute('aria-label')),
       labelText: labelTexts.join(' | '),
       visibleText: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 200),
       checked: input ? input.checked : undefined,
       disabled: input ? input.disabled : undefined,
       outerHTML: el.outerHTML.slice(0, 500),
     };
   })
   ```
   Результат сериализовать через `json.dumps(rows, indent=2, ensure_ascii=False)`. Записать под заголовком:
   ```
   Matched compare checkbox details (first 10):
   <json>
   ```

   **Секция D — outerHTML compare-панели (truncated):**
   ```python
   htmls = page.get_by_test_id("project-compare-panel").evaluate_all(
       "(els, maxChars) => els.slice(0, 2).map(el => el.outerHTML.slice(0, maxChars))",
       8000,
   )
   ```
   Если список пустой — `<no matches>`. Если несколько — join через `"\n\n--- matched panel ---\n\n"`.

3. **Сохранить существующие скрин/трассу smoke на фейле.** Если в smoke уже есть `page.screenshot()` / `context.tracing.stop()` для других шагов — не трогать. Diagnostics-файл кладётся рядом с ними в ту же `archive/smoke-runs/<run_id>/` папку.

4. **Sanity-тест (локально):**
   - Baseline: `python scripts/run_local_smoke.py --skip-build` → exit 0, никаких diagnostics-файлов создаваться **не должно** (код выполняет diagnostics только в `except`).
   - Sabotage: временно переименовать `data-testid="project-compare-panel"` в frontend на `project-compare-panel-BROKEN`, пересобрать фронт, повторить smoke → exit non-zero, `archive/smoke-runs/<latest>/compare-diagnostics.txt` существует, содержит URL, counts (где panel = 0, checkbox > 0), JSON-блок с рядами чекбоксов, и для секции D — `<no matches>`. Вернуть переименование откатом.
   - Оба проверить локально перед коммитом, отчёт включает финальный smoke exit в обоих режимах.

## Acceptance
- Код-diff трогает только `scripts/run_local_smoke.py` (плюс при необходимости новые константы в том же файле, без вынесения в новый модуль).
- Никаких новых зависимостей в `app/backend/requirements.txt` / `package.json`.
- Baseline smoke зелёный, sabotage smoke падает с понятным diagnostics-дампом.
- `archive/smoke-runs/<run_id>/compare-diagnostics.txt` создаётся только при фейле compare-блока (другие фейлы smoke — вне scope).
- Один коммит: `chore(smoke): dump compare-panel DOM state on compare-flow failure`.

## Notes
- Diagnostics-хелпер — file-local (функция внутри `run_local_smoke.py`), без выделения в отдельный модуль. Это scaffolding, не библиотека.
- НЕ swallow исключение: `raise RuntimeError(...) from exc` — from-clause обязателен, иначе original traceback пропадёт.
- `archive/smoke-runs/` уже есть с `.gitkeep` и `README.md`, новая подпапка run'а попадает под `.gitignore` pattern `archive/smoke-runs/*` (tracked только gitkeep+README).
- Если по ходу обнаружится, что smoke уже имеет какой-то общий failure-handler / finally — встроиться туда, не дублировать логику.
- Отчёт в конце (10-15 строк): путь к модифицированной функции, diff ключевых строк, результат baseline + sabotage запусков.
