# CX Task: Wire Lighthouse CI into GitHub Actions with real thresholds

## Goal
Подключить существующий `.lighthouserc.json` к CI-пайплайну `D:\AB_TEST\`: добавить job в `.github/workflows/test.yml`, который на каждом push/PR поднимает backend-served frontend, гоняет Lighthouse и валит билд при падении скоров ниже порогов.

## Context
- Репо: `D:\AB_TEST\`, HEAD = `4b28afb5`. Не ветка, работать на main локально.
- `.lighthouserc.json` уже в корне (из Commit `c29ab0d7`), содержит:
  - `collect.url = ["http://127.0.0.1:3000"]`, `numberOfRuns=1`, `preset=desktop`
  - `assert.assertions`: `performance ≥ 0.85` (warn), `accessibility ≥ 0.9` (error), `best-practices ≥ 0.9` (warn), `seo ≥ 0.8` (warn)
  - `upload.target = "temporary-public-storage"`
- **Проблема:** URL `127.0.0.1:3000` не соответствует реальному runtime (backend-served frontend стартует на free port через `scripts/run_frontend_e2e.py`; e2e использует `PORT` env). В CI никто Lighthouse не запускает — `.lighthouserc.json` лежит мёртвым весом.
- CI config: `.github/workflows/test.yml`. В нём сейчас запускаются `npm.cmd run test:unit`, backend pytest, build, e2e. Добавить шаг Lighthouse **после** build и e2e.
- Порты: в CI удобно использовать фиксированный порт (например, 4174 — совпадает с vite preview range). Backend должен серверить прод-бандл (`AB_SERVE_FRONTEND_DIST=true`, `npm run build` → `app/frontend/dist/`).

## Deliverables
1. Обновить `.lighthouserc.json`:
   - `collect.url` → `["http://127.0.0.1:4174/"]` (или через env-var `${LHCI_URL}`).
   - `collect.numberOfRuns` → `3` (уменьшить шум).
   - Добавить `collect.settings.skipAudits = ["uses-http2", "canonical"]` (ложные срабатывания на localhost).
   - Оставить current thresholds **как есть**, не занижать.
2. Новый Python-хелпер `scripts/run_lighthouse_ci.py`:
   - Принимает `--port` (default 4174), `--dist-dir` (default `app/frontend/dist`).
   - Запускает uvicorn с `AB_SERVE_FRONTEND_DIST=true`, `AB_FRONTEND_DIST_PATH=app/frontend/dist`, `--port <port>`.
   - Ждёт `GET /health` → 200 (timeout 30s).
   - Экспортит `LHCI_URL=http://127.0.0.1:<port>/`.
   - Запускает `npx lhci autorun`.
   - В любом случае убивает uvicorn в `finally` (через subprocess.Popen + terminate).
   - Возвращает exit code lhci.
3. Обновить `.github/workflows/test.yml`:
   - Новый job `lighthouse` (или шаг в существующем frontend-job):
     - Зависит от build-step (нужен готовый `dist/`).
     - Устанавливает `npm install -g @lhci/cli@0.14.x` (pin версии).
     - Запускает `python scripts/run_lighthouse_ci.py`.
     - Артефактит `.lighthouseci/` через `actions/upload-artifact@v4`.
   - Поля: `continue-on-error: false` для accessibility (error threshold), но warning categories не должны ронять build.
4. Обновить `scripts/verify_all.py` и `scripts/verify_all.cmd` — добавить опциональный флаг `--with-lighthouse`, который вызывает `run_lighthouse_ci.py`. По умолчанию **выключен** (локально не нужен, медленно).
5. `README.md` — короткая секция `Lighthouse` (как запустить локально, какие пороги).
6. Один коммит: `ci: wire lighthouse ci with backend-served frontend and real thresholds`.
7. Короткий отчёт `docs/plans/2026-04-21-lighthouse-ci-report.md`:
   - Первый прогон скоры (perf/a11y/bp/seo).
   - Что чинилось если упало (или «зелёно с порога»).

## Acceptance
- `python scripts/run_lighthouse_ci.py` локально на чистом HEAD = exit 0. Или — если threshold не проходит — exit != 0 с читаемым выводом (и в отчёте зафиксировано, что скоры ниже; в таком случае код-фиксы до прохождения).
- `scripts\verify_all.cmd --with-e2e` = exit 0 (без `--with-lighthouse` — быстрый).
- `scripts\verify_all.cmd --with-e2e --with-lighthouse` = exit 0 (полный).
- CI workflow YAML синтаксически валиден: `python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"` = 0.
- Commit на HEAD с правильным сообщением и Co-Authored-By.
- Отчёт создан, содержит реальные числа.

## How
1. Изменить `.lighthouserc.json`.
2. Написать `scripts/run_lighthouse_ci.py` — основа: `subprocess.Popen(uvicorn)`, health-poll через `urllib.request`, `subprocess.run(["npx", "lhci", "autorun"])`, teardown uvicorn.
3. Обновить workflow YAML. Использовать `actions/setup-node@v4` если нет; Node LTS.
4. Прогнать локально: `npm run build && python scripts/run_lighthouse_ci.py`. Смотреть результат.
5. Если a11y < 0.9 — открыть `.lighthouseci/lhr-*.json`, исправить топ-2 violations кодом (или поднять с a11y audit task, если тот уже запущен).
6. Если perf < 0.85 — проверить main JS bundle gzip (≤ 130 KB); при необходимости дотянуть lazy-loading.
7. Коммит, verify, отчёт.

## Notes
- **Не** занижать threshold'ы чтобы зелёное прошло. Если скоры не добраться — лучше зафиксировать `continue-on-error: true` только для `performance` с TODO в отчёте, сохранить строгий gate на accessibility.
- **Не** использовать `temporary-public-storage` upload в CI если есть чувствительные данные — оставить как есть (пустой демо).
- Не ставить `@lhci/cli` в `devDependencies` — это глобальный CLI для CI; локально тоже через `npx @lhci/cli@0.14.x autorun` чтобы не тянуть в bundle.
- Free-port-pick нужен если `4174` занят: сделать `--port 0` с pick через `socket.bind((_, 0))` и передавать в uvicorn. Но для CI фикс `4174` проще.
- Windows-specific: uvicorn subprocess teardown — использовать `CREATE_NEW_PROCESS_GROUP` + `CTRL_BREAK_EVENT` либо `taskkill /F /PID <pid>`. На Linux CI — `terminate()` достаточно.
- Backend test_performance p95-guard может флапнуть — перезапустить один раз.
- **Не** пушить на remote.

## Out of scope
- Code-splitting рекчарта дальше (уже lazy)
- Визуальный редизайн
- A11y fixes (отдельный таск — `2026-04-21-cx-a11y-audit.md`)
- Новые GitHub Actions (Snyk, CodeQL и т.д.)
