# CX Task: Regenerate `docs/demo/*.png` screenshots against v1.1.0 UI

## Goal
Перегенерировать все три PNG-скриншота в `docs/demo/` так, чтобы они показывали реальный v1.1.0 UI (comparison dashboard, webhook manager, 4-language switcher). Добавить 2 новых скриншота — `comparison-dashboard.png` и `webhook-manager.png` — и обновить секцию `## Demo` в `README.md` + HF Space README, чтобы ссылки указывали на свежие файлы. Существующий `scripts/run_local_smoke.py` уже пишет 3 основных скрина; его нужно расширить, а не заменять.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `14259fff` (tag `v1.1.0`). Не ветка, не push.
- **Текущие скриншоты.** `docs/demo/wizard-overview.png`, `docs/demo/review-step.png`, `docs/demo/results-dashboard.png`. Сгенерированы до v1.1.0 и не отражают новые фичи: multi-language switcher (4 кнопки en/ru/de/es), WebhookManager в sidebar, ComparisonDashboard (lazy-loaded React chunk).
- **Smoke script.** `scripts/run_local_smoke.py` использует Playwright, поднимает backend на свободном порту, открывает frontend `dist`, импортирует `docs/demo/sample-project.json`, делает analysis и три скриншота через `capture_success_screenshot()` (строки 106-220). Архивит копии в `app/frontend/playwright-smoke-artifacts/<timestamp>/screenshots/`.
- **Sample data.** `docs/demo/sample-project.json` — существует, используется smoke.
- **Comparison endpoint.** `POST /api/v1/projects/compare` — берёт 2-5 project IDs. Frontend-компонент `app/frontend/src/components/ComparisonDashboard.tsx`. Чтобы сделать скрин — нужно ≥2 saved project с analysis. Seed-скрипт `scripts/seed_demo_workspace.py` создаёт 3 demo проекта — можно использовать.
- **Webhook manager.** Компонент `app/frontend/src/components/WebhookManager.tsx` в Sidebar. Для скрина нужно хотя бы 1 webhook в БД. CRUD через `POST /api/v1/webhooks`.
- **GitHub README vs HF README.** В репо один `README.md` с HF frontmatter сверху. И github.com, и HF Space читают один файл. Скрины ссылаются через relative path `docs/demo/<name>.png`. На HF путь должен работать через `raw.githubusercontent.com`; см. как уже сделано в существующем README (есть несколько ссылок на `raw.githubusercontent.com` если HF Space не тянет локальные binary).

## Deliverables

1. **Расширить `scripts/run_local_smoke.py`:**
   - Перед основным flow (после backend старта, перед import sample) запустить `python scripts/seed_demo_workspace.py --idempotent` через `subprocess.run` (не через импорт — изоляция окружения). Это гарантирует 3 проекта в БД.
   - Создать одну webhook-подписку через API (`POST /api/v1/webhooks` с `{"type":"slack","url":"https://hooks.slack.com/demo/placeholder","events":["analysis.completed"],"active":true}`). Secure mode учитывать: если smoke поднимает backend c `AB_API_TOKEN`, добавлять `Authorization: Bearer ...`.
   - После trinity существующих скринов добавить два новых шага:
     - **Comparison dashboard.** Перейти на `/compare` (или вызвать UI action «Compare saved projects»), выбрать 2 первых demo проекта из sidebar, дождаться рендера (timeout 15s, ждать `[data-testid="comparison-dashboard"]` или эквивалент — если нет testid, добавить его в `ComparisonDashboard.tsx`). Сохранить как `docs/demo/comparison-dashboard.png`, полная страница (full_page=True).
     - **Webhook manager.** Открыть Sidebar → секцию Webhooks (если есть collapsible), дождаться рендера webhook row, сохранить как `docs/demo/webhook-manager.png`.
   - Оба новых скрина использовать существующий паттерн `capture_success_screenshot(page, archive_name, stable_name)`.
   - Все старые 3 скрина **тоже** перегенерируются в рамках одного прогона smoke (они часть уже существующего flow).

2. **Locale switcher визуализация.**
   - До того как сделать `wizard-overview.png`, переключить язык на один из локалей (`en` или `ru` — не менять) **но** убедиться, что 4-кнопочный switcher виден в UI. Если не виден — проверить, что после seed/import language switcher не исчез (может быть скрыт в collapse).
   - Если в текущем layout switcher невидим в верхней части wizard страницы — НЕ делать UI-рефактор, просто задокументировать в отчёте и включить его в `comparison-dashboard.png` или отдельным скрином `locale-switcher.png` (если проще).

3. **Обновить `docs/demo/`:**
   - 5 PNG после прогона: `wizard-overview.png`, `review-step.png`, `results-dashboard.png`, `comparison-dashboard.png`, `webhook-manager.png`.
   - Разумное качество: viewport ≥ 1440×900, full_page где смысл есть (results, comparison). Не делать 4K — размер файла <500 KB per image, иначе GitHub render тормозит.
   - Если PNG >500KB — пропустить через `pngquant` / `oxipng` если доступны; если нет — оставить, но отметить в отчёте. **НЕ** коммитить lossy JPG.

