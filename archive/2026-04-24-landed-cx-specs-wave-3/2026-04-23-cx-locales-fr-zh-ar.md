# CX Task: Добавить fr / zh / ar локали (включая RTL для ar)

## Goal
Расширить i18n с 4 текущих локалей (en, ru, de, es) до 7 — добавить французский (`fr`), упрощённый китайский (`zh`) и арабский (`ar`). Arabic требует RTL layout support. Language switcher должен показать все 7. Backend `Accept-Language` поддерживает новые коды. Следовать прецеденту `c57e111d` (полный de/es перевод, 887 leaf keys, 0 placeholder mismatch).

## Context
- **Repo.** `D:\AB_TEST\`, `main`, HEAD `68c355bf` (или новее).
- **Existing locales:**
  - Frontend: `app/frontend/src/i18n/{en,ru,de,es}.json` (1157 lines each, 887 leaf keys).
  - Backend: `app/backend/app/i18n/{en,ru,de,es}.json`.
  - Init: `app/frontend/src/i18n/index.ts`, `supportedLngs: ["en","ru","de","es"]` + fallback chains `de-AT→de` / `es-MX→es`.
  - Switcher: `app/frontend/src/App.tsx` — 4 кнопки с `aria-pressed`, `aria-label="Language preference"` group, persist в `localStorage` key `ab-test:language`, `document.documentElement.lang` sync.
- **Precedent spec:** `archive/2026-04-23-landed-cx-specs/2026-04-22-cx-locales-de-es.md` (или `docs/plans/codex-tasks/` если archive ещё не run). Шаблон для перевода / терминологии / acceptance.
- **Terminology anchors (ru/de/es уже закреплены):** эксперимент/Experiment/experimento, метрика/Metrik/métrica, вариант/Variante/variante, референс/Referenz/línea base (baseline), уровень значимости/Signifikanz/significancia, мощность/Power/potencia, MDE (universal), конверсия/Konversion/conversión.
- **fr/zh/ar terminology anchors (новые):**
  - **fr:** expérience A/B, variante, référence, niveau de signification, puissance, MDE, conversion, taille d'échantillon, intervalle de crédibilité, régression vers la moyenne.
  - **zh (Simplified):** A/B 实验, 变体, 基线, 显著性水平, 检验效能, 最小可检测效应 (MDE), 转化率, 样本量, 置信区间, 贝叶斯推断.
  - **ar:** اختبار A/B، المتغيرة، الأساس المرجعي، مستوى الدلالة، القوة الإحصائية، الحد الأدنى للتأثير (MDE)، معدل التحويل، حجم العينة، الفاصل الائتماني، الاستدلال البايزي.
- **RTL requirement for ar:** `<html dir="rtl" lang="ar">` при `changeLanguage('ar')`. CSS уже должен быть agnostic, но проверить `flex-direction`, `text-align`, `margin-inline-start/end` usage. Если есть `left/right` hardcoded — заменить на logical properties.

## Deliverables

1. **Frontend локали** (3 новых):
   - `app/frontend/src/i18n/fr.json` — полный перевод всех 887 leaf keys с `en.json`.
   - `app/frontend/src/i18n/zh.json` — аналогично.
   - `app/frontend/src/i18n/ar.json` — аналогично.
   - Плюральные формы: fr — `one/other`; zh — `other` only (Chinese has no plural); ar — `zero/one/two/few/many/other` (полная CLDR).
   - **Coverage check:** после перевода `jq 'leaf_paths | length' fr.json` = `... zh.json` = `... ar.json` = 887.
   - Если термин непонятен — оставить `<angle>` маркер и фиксировать в отчёте. Предпочтительно native DS-глоссарий, не DeepL машинный.

2. **Frontend init** (`src/i18n/index.ts`):
   - `resources` добавить `fr`, `zh`, `ar`.
   - `supportedLngs: ["en","ru","de","es","fr","zh","ar"]`.
   - Fallback chains: `fr-CA→fr→en`, `zh-CN→zh→en`, `zh-TW→zh→en` (упрощённый как fallback для традиционного), `ar-SA→ar→en`, `ar-EG→ar→en`.

3. **Frontend switcher** (`App.tsx`):
   - 7 кнопок в group — может не влезать горизонтально. Рассмотреть dropdown (`<select>` с accessible label) или collapse по breakpoint.
   - `aria-pressed` / `aria-label` patterns сохранить.
   - Добавить `document.documentElement.dir = "rtl"` при `ar`, иначе `"ltr"`.

4. **Backend локали** (3 новых):
   - `app/backend/app/i18n/{fr,zh,ar}.json` — полный перевод ключей используемых в backend (warnings, reports, errors).
   - `SUPPORTED_LANGUAGES` константа в backend `i18n/__init__.py` — расширить.

5. **RTL CSS audit для ar:**
   - Grep по `app/frontend/src/**/*.{css,tsx,ts}` на:
     - hardcoded `left:` / `right:` → заменить на `inset-inline-start` / `inset-inline-end`.
     - `margin-left` / `margin-right` → `margin-inline-start` / `margin-inline-end`.
     - `padding-left` / `padding-right` → аналогично.
     - `text-align: left` / `right` → `start` / `end`.
     - `flex-direction: row` — проверить что не reverse нужен.
   - Визуальный check: запустить dev server в `ar`, убедиться что layout не сломан.

6. **Тесты:**
   - Frontend: `i18n.test.tsx` — add кейсы `changeLanguage('fr' | 'zh' | 'ar')`.
   - Frontend: `a11y-rtl.test.tsx` (новый) — render главных экранов под `lang="ar"` + `dir="rtl"`, 0 axe violations.
   - Backend: `test_export_api.py` — add `Accept-Language: fr` / `zh` / `ar` assertions на переведённый output.
   - Typecheck + full frontend suite exit 0.

7. **Docs:**
   - `README.md` — секция «Supported languages» — список 7 локалей.
   - `docs/RUNBOOK.md#adding-a-new-locale` — update со шагами для RTL (если ещё не было).

