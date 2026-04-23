# CX Task: Полный перевод UI на de/es (1158 ключей)

## Goal
Сейчас `app/frontend/src/i18n/de.json` и `es.json` содержат по 32 строки (~3% от `en.json` в 1158 строк) — только `app.*` namespace. Всё остальное падает на `fallbackLng: "en"`, и пользователь в немецком / испанском режиме видит большую часть UI на английском. Закрыть gap: полностью перевести de/es на фактический контент en.json, сохранив структуру ключей и плейсхолдеров. Tier 2 roadmap #1 из README.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `1e8472b0`.
- **Файлы.**
  - Источник: `app/frontend/src/i18n/en.json` — 1158 строк, canonical.
  - Таргеты: `app/frontend/src/i18n/de.json`, `app/frontend/src/i18n/es.json` — сейчас 32 строки каждый (только `app.title`, `app.tagline`, и т. п. в `app` namespace).
  - Backend локали `app/backend/app/i18n/{de,es,en}.json` уже полные (использовались в export-тестах) — **не трогать**, это отдельный contract.
- **Runtime.** `react-i18next` (см. `app/frontend/src/i18n/index.ts`), `fallbackLng: "en"`, `regional fallback` `de-AT→de` / `es-MX→es`. Тест на локальные переключатели — `app/frontend/src/test/a11y-locales.test.tsx`.
- **UI strings.** В en.json есть интерполяции `{{name}}`, `{{count}}`, pluralization через i18next (`key_one` / `key_other`), вложенные объекты глубиной до 5. Все плейсхолдеры и plural-формы должны сохраниться bит-в-бит.
- **Runbook.** `docs/RUNBOOK.md#adding-a-new-locale` описывает минимальные шаги (добавить файл, зарегистрировать в switcher). Для full coverage — шаги те же, но объём другой.
- **Домен.** A/B testing / experimentation terminology: "metric", "baseline", "variant", "conversion", "significance", "sample size", "power", "MDE", "SRM", "bayesian posterior", "HDI", "sequential testing", "CUPED". Соответствующий de/es терминологический стандарт — у статистики и data-science сообщества; использовать устоявшиеся переводы (см. Notes).

## Deliverables

1. **`app/frontend/src/i18n/de.json`** — полный перевод en.json.
   - Та же структура JSON (тот же порядок ключей, та же глубина вложенности).
   - Все `{{placeholder}}` сохранены побуквенно.
   - Pluralization: для каждого ключа, у которого в en есть `_one` и `_other`, создать `_one` и `_other` в de (немецкий использует две формы, как английский — можно mapping 1:1).
   - Tone: sachlich, direkt, без англицизмов там, где есть устоявшийся немецкий термин.
   - Терминологические choices (привязать раз, применять везде):
     - "A/B test" → "A/B-Test"
     - "variant" → "Variante"
     - "baseline" → "Referenz" (не "Baseline")
     - "conversion rate" → "Konversionsrate"
     - "statistical significance" → "statistische Signifikanz"
     - "sample size" → "Stichprobengröße"
     - "MDE (minimum detectable effect)" → "MDE (minimal detektierbarer Effekt)"
     - "SRM (sample ratio mismatch)" → "SRM (Stichprobenverhältnis-Abweichung)"
     - "posterior" → "A-posteriori-Verteilung" (или "Posterior" где длина критична)
     - "credible interval / HDI" → "Kredibilitätsintervall"

2. **`app/frontend/src/i18n/es.json`** — полный перевод en.json.
   - Та же структура, те же placeholders и pluralization (испанский — 2 формы `_one`/`_other`).
   - Tone: formal tú / usted mix — **использовать `usted`** (formal) для consistency с business/B2B tone.
   - Терминологические choices:
     - "A/B test" → "test A/B"
     - "variant" → "variante"
     - "baseline" → "línea base"
     - "conversion rate" → "tasa de conversión"
     - "statistical significance" → "significancia estadística"
     - "sample size" → "tamaño de muestra"
     - "MDE" → "MDE (efecto mínimo detectable)"
     - "SRM" → "SRM (desajuste de proporción de muestra)"
     - "posterior" → "posterior" (использовать термин как есть, это стандарт в испаноязычной статистике)
     - "credible interval / HDI" → "intervalo de credibilidad"

3. **Валидация структуры.** Скрипт / ручная проверка, что keys set в en / de / es идентичен:
   - `python -c "import json; e=json.load(open('app/frontend/src/i18n/en.json')); d=json.load(open('app/frontend/src/i18n/de.json')); print(set(flatten(e)) - set(flatten(d)))"` (или эквивалентная проверка — достаточно jq `leaf_paths` diff).
   - Если есть missing — дополнить. Если есть extra — удалить.

4. **Фронтенд-тесты:** `npm --prefix app/frontend run test -- src/test/a11y-locales.test.tsx` должен остаться зелёным. Если тест проверяет наличие конкретных ключей или длин — убедиться, что они присутствуют и в de/es.

5. **Обновить `docs/RUNBOOK.md`** (секция "adding a new locale") — одной строкой, что de/es теперь full coverage, не partial. Больше ничего в runbook не менять.

## Acceptance
- `wc -l app/frontend/src/i18n/*.json` → три файла с близкими line counts (en 1158, de/es должны быть в пределах ±5% — небольшая вариация из-за разной длины переводов).
- `python scripts/verify_all.py --skip-build` → exit 0 (frontend typecheck + unit + e2e не сломались).
- Ручная проверка в браузере (`npm --prefix app/frontend run dev`): переключить locale на `de`, пройти Wizard → Review → Results → Comparison → Webhooks — нет английских fallback-строк (только если в en сама строка — имя собственное / название продукта). То же для `es`.
- Никаких TODO-placeholders вида "TODO translate" в финальных файлах.
- Один коммит: `feat(i18n): complete de/es UI translation coverage`.
- Если translation занимает >1 сессию CX — промежуточный pointer в `docs/plans/2026-04-23-translation-progress.md` OK, но не коммитить partial перевод в main.

## Notes
- **Перевод не буквальный.** Цель — natural phrasing в немецком / испанском, а не word-for-word match. "Click to continue" → в de "Weiter" (короче), а не "Klicken Sie, um fortzufahren". Читаемость > literal.
- **Consistency внутри файла важнее, чем точность конкретного термина.** Если 10 раз перевёл "variant" как "Variante", не переключайся на "Option" в 11-й — даже если "Option" идёт лучше по смыслу в конкретном месте.
- **Длинные переводы.** Немецкий в среднем на 30% длиннее английского (композитные существительные). Если перевод ломает UI layout — это не scope этой задачи, оставить как есть и флагнуть в отчёте.
- **Не лить переводы через Google Translate / DeepL без review.** Особенно статистические термины — machine translation часто выбирает неправильный термин в context A/B testing. Если не уверен — используй термины из `backend/app/i18n/de.json` / `es.json` как ground truth (там уже выверено для export-отчётов).
- **Не расширять en.json** в ходе работы. Если найдёшь ключ, который не используется в компонентах (dead key) — оставить, не trimmить; это отдельная уборка.
- Отчёт (15-20 строк): line-count итог по каждому файлу, список терминологических choices (чтобы будущий fr/zh/ja/ar переводчик был consistent), замеченные UI-layout риски, повторные запуски suite.