4. **Обновить `README.md`:**
   - Секция `## Demo`:
     ```markdown
     ![Wizard overview](docs/demo/wizard-overview.png)
     ![Review step](docs/demo/review-step.png)
     ![Results dashboard](docs/demo/results-dashboard.png)
     ![Multi-project comparison](docs/demo/comparison-dashboard.png)
     ![Webhook manager](docs/demo/webhook-manager.png)
     ```
   - Сразу после блока скринов — короткий 3-строчный абзац: что показано в каждом и в каком порядке пользователь проходит по wizard.
   - HF Space версия README: проверить, не рендерит ли HF binary-ссылки через raw.githubusercontent (см. как сделано сейчас). Если да — продублировать `raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/docs/demo/<name>.png` для HF совместимости.

5. **Обновить `CHANGELOG.md`:**
   - Под разделом для `v1.1.0` (если Unreleased/Post-v1.1.0 секция существует — туда; иначе создать `### Unreleased` секцию) добавить 1 bullet: «Regenerated demo screenshots to match v1.1.0 UI (comparison dashboard, webhook manager).»

6. **Один коммит:**
   ```
   docs: regenerate demo screenshots for v1.1.0 ui and add comparison/webhook captures
   ```
   Co-Authored-By: Codex <noreply@anthropic.com>
   В коммит включить: обновлённые PNG, smoke script, README.md, CHANGELOG.md, этот CX-файл.

7. **Отчёт `docs/plans/2026-04-22-regenerate-screenshots-report.md`:**
   - Список файлов изменённых (с размерами PNG до/после).
   - Вывод smoke (сколько скринов, durations).
   - `scripts/verify_all.cmd --with-e2e` exit code.
   - Любые UI-нюансы, замеченные во время (data-testid которые пришлось добавить, collapse-hack для webhook).

## Acceptance
- После `scripts/verify_all.cmd --with-e2e` exit 0.
- `docs/demo/` содержит 5 PNG, все с mtime сегодняшней даты.
- Каждый PNG открывается как валидное изображение (`python -c "from PIL import Image; Image.open('docs/demo/comparison-dashboard.png').verify()"` = 0).
- Размер каждого PNG < 1 MB (мягкий лимит; warning в отчёте если больше).
- `README.md` содержит 5 корректных markdown image ссылок на обновлённые файлы.
- Коммит subject уникальный, CX-файл застейджен в тот же коммит.
- `git status --short` пусто.
- **НЕ** push на remote, **НЕ** upload на HF Space — юзер делает сам.

## How
1. Baseline: `git status --short` пусто, `scripts/verify_all.cmd` = 0.
2. Прочитать `scripts/run_local_smoke.py` целиком (существующий flow).
3. Прочитать `ComparisonDashboard.tsx`, `WebhookManager.tsx` — найти селекторы и testid.
4. Добавить seed-step и webhook-setup в smoke. Проверить, что `seed_demo_workspace.py` запускается из smoke без конфликта (если оба трогают один SQLite — seed первый).
5. Расширить Playwright flow: 2 новых скрина с waits на видимые элементы, не на `sleep`.
6. Локальный прогон `python scripts/run_local_smoke.py`. Итеративно чинить селекторы, если промахи.
7. Проверить размеры PNG, оптимизировать при необходимости (`pngquant --force --quality=85-95 -o docs/demo/<name>.png docs/demo/<name>.png` если установлен).
8. Обновить README, CHANGELOG.
9. `git add docs/demo/*.png scripts/run_local_smoke.py README.md CHANGELOG.md docs/plans/codex-tasks/2026-04-22-cx-regenerate-screenshots.md docs/plans/2026-04-22-regenerate-screenshots-report.md`.
10. Commit. `scripts/verify_all.cmd --with-e2e`. Отчёт.

## Notes
- **НЕ** делать UI-рефактор. Если data-testid отсутствует — добавить один-два минимальных testid без переструктурирования компонента.
- **НЕ** менять sample-project.json (используется smoke и документацией).
- **НЕ** менять поведение smoke для основных 3 скринов — только расширить.
- **НЕ** добавлять в smoke retry-loops с большими sleep; таймауты Playwright уже гибкие.
- Если `pngquant` недоступен — не ставить его как devDep. Либо уменьшить viewport, либо оставить как есть.
- При скрине comparison-dashboard — включить overlay с power-curve и forest-plot (они есть в UI v1.1.0), это визуально отличает скрин от старого results-dashboard.
- При скрине webhook-manager — не коммитить реальные webhook URLs. Использовать `https://hooks.slack.com/demo/placeholder` как sample.
- После коммита — оставить smoke-артефакты в `app/frontend/playwright-smoke-artifacts/` (они в `.gitignore` уже). Не пушить их.
- HF Space не рендерит binary из PR-веток; после merge на main images подтянутся автоматически через `raw.githubusercontent.com` в следующий рестарт Space.

## Out of scope
- Видео/GIF превью (отдельный будущий таск).
- Редизайн `ComparisonDashboard.tsx` / `WebhookManager.tsx`.
- Translation screenshots для de/es (их UI частичный, ждёт Tier 2 #6 full translation).
- Обновление `docs/demo/sample-project.json`.
- Deploy на HF Space (юзер сам).
