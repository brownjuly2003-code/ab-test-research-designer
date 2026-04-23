# CX Task: Bundle optimization — main chunk 247KB → <200KB gzip

## Goal
Снизить main JS chunk с текущих 247.88 KB gzip ниже 200 KB gzip через targeted lazy-loading без деградации UX. Follow-up к `d72356cd` где 3 новые локали вытолкнули bundle за 140 KB advisory; реалистичный целевой budget — 200 KB (recharts + react и так ~150 KB gzip даже без app code).

## Context
- **Repo.** `D:\AB_TEST\`, `main`, HEAD `906ec9ce` (или новее).
- **Current bundle** (из `npm --prefix app/frontend run build`):
  - `index-*.js`: **247.88 KB gzip** (851.86 KB raw) — main chunk.
  - `CartesianChart-*.js`: 106.33 KB gzip — уже lazy (recharts core).
  - `ComparisonDashboard-*.js`: 11.19 KB gzip — уже lazy.
  - `PosteriorPlot`, `PowerCurveChart`, `SequentialBoundaryChart`, `LineChart`: 0.9-5.8 KB gzip — lazy.
  - `WebhookManager`, `ApiKeyManager`: 2.1-2.6 KB gzip — lazy.
- **Что вероятно сидит в main chunk:**
  - 7 locale JSONs через static `import` в `app/frontend/src/i18n/index.ts` (en+ru+de+es+fr+zh+ar = 412 KB raw, ~80 KB gzip).
  - `zustand` stores и большинство components.
  - `i18next` + `react-i18next` runtime.
  - `react` + `react-dom` + i18n detector.
- **Хорошая newxs:** `manualChunks` не настроен в `vite.config.ts` — можно добавить.
- **Не трогать:** тесты кроме релевантных frontend a11y/unit тестов, CI workflow, lighthouse.lighthouserc.json (targets уже правильные), spec файлы.

## Deliverables

1. **Lazy-load локалей через `i18next-http-backend` ИЛИ dynamic imports в `i18n/index.ts`.**
   - Preferred: dynamic imports. В `i18n/index.ts` заменить статические `import en from "./en.json"` и т.д. на `backend: { loadPath: "/locales/{{lng}}.json" }` с `i18next-http-backend`, либо вручную через `i18n.addResourceBundle` после `import("./en.json")`.
   - Переместить JSON'ы в `app/frontend/public/locales/{en,ru,de,es,fr,zh,ar}.json` чтобы vite их не inline'ил.
   - Backend FastAPI уже mount'ит `app/frontend/dist/` — убедиться что `public/locales/` попадает в build output (vite копирует `public/*` в корень dist).
   - Update backend если он serve'ит static — убедиться что новый маршрут `/locales/*.json` проксируется.
   - Cache стратегия: `cache: ["localStorage"]` от i18next-browser-languagedetector уже в init — оставить. Добавить `detection.caches` если нужно для skip'а повторных fetch'ей.

2. **`vite.config.ts` manualChunks:**
   ```ts
   build: {
     rollupOptions: {
       output: {
         manualChunks: {
           "vendor-react": ["react", "react-dom"],
           "vendor-i18n": ["i18next", "react-i18next", "i18next-browser-languagedetector"],
           "vendor-state": ["zustand"],
         },
       },
     },
     chunkSizeWarningLimit: 500,
   },
   ```
   Цель — вытащить React и i18next core в стабильные vendor chunks с хорошим cache hit rate.

3. **Проверка.**
   - `npm run build` → main chunk <200 KB gzip. Report размеры до/после.
   - Сохранить типовые user-flows: language switch (с проверкой что переключение на не-загруженную локаль показывает loading indicator или fallback на en), project compare, Monte-Carlo distribution view — всё должно работать.
   - Network tab (DevTools) — подтвердить что только `en.json` (default) загружается на старте; другие локали — on-demand.

4. **Тесты.**
   - `i18n.test.tsx`: добавить кейс "async changeLanguage loads the target locale via backend fetch" — stub `fetch` / i18next backend, проверить что `changeLanguage('fr')` вызывает resolver.
   - Если dropped тесты при переходе на async — fix их (использовать `await i18n.changeLanguage(...)`).
   - `a11y-rtl.test.tsx`: убедиться что `beforeEach` async load работает (изменить `i18n.changeLanguage("ar")` на properly-awaited). Test должен остаться стабильным.
   - Full frontend suite под 2-forks должен быть зелёным.

5. **Отчёт `docs/plans/2026-04-23-bundle-optimization-report.md`:**
   - Bundle размеры до/после (main + каждый chunk).
   - Lighthouse performance score до/после (локальный запуск lhci autorun в dev).
   - First Contentful Paint / Largest Contentful Paint до/после если получится измерить.

6. **Один коммит:** `perf(bundle): lazy-load locale json and chunk vendor libs`.

7. **Push** на origin/main.

## Acceptance
- `npm --prefix app/frontend run build` → main chunk < 200 KB gzip (экономия ≥ 50 KB vs baseline 247.88 KB).
- Vendor chunks (react / i18n / state) создались как отдельные assets.
- `npm run test:unit` зелёный под default параллелизмом.
- `scripts\verify_all.cmd --with-e2e` = 0.
- Lighthouse performance score не хуже чем было (обычно improves after lazy-load).
- Смена локали в UI работает во всех 7 вариантах (ручной smoke).

## Notes
- **НЕ** делать `--maxWorkers=1` global — если тесты флапают на locale load race, fix через proper async/await в beforeEach.
- **НЕ** ломать HF Space build — public/locales/* должны попадать в `app/frontend/dist/` для Docker serving. Проверить `app/backend/app/main.py` static mount.
- **НЕ** трогать `app/frontend/src/i18n/index.ts` так, чтобы SSR ломалось (если есть). Проверить.
- Bundle budget 200 KB — soft target. Если lazy-load локалей дал 195 KB — ок, не гонись за 180.
- **LocalStorage caching.** i18next-browser-languagedetector с `caches: ["localStorage"]` может кэшировать язык (уже реализовано); добавь `i18next-localstorage-backend` если хочешь кэшировать JSON bundle'ы — optional.

## Out of scope
- Route-level code splitting (отдельный follow-up).
- React Server Components.
- Замена recharts на легкие chart libs (отдельно).
- Перенос i18n JSON в server-side API (overkill для static files).
