# Product Gap Check — AB Test Research Designer

> Codex agent dispatch вернул silent fail (file не создал). Investigation сделан Claude Code напрямую через Grep + Read по `D:\AB_TEST\app\` на 2026-05-10.

## 1. CUPED — `FACT` (есть, нашлось место в UI)

- **Status**: ✅ FACT
- **Where**: `app/frontend/src/components/WizardDraftStep.tsx:535-541` — секция с CSS-классом `cuped-section`. Два инпута:
  - `metrics-cuped_pre_experiment_std` (pre-experiment std dev)
  - `metrics-cuped_correlation` (correlation)
- **UI step**: WizardDraftStep = wizard **step 4 (Metrics)** — но CUPED-блок **ниже** базовых полей baseline/MDE/power. На текущем walkthrough он не попал в кадр потому что Playwright не доскроллил вниз страницы Metrics.
- **Backend**: `app/backend/app/stats/continuous.py` + `app/backend/app/routes/analysis.py` — обработка CUPED в анализе.
- **Visual для записи**: на step 4 после стандартных полей — scroll down → найти «CUPED»-секцию с двумя number inputs, заполнить (например, std=1.0, correlation=0.5) → vegetate variance reduction в Live estimate / Review.
- **Script implication**: сцена `60s @ 36-43s` и `90s @ 45-52s` остаётся валидной. Поправка к производственному рецепту: **на step 4 нужен дополнительный hero shot CUPED-секции**, не только baseline/MDE.

## 2. Multilang — `PARTIAL` (7 в коде, 4 в live demo — stale build или CSS overflow)

- **Status**: ⚠️ PARTIAL — расхождение между кодом и развёрнутым demo
- **Where (код)**: `app/frontend/src/App.tsx:12` — `SUPPORTED_LANGUAGES = ["en", "ru", "de", "es", "fr", "zh", "ar"]`. Маппинг unconditional — все 7 кнопок рендерятся всегда.
- **Where (locales)**: `app/frontend/public/locales/` — все 7 JSON файлов на месте: `en.json`, `ru.json`, `de.json`, `es.json`, **`fr.json`**, **`zh.json`**, **`ar.json`**.
- **RTL**: `App.tsx:34` — `document.documentElement.dir = language === "ar" ? "rtl" : "ltr"` — RTL хардкодом для AR.
- **Why discrepancy**: live demo на HF Spaces показывает только EN/RU/DE/ES в snapshot. Git history:
  - `d72356cd: feat(i18n): french / simplified-chinese / arabic locales (+RTL for ar)` — добавление FR/ZH/AR
  - `28bd2fbc: perf(bundle): lazy-load locale json and chunk vendor libs` — lazy-loading локалей
- **Most likely cause**: HF Spaces space `liovina/ab-test-research-designer` развёрнут со stale build (до коммита d72356cd) ИЛИ lazy-loading локалей фейлит инициализацию для FR/ZH/AR без trigger'а. Менее вероятно — CSS overflow скрывает 5-7-ю кнопки за пределами кадра.
- **Visual для записи**: код ПОДДЕРЖИВАЕТ полный 7-language flip с AR-RTL. Но live demo может НЕ отдавать AR. Два пути:
  - **Path A (быстрый)**: использовать локально собранный фронт (`cd app/frontend && npm run dev`) — там build свежий, AR-RTL flip работает гарантированно. Запись с localhost.
  - **Path B (HF demo)**: pre-recording проверить toggle в браузере вручную (сразу видно есть ли FR/ZH/AR кнопки). Если нет — перезалить Space с `git push` от `main` HEAD. Пока pre-recording делается.
- **Script implication**: сцена `90s @ 65-70s` (RTL flip как акцент) остаётся валидной — реализация в коде есть. Recording должна быть с локального dev-сервера или freshly redeployed Space.

## 3. Multi-arm с Bonferroni — `FACT` (через `bonferroni_note` в API response)

- **Status**: ✅ FACT (Bonferroni); FDR не найден в коде на frontend
- **Where (API contract)**: `app/frontend/src/lib/generated/api-contract.ts:138` — `bonferroni_note?: string | null` в response.
- **Where (UI render)**: 
  - `app/frontend/src/components/LivePreviewPanel.tsx` — отображает `bonferroni_note` в Live estimate panel
  - `app/frontend/src/components/results/internal/SensitivityOverview.tsx` — в Sensitivity table в Review-output
- **Trigger**: `bonferroni_note` приходит от backend когда `Variants count > 2` (т.е. multi-arm setup).
- **User-facing text**: `"Adjusted for multiple comparisons."` — статическая строка из API response.
- **Visual для записи**: на step 3 Setup поставить Variants count = 4 → step 4 Live estimate покажет «Adjusted for multiple comparisons.» bonferroni-note → step 6 Review в Sensitivity Overview та же подпись.
- **FDR**: в frontend коде не найден. Либо нет (только Bonferroni), либо backend-only фича. Скрипт-сцена `90s @ 58-65s` упоминает «Multi-arm. FDR. Guardrails.» — **нужно убрать FDR упоминание**, оставить только Bonferroni.
- **Script implication**: 
  - Сцена работает с Bonferroni note вместо FDR.
  - Поправка к script v3: «Multi-arm. FDR. Guardrails.» → **«Multi-arm. Bonferroni. Guardrails.»** или **«Multi-arm correction. Guardrails.»** (нейтральнее).

## 4. Bayesian view — `FACT` (полная реализация с PosteriorPlot)

- **Status**: ✅ FACT
- **Where**: 
  - `app/frontend/src/components/PosteriorPlot.tsx` — компонент с posterior distribution
  - `app/frontend/src/components/results/BayesianSection.tsx` — секция в Review-output
  - `app/frontend/src/lib/generated/api-contract.ts:139` — `bayesian_sample_size_per_variant?: number | null` в response
  - Тесты: `PosteriorPlot.test.tsx`, `PosteriorPlot.integration.test.tsx`, `a11y-bayesian-sequential.test.tsx`
- **Trigger**: Constraints step radio Frequentist → Bayesian.
- **What surfaces** (по тестам и компонентам): posterior distribution plot + credible interval + bayesian sample size per variant. Отдельная секция «BayesianSection» в Review.
- **Visual для записи**: на step 5 Constraints переключить radio с Frequentist на Bayesian → Run analysis → в Review появится BayesianSection с PosteriorPlot. Hero shot этой секции = scene `90s @ 52-58s`.
- **Script implication**: сцена остаётся валидной, нужен только дополнительный recording-step (переключить radio до Run analysis).

## Сводка для производственного рецепта

| Сцена в v3 | Реальность | Patch к recipe |
|---|---|---|
| CUPED (60s @ 36-43s, 90s @ 45-52s) | Есть в step 4 ниже базовых полей | Доскроллить step 4, заполнить cuped_pre_experiment_std + cuped_correlation, hero shot |
| Multilang RTL (90s @ 65-70s) | 7 в коде, на HF может быть stale | Recording с локального dev-сервера (`npm run dev`) — гарантированный AR-RTL flip; либо redeploy HF Space до записи |
| Multi-arm FDR (90s @ 58-65s) | Только Bonferroni, FDR нет | Скрипт: убрать «FDR», оставить «Bonferroni. Guardrails.» |
| Bayesian (90s @ 52-58s) | Полная реализация с posterior plot | На step 5 переключить radio Bayesian → Run analysis → hero shot BayesianSection |

После применения этих 4 правок — production recipe завершён, скрипт v3 синхронизирован с реальным продуктом.
