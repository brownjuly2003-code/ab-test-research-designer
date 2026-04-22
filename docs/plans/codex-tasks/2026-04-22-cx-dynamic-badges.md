# CX Task: Dynamic quality-gate badges for README

## Goal
Заменить статические placeholder-бейджи в `README.md` на динамические shields.io бейджи, которые реально отражают актуальное состояние проекта: (1) количество проходящих тестов, (2) coverage %, (3) Lighthouse performance score. Бейджи обновляются автоматически через GitHub Actions workflow, который после каждого зелёного run'а пишет значения в gist / в JSON-файл в репо, а shields.io читает их через endpoint-badge.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `14259fff` (tag `v1.1.0`). Не ветка, не push.
- **Текущие бейджи в README (строки 14-17):**
  ```
  [![Release](...)] [![License: MIT](...)] [![Python](...)] [![Node](...)]
  ```
  — Release/License/Python/Node остаются. Добавить 3 **новых** динамических; не трогать существующие.
- **Existing CI workflow.** `.github/workflows/test.yml` — 3 job (verify ubuntu+windows, docker, lighthouse). Lighthouse job уже пишет артефакты в `.lighthouseci/` — оттуда можно вычленить score.
- **Test count.** Backend: `pytest` в `app/backend/tests/` — запуск через `python scripts/verify_all.py`. Сейчас 233+ backend tests. Frontend: vitest в `app/frontend/` — 200+. Суммарно можно писать как «tests: 433+» или разбить на два бейджа (backend / frontend). Предпочтение: один бейдж «tests: 433 passed».
- **Coverage.** В репо **пока** нет coverage run в CI. Нужно добавить `pytest --cov=app/backend/app --cov-report=json:coverage-backend.json` в `verify` job. Frontend coverage (vitest) — опционально, если легко; иначе только backend.
- **Lighthouse.** `scripts/run_lighthouse_ci.py` уже запускает Lighthouse CI и ассертит pass. Извлечь `performance` score из результата (обычно 0..1, формат × 100 для бейджа).
- **Endpoint для shields.io.** Два варианта:
  - **(A) JSON-файл в репо.** CI записывает `badges/metrics.json`, shields.io читает через `https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/.../badges/metrics.json&query=$.tests.label`. Плюс: всё в репо, воспроизводимо, нет внешних зависимостей. Минус: CI коммитит обратно в main (нужен `github-actions[bot]` commit на `badges/` — чисто).
  - **(B) GitHub Gist.** CI пушит в gist через token. Плюс: нет auto-commits в main. Минус: требует secret `GIST_TOKEN`.
  - **Выбор CX — вариант (A)** (самодостаточно, без дополнительных secrets). CI коммитит только `badges/metrics.json`, skip CI loop через `[skip ci]` в commit message.

## Deliverables

1. **Новый job в `.github/workflows/test.yml` (или отдельный `metrics.yml`):**
   - Job `update-metrics-badges`:
     - `needs: [verify, lighthouse]` — только если оба зелёные.
     - `if: github.ref == 'refs/heads/main' && github.event_name == 'push'` — обновлять только на main push, не на PR.
     - Permissions: `contents: write`.
     - Steps:
       1. `actions/checkout@v4` (full history, `fetch-depth: 0`).
       2. Install Python deps.
       3. Download artifact `lighthouseci` (существует уже в lighthouse job — но сейчас он `upload-artifact`, надо проверить что доступен в другом job через `actions/download-artifact`).
       4. Download coverage artifact (будет добавлен в verify job — см. пункт 2).
       5. Собрать метрики скриптом `scripts/collect_badge_metrics.py`:
          - tests: количество passed (парсинг pytest `--tb=no -q` output или json-report).
          - coverage: process `coverage-backend.json`.
          - lighthouse: process `.lighthouseci/manifest.json` → avg `performance` score.
          - Вывод: `badges/metrics.json` с структурой:
            ```json
            {
              "tests": {"schemaVersion": 1, "label": "tests", "message": "433 passed", "color": "green"},
              "coverage": {"schemaVersion": 1, "label": "coverage", "message": "87%", "color": "green"},
              "lighthouse": {"schemaVersion": 1, "label": "lighthouse", "message": "94", "color": "green"}
            }
            ```
          - Color thresholds: coverage ≥80% green / 60-79 yellow / <60 red; lighthouse ≥90 green / 70-89 yellow / <70 red; tests — всегда green пока > 0.
       6. Коммит `badges/metrics.json` обратно в main если есть diff, с user `github-actions[bot]` и subject `chore: update badge metrics [skip ci]`. Использовать `stefanzweifel/git-auto-commit-action@v5` (стабильная, широко используется) ИЛИ вручную `git add && git commit && git push` — выбрать вручную для минимальных зависимостей.

