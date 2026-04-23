# CX Task: Phase 2 gap check — reduced-motion + bundle budget

## Goal
Подтвердить что реализация Phase 2 в `D:\AB_TEST\` проходит два constraints из `docs\plans\codex-tasks\phase-2-*.md`:
1. CSS правило `@media (prefers-reduced-motion: reduce)` отключает transitions и animations во всём приложении.
2. Main JS gzip-bundle < 130 KB (PowerCurveChart должен лежать в отдельном lazy-chunk, основной chunk не должен тянуть recharts целиком).

Если проверка выявит дефицит — закрыть минимальным патчем и зафиксировать в отчёте.

## Context
- Репо: `D:\AB_TEST\`, ветка `main`.
- Phase 2 уже реализован в working tree (charts, skeletons, dark toggle, lucide icons).
- Этот таск может запускаться **до или после** коммит-таска (`2026-04-21-cx-commit-phase-1-2.md`). Если после — работать на HEAD; если до — правки попадут в Commit 2 bucket.
- Последний build: main JS gzip ≈ 114.80 KB, PowerCurve chunk gzip ≈ 107.09 KB (отдельный chunk). Теоретически в лимите, но нужна проверка на HEAD.

## Deliverables
1. `docs\plans\2026-04-21-phase-2-gap-report.md` с разделами:
   - **Reduced motion:** путь к CSS файлу где реализовано, выдержка правила; если был патч — diff-summary.
   - **Bundle budget:** вывод `npm run build` с размерами dist, явное PASS/FAIL по 130 KB gzip на main chunk; ссылка на lazy-load механизм (`React.lazy` / dynamic import) для PowerCurveChart; если не lazy — где и как починено.
   - **Risk log:** что изменилось в CSS/TSX и влияет ли на существующие тесты.
2. Если патч — минимальные правки в `app/frontend/src/styles/**` и/или `app/frontend/src/components/ResultsPanel.tsx` (или где импортится PowerCurveChart).
3. После правок: `cd app/frontend && npm.cmd exec tsc -- --noEmit -p . && npm.cmd run test:unit && npm.cmd run build` → все exit 0.

## Acceptance
- `grep -r "prefers-reduced-motion" app/frontend/src/` возвращает **ровно одно** (или несколько согласованных) правил, покрывающих `*, *::before, *::after { transition: none !important; animation: none !important; }`.
- `npm run build` → main JS gzip < 130 KB; PowerCurveChart в отдельном chunk.
- Unit tests: 152/152 passed (baseline); новых тестов добавлять не нужно — визуальная проверка достаточна.
- Отчёт создан и содержит фактические цифры из build-вывода.

## How

### Reduced motion
1. `grep -rn "prefers-reduced-motion" app/frontend/src/styles/ app/frontend/src/App.css` — если нашёл, зафиксировать; если нет — создать `app/frontend/src/styles/motion.css` (или дописать в существующий общий стилевой файл) блок:
   ```css
   @media (prefers-reduced-motion: reduce) {
     *, *::before, *::after {
       animation-duration: 0.001ms !important;
       animation-iteration-count: 1 !important;
       transition-duration: 0.001ms !important;
       scroll-behavior: auto !important;
     }
   }
   ```
2. Подключить в точке входа (`main.tsx` или `styles/index.css`).
3. Ручная проверка: в браузере DevTools → Rendering → «Emulate CSS media feature prefers-reduced-motion: reduce» → анимация Skeleton должна остановиться, hover-lift на метрик-картах — без transform.

### Bundle budget
1. `cd app/frontend && npm.cmd run build`. Зафиксировать строку `dist/assets/index-*.js` + gzip.
2. Если gzip ≥ 130 KB:
   - Посмотреть где импортится `recharts`. Цель — только в `PowerCurveChart.tsx` (+ внутри `results/*`), и сам `PowerCurveChart` должен подгружаться через `React.lazy`.
   - Если в `ResultsPanel.tsx` есть прямой `import { PowerCurveChart } from "./PowerCurveChart"` — заменить на `const PowerCurveChart = React.lazy(() => import("./PowerCurveChart"))` и обернуть в `<Suspense fallback={<Skeleton ... />}>`.
   - Повторить build, убедиться что main chunk упал < 130 KB и появился отдельный async-chunk.
3. Если уже < 130 KB — просто зафиксировать в отчёте, ничего не менять.

## Notes
- **Не** обновлять `recharts` / `lucide-react` версии.
- **Не** трогать backend.
- Если reduced-motion уже реализован правильно, **не** дублировать правило в нескольких местах.
- Если требуется `React.lazy` — импорт `Suspense` обязателен; без него React 19 выбросит runtime ошибку.
- Не использовать `React.lazy` для компонентов которые монтируются сразу при первом рендере Results — фоллбек должен быть внятным скелетоном, не пустотой.

## Out of scope
- Любые другие Phase 2 / Phase 3 / Phase 4 правки
- Коммиты (их делает коммит-таск отдельно — см. `2026-04-21-cx-commit-phase-1-2.md`). Работу этого таска оставить в working tree и **не** коммитить самостоятельно, если коммит-таск ещё не отработан.