8. **Один коммит** (не bundle, локали не coupl'ятся с другими features):
   ```
   feat(i18n): french / simplified-chinese / arabic locales (+RTL for ar)
   ```

9. **Report** `docs/plans/2026-04-23-locales-fr-zh-ar-report.md`:
   - Leaf-key count на локаль (должно совпадать).
   - Список `<angle>` маркеров если остались.
   - RTL audit result: список replaced CSS properties + any that couldn't be converted automatically.
   - A11y result под `ar+rtl`.

## Acceptance
- `scripts\verify_all.cmd --with-e2e` = exit 0.
- `jq 'leaf_paths | length' app/frontend/src/i18n/{en,fr,zh,ar}.json` — все 4 одинаковые (887).
- `curl -H "Accept-Language: fr" http://127.0.0.1:8008/api/v1/analyze -X POST -d @docs/demo/sample-project.json -H "Content-Type: application/json" | jq .report.executive_summary` содержит французский текст.
- `document.documentElement.dir === "rtl"` в DOM после `changeLanguage('ar')`.
- Lighthouse a11y ≥ 0.9 для `html lang="ar" dir="rtl"`.
- Один коммит, subject уникальный, `Co-Authored-By: Codex <noreply@anthropic.com>`.
- `git status --short` = пусто после commit+push.
- CI `Tests` зелёный на main.

## Notes
- **CX-файл hygiene:** stage этого файла в коммит.
- **Native quality > machine translation.** `<angle>` маркер лучше неправильного.
- **Bundle budget:** 3 новых JSON ≈ 8-12 KB gzip total. Main chunk не должен превысить 140 KB gzip. Если превышает — рассмотреть lazy-load локалей через `i18next-http-backend` или dynamic imports по `changeLanguage`.
- **НЕ** транслитерировать термины («sample size» → «ساميبل سايز» — wrong).
- **НЕ** ломать существующие en/ru/de/es тесты.
- **Arabic typography:** убедиться что fonts поддерживают Arabic glyphs (web fonts если нужно — Noto Sans Arabic). Если дефолтный font stack не поддерживает — добавить fallback в CSS.
- **Test flakiness:** `test_performance` может флапнуть — один ретрай OK.
- **НЕ** принудительно detect'ить locale из `navigator.language` — manual select приоритет.

## Out of scope
- ja / ko / pt / hi / tr локали — отдельный follow-up.
- Date / number formatting через Intl API — отдельно.
- RTL для ru / he (hebrew не в scope сейчас).
- LLM advice translation — остаётся на языке модели.
- Translated README / RUNBOOK content — остаётся en.