2. **Coverage run в существующем `verify` job:**
   - Модифицировать `scripts/verify_all.py` (или добавить флаг `--with-coverage`), чтобы на Ubuntu прогон писал `coverage-backend.json`.
   - В CI verify job при `matrix.os == 'ubuntu-latest'` — загружать артефакт `coverage-backend.json` через `actions/upload-artifact@v4`.
   - Coverage не должен ломать Windows run (если проще — гонять coverage только на Ubuntu).
   - Порог coverage — **не ввести gate сейчас**, только репортинг. Иначе зелёный CI может упасть на первом же run.

3. **Скрипт `scripts/collect_badge_metrics.py`:**
   - CLI: `python scripts/collect_badge_metrics.py --coverage coverage-backend.json --lighthouse .lighthouseci/manifest.json --test-results <путь к junit xml или pytest summary> --output badges/metrics.json`
   - Устойчив к частично отсутствующим входам: если coverage.json нет — пишет `message: "n/a"`, `color: lightgrey`, не падает. Логика — это про обновление бейджей, не про тест-ран.
   - Генерирует 3 shields.io endpoint JSON schema (schemaVersion 1).

4. **Обновить `README.md`:**
   - Добавить 3 бейджа рядом с существующими:
     ```markdown
     [![Tests](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/badges/metrics.json&query=$.tests&label=tests)](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/workflows/test.yml)
     [![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/badges/metrics.json&query=$.coverage&label=coverage)](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/workflows/test.yml)
     [![Lighthouse](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/badges/metrics.json&query=$.lighthouse&label=lighthouse)](https://github.com/brownjuly2003-code/ab-test-research-designer/actions/workflows/test.yml)
     ```
   - **Важно.** Каждый бейдж — отдельный query на отдельный подобъект. Проверить actual синтаксис shields.io endpoint (`query` использует jq-like path: `$.tests.message` если нужно значение, либо `$.tests` если shields.io сам читает весь schemaVersion payload — сейчас второй вариант корректен).

5. **Инициализация `badges/metrics.json`:**
   - Создать файл руками в этом коммите с placeholder-значениями (tests: n/a, coverage: n/a, lighthouse: n/a). CI при первом run обновит. Иначе shields.io в первый раз вернёт 404.

6. **Один коммит:**
   ```
   ci: add dynamic tests/coverage/lighthouse badges via shields.io endpoint
   ```
   Co-Authored-By: Codex <noreply@anthropic.com>
   В коммит: `.github/workflows/test.yml`, `scripts/collect_badge_metrics.py`, `scripts/verify_all.py` (если нужен `--with-coverage`), `app/backend/requirements.txt` (если coverage dep добавлен), `README.md`, `badges/metrics.json`, этот CX-файл, отчёт.

7. **Отчёт `docs/plans/2026-04-22-dynamic-badges-report.md`:**
   - Список файлов.
   - Вывод `collect_badge_metrics.py` на локальных данных (запустить локально, чтобы показать, что работает).
   - YAML-валидация workflow.
   - `scripts/verify_all.cmd --with-e2e` exit 0.
   - Инструкция юзеру: после push на main первый CI run обновит `badges/metrics.json`, через 2-3 минуты shields.io показывает реальные значения. shields.io кеширует 300s; в первый раз можно форсить через `?cacheSeconds=0`.

