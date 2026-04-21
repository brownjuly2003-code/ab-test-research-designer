# CX Task: Добавить de.json и es.json локали

## Goal
Расширить i18n в `D:\AB_TEST\` двумя дополнительными локалями — немецкий (`de`) и испанский (`es`) — поверх уже landed `en` + `ru`. Language switcher в header должен показать все 4. Backend `Accept-Language` тоже поддерживает новые коды.

## Context
- Репо: `D:\AB_TEST\`, `main`, HEAD после `4099f73c`.
- Verify зелёный: backend 177, frontend 197 unit, scripts\verify_all.cmd --with-e2e = 0.
- Существующие локали:
  - Frontend: `app/frontend/src/i18n/en.json`, `ru.json`.
  - Backend: `app/backend/app/i18n/en.json`, `ru.json`.
  - Switcher: см. `app/frontend/src/App.tsx` (ищи `language` / `theme` controls).
- `react-i18next` init в `app/frontend/src/i18n/index.ts` — supportedLngs `["en", "ru"]`.
- Терминология (ru уже задаёт референс): эксперимент, метрика, вариант, уровень значимости, мощность, MDE, конверсия. Для de/es — использовать стандартные статистические термины (Experiment, Metrik, Variante, Signifikanz, Power, MDE, Konversion / Experimento, Métrica, Variante, Significancia, Potencia, MDE, Conversión).

## Deliverables
1. **Frontend локали:**
   - `app/frontend/src/i18n/de.json` — полный перевод всех ключей из `en.json`.
   - `app/frontend/src/i18n/es.json` — аналогично.
   - Плюральные формы: de — `one/other`; es — `one/other`.
   - Не оставлять английские strings; если термин непонятен — оставить в угловых скобках рядом `"Experiment <experiment>"` и зафиксировать в отчёте для code review.

2. **Frontend init:**
   - `src/i18n/index.ts`:
     - `resources` добавить `de` и `es` namespace `common`.
     - `supportedLngs: ["en", "ru", "de", "es"]`.
   - `App.tsx` language switcher:
     - 4 кнопки (или dropdown) EN / RU / DE / ES.
     - `aria-pressed` на активной.
     - `aria-label="Language preference"` на группе.
     - Persist в `localStorage` ключ `ab-test:language`.

3. **Backend локали:**
   - `app/backend/app/i18n/de.json` — полный перевод используемых ключей (warnings, report sections, error messages).
   - `app/backend/app/i18n/es.json` — аналогично.
   - `app/backend/app/i18n/__init__.py` — расширить `SUPPORTED_LANGUAGES = ("en", "ru", "de", "es")` (или аналогичную константу).
   - Accept-Language fallback chain: `de-AT` → `de` → `en`, `es-MX` → `es` → `en`.

4. **Тесты:**
   - Frontend: `i18n.test.tsx` — дополнить кейсами `changeLanguage('de')` + `changeLanguage('es')`.
   - Backend: `test_export_api.py` — extend кейсами `Accept-Language: de` и `Accept-Language: es` с assertion что report содержит переведённые ключевые фразы (например, немецкое «Zusammenfassung», испанское «Resumen»).

5. **A11y:**
   - Прогнать существующие `a11y-*.test.tsx` с `i18n.changeLanguage('de')` и `'es'` в beforeEach — убедиться что 0 violations сохраняется. Добавить один общий `a11y-locales.test.tsx` если удобнее, либо extend существующий.

6. **Regen:**
   - `python scripts/generate_frontend_api_types.py --check` = 0 (не должно меняться — только локали).
   - `python scripts/generate_api_docs.py --check` = 0.

7. **Docs:**
   - `README.md` — в секции «Demo» или «Docs» — перечислить supported languages (EN, RU, DE, ES).
   - `docs/RUNBOOK.md` — процедура «Adding a new locale» (reference шаги).

8. **Один коммит:**
   ```
   feat: german and spanish locales for ui and reports
   ```

9. **Отчёт `docs/plans/2026-04-22-locales-de-es-report.md`:**
   - Coverage: `jq 'paths(scalars) | length' *.json` — numbers of keys per locale (должно совпадать).
   - Список терминов с неопределённым переводом (если остались `<...>` маркеры).
   - A11y check confirmation per locale.

## Acceptance
- `scripts\verify_all.cmd --with-e2e` = exit 0.
- `jq 'leaf_paths | length' app/frontend/src/i18n/en.json` = `... de.json` = `... es.json` (совпадает).
- `curl -H "Accept-Language: de" http://127.0.0.1:8008/api/v1/analyze -X POST -d @docs/demo/sample-project.json -H "Content-Type: application/json" | jq .report.executive_summary` содержит немецкий текст (не английский).
- Frontend тесты +4–6 новых (locale switch).
- Lighthouse a11y ≥ 0.9 при `html lang="de"` / `"es"`.
- Commit subject уникальный, `Co-Authored-By: Codex <noreply@anthropic.com>`.
- Этот CX-файл стадж в свой коммит.
- `git status --short` = пусто.

## How
1. Baseline: `git status --short` = пусто, verify = 0.
2. Скопировать `en.json` → `de.json` / `es.json`. Полный перевод. Если требуется — использовать профессиональную DS-терминологию (не DeepL машинный).
3. Аналогично backend `en.json`.
4. Обновить init + supportedLngs.
5. Дополнить switcher UI. Проверить visual layout (4 кнопки могут не влезать — использовать dropdown если узко).
6. Unit-тесты.
7. README / RUNBOOK.
8. Commit + verify + report.

## Notes
- **CX-файл hygiene:** staging этого файла в коммит.
- **Commit subject hygiene:** проверка на дубль.
- **Качество перевода:** предпочтительно нативный DS-глоссарий. Если сомневаешься в термине — оставляй `<angle-bracket>` маркер и добавляй к отчёту для review; лучше mark'нутый чем неправильный.
- **НЕ** транслитерировать «Sample Size» → «Зэмпл сайз». Правильно: нем. «Stichprobengröße», исп. «Tamaño de muestra».
- **НЕ** ломать существующие `en`/`ru` тесты — вся новая локалевая логика additive.
- **Bundle budget:** 2 новых JSON ≈ 2–4 KB gzip каждый; main chunk не должен превысить 140 KB gzip. Если превышает — рассмотреть lazy-load локалей по `changeLanguage`.
- **НЕ** менять switcher на autodetect-only; manual выбор приоритет.
- Backend `test_performance` может флапнуть — перезапустить один раз.
- **НЕ** пушить на remote.

## Out of scope
- fr / zh / ja / ar (RTL) локали
- Date / number formatting per locale (Intl API) — не в scope
- Translated README / docs / RUNBOOK content (остаётся en)
- LLM advice translation (всегда на языке модели)