## Acceptance
- `.github/workflows/test.yml` (или отдельный workflow) содержит job `update-metrics-badges` с правильным `needs` и `if`.
- `scripts/collect_badge_metrics.py` запускается локально без аргументов с тестовым JSON и не падает на missing inputs.
- `badges/metrics.json` существует в коммите с schemaVersion 1 JSON.
- `README.md` содержит 3 новых бейджа через shields.io endpoint.
- YAML валиден (`python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"` exit 0).
- `scripts/verify_all.cmd --with-e2e` exit 0 (нельзя ломать существующий pipeline).
- Local dry-run: `python scripts/collect_badge_metrics.py --output /tmp/m.json` с минимальными входами → валидный JSON, 3 ключа.
- Коммит subject уникальный. CX-файл застейджен. `git status --short` пусто.
- **НЕ** push на remote.

## How
1. Baseline: `git status --short` пусто, verify = 0.
2. Прочитать `.github/workflows/test.yml`, `scripts/verify_all.py`, `scripts/run_lighthouse_ci.py`. Понять формат `.lighthouseci/manifest.json`.
3. Написать `scripts/collect_badge_metrics.py`. Локальный прогон с моками.
4. Добавить coverage run в `verify_all.py` (через `pytest-cov`, если ещё нет — добавить в `requirements.txt`; проверить сейчас). Не гейт.
5. Добавить job в `test.yml`. Валидировать YAML.
6. Создать `badges/metrics.json` с placeholder.
7. Обновить `README.md` — 3 новых бейджа.
8. Локальный полный verify.
9. Коммит, отчёт.

## Notes
- **Лицензия shields.io endpoint.** Бесплатно для публичных репо. Rate-limit ~60req/min per IP, кешируется на shields side. Для README-прогрузки — неважно.
- **shields.io schemaVersion 1 format.** Корневой объект `{"schemaVersion":1,"label":"...","message":"...","color":"..."}`. Мы вкладываем это как `$.tests` / `$.coverage` / `$.lighthouse`. shields.io читает через `query=$.tests` — но по доке endpoint ждёт root-level schemaVersion. Проверить: если endpoint query не работает — разделить на 3 файла `badges/tests.json`, `badges/coverage.json`, `badges/lighthouse.json`. Предпочтительно один файл, но fallback на три — допустим, если shields.io query не парсит.
- **Auto-commit loop.** `[skip ci]` в commit message обязателен, иначе каждый update триггерит новый verify → новый update → infinite loop.
- **Permissions.** `contents: write` даёт `github-actions[bot]` пушить в main. Если в репо защищена main branch — юзер должен allow github-actions bot (записать в отчёт как pre-req).
- **Auto-commit action choice.** `stefanzweifel/git-auto-commit-action@v5` — популярная, надёжная, не тянет лишнего. Альтернатива — 3 строки bash (`git add && git commit && git push`). Выбрать по вкусу; auto-commit action понятнее.
- **Не** делать coverage gate сейчас. Покажем число, дальше решим threshold.
- **Не** добавлять frontend coverage если это 40+ минут дополнительной работы — оставить как follow-up.
- **Не** использовать секретов, кроме auto-provided `GITHUB_TOKEN`.
- **Не** менять dockerhub-бейджи / release-бейджи (они статичны уже работают).
- Если `pytest-cov` уже есть в `requirements.txt` — переиспользовать; не дубль.
- Локальный тест shields.io endpoint после push — через curl: `curl 'https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/main/badges/metrics.json&query=$.tests'` → вернёт SVG.

## Out of scope
- Frontend coverage badge (если не тривиально).
- Build-time / bundle-size badge.
- Licence scan badge.
- Dependabot / Renovate setup.
- Coverage gate (блокирующий порог).
- Security scan badges (Snyk / Dependabot alerts).
- README redesign за пределами добавления 3 строк бейджей.
