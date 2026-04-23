# CX Task: Починить lighthouse → update-metrics-badges артефакт pipeline

## Goal
`update-metrics-badges` CI job падает на шаге `Download Lighthouse artifact` с ошибкой `Artifact not found for name: lighthouseci`. Root cause: job `lighthouse` логирует `##[warning]No files were found with the provided path: .lighthouseci/. No artifacts will be uploaded` — `actions/upload-artifact@v4` не находит файлов, хотя `lhci autorun` завершается успехом ("Uploading median LHR of http://127.0.0.1:4174/...success!", score 97). Цель — разобраться, почему `.lighthouseci/` на runner'е пустой после autorun с `upload.target = "temporary-public-storage"`, и починить так, чтобы `manifest.json` (или альтернативный вход для `scripts/collect_badge_metrics.py`) оказывался в artifact.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `f1316300`.
- **Падающий run.** `24815566631` (https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/24815566631). `verify` (Ubuntu + Windows) зелёный, `docker` зелёный, `lighthouse` зелёный (score 97, upload в temp-public-storage success), `update-metrics-badges` красный с `Unable to download artifact(s): Artifact not found for name: lighthouseci`.
- **Файлы в игре:**
  - `.github/workflows/test.yml` — jobs `lighthouse` (строки 87-125) и `update-metrics-badges` (127-180).
  - `scripts/run_lighthouse_ci.py` — запускает backend на порту 4174, делает `npx --yes @lhci/cli@0.14.0 autorun --collect.url=...` с `cwd=ROOT_DIR`.
  - `.lighthouserc.json` — конфиг:
    ```json
    {
      "ci": {
        "collect": { "url": ["http://127.0.0.1:4174/"], "numberOfRuns": 3, "settings": { "preset": "desktop", "skipAudits": ["uses-http2", "canonical"] } },
        "assert": { "assertions": { "categories:performance": ["warn", {"minScore": 0.85}], "categories:accessibility": ["error", {"minScore": 0.9}], "categories:best-practices": ["warn", {"minScore": 0.9}], "categories:seo": ["warn", {"minScore": 0.8}] } },
        "upload": { "target": "temporary-public-storage" }
      }
    }
    ```
  - `scripts/collect_badge_metrics.py` — функция `lighthouse_score(path)`. После недавнего фикса `117ae639` читает либо `manifest.json` (основной), либо fallback `lhr-*.json` из той же директории.
- **Что уже точно НЕ работает:**
  - Artifact upload path `.lighthouseci/` — директория существует (preflight "✅ .lighthouseci/ directory writable"), но после autorun в ней нет файлов.
  - fallback на `lhr-*.json` из collect_badge_metrics — бесполезен, т. к. их тоже нет в artifact (нечего скачивать).
- **Гипотезы причины (в порядке вероятности, каждую надо подтвердить/опровергнуть, не угадывать):**
  1. `upload.target = "temporary-public-storage"` в lhci 0.14 запускает cleanup локальных `.lighthouseci/*.json` после успешной загрузки во внешнее хранилище. Проверяется: после `lhci autorun` добавить шаг `ls -la .lighthouseci/` и посмотреть, пусто ли, или там что-то есть, но не на ожидаемом пути.
  2. `lhci autorun` с `@lhci/cli` установленным через `npm install -g` (строка 114 workflow) может использовать глобальный рабочий каталог, а не `cwd` Python-процесса. Проверяется тем же `ls` + `find / -name 'lhr-*.json' 2>/dev/null` на runner'е.
  3. `npx --yes @lhci/cli@0.14.0 autorun` (из скрипта) в CI не работает, потому что глобальный `@lhci/cli` уже установлен, и npx делегирует туда с другим cwd. Проверяется заменой на прямой `lhci autorun`.
- **Известные рабочие факты из локального запуска** (Windows, Python 3.13): после `python scripts/run_lighthouse_ci.py` локально файлы `.lighthouseci/lhr-*.json` и HTML отчёты **появляются** в рабочей папке, badge `lighthouse.json` собирается со score 97. Значит lhci при той же конфигурации локально файлы держит — поведение в Ubuntu CI чем-то отличается.

## Deliverables

### Шаг 1: Диагностический прогон CI (обязателен, не пропускать)
Добавить в `.github/workflows/test.yml` в job `lighthouse` между "Run Lighthouse CI" и "Upload Lighthouse artifacts" новый шаг:
```yaml
- name: Diagnose lighthouse output location
  if: always()
  run: |
    set -x
    echo "== CWD =="
    pwd
    echo "== .lighthouseci/ listing =="
    ls -la .lighthouseci/ 2>&1 || echo "missing"
    echo "== find all lhr-*.json on runner =="
    find / -name 'lhr-*.json' 2>/dev/null | head -30
    echo "== find all manifest.json near .lighthouseci =="
    find / -path '*/lighthouseci*/manifest.json' 2>/dev/null | head -30
    echo "== lhci version =="
    lhci --version 2>&1 || true
    echo "== npm config =="
    npm config get prefix
```
Push, дождаться прогона, посмотреть `gh run view <id> --job <lighthouse-job-id> --log | grep -A 100 "Diagnose lighthouse"`. **Не коммитить фикс до тех пор, пока не увидели реальный location файлов.** Отчёт — 1 параграф про фактическое поведение (где лежат файлы, пуст ли `.lighthouseci/`, какие пути нашёл `find`).

### Шаг 2: Фикс — один из двух путей в зависимости от диагностики

**Путь A — если файлы лежат в `.lighthouseci/` но upload-artifact их не видит (права / глоб-паттерн):**
- Заменить `path: .lighthouseci/` на явный `path: .lighthouseci/**` (glob подхватит содержимое напрямую, а не каталог как directory-placeholder).
- Либо добавить `include-hidden-files: true`, если проблема в dot-префиксе (маловероятно, `.lighthouseci` — не dotfile в glob-смысле, но проверить).

**Путь B — если файлы не создаются в `.lighthouseci/` из-за temporary-public-storage target:**
- Вариант B1 (минимальный): после `python scripts/run_lighthouse_ci.py` добавить шаг, который парсит stdout lhci на URL `https://storage.googleapis.com/lighthouse-infrastructure.appspot.com/reports/*.report.html` (или соответствующий JSON-отчёт), скачивает JSON через `curl` в `.lighthouseci/lhr-median.json`, и генерирует минимальный `.lighthouseci/manifest.json` вида:
  ```json
  [{"url":"http://127.0.0.1:4174/","isRepresentativeRun":true,"jsonPath":"lhr-median.json","summary":{"performance":0.97,"accessibility":0.9,"best-practices":0.9,"seo":0.8}}]
  ```
  `collect_badge_metrics.py` уже умеет читать такой манифест.
- Вариант B2 (предпочтительнее, если lhci CLI поддерживает): вызывать `lhci autorun` с флагом `--upload.target=filesystem --upload.outputDir=.lighthouseci` — это ДОБАВИТ filesystem target к существующему temp-public-storage через CLI override, и filesystem target явно пишет `manifest.json`. Проверить через локальный прогон, что оба upload'а срабатывают (в stdout должны быть обе строки — "Uploading median LHR...success!" И запись в filesystem).
- Вариант B3 (альтернатива B2, если B2 не сработает): перейти на `lhci collect` + `lhci assert` + два отдельных `lhci upload` (один `temporary-public-storage`, второй `filesystem`). Это вариант с максимальным контролем. Менять `run_lighthouse_ci.py`, не `.lighthouserc.json`.

### Шаг 3: Проверить, что `scripts/collect_badge_metrics.py` действительно парсит результат
- Локально: `python scripts/run_lighthouse_ci.py` → `python scripts/collect_badge_metrics.py --lighthouse .lighthouseci/manifest.json ...` → `badges/lighthouse.json` со score 97.
- Если путь к manifest'у меняется (например, filesystem target кладёт его в `.lighthouseci/lhci-reports/manifest.json`) — обновить команду в workflow step "Refresh badge payloads" на фактический путь.

### Шаг 4: Удалить диагностический шаг из шага 1
Отдельным коммитом: `chore(ci): remove lighthouse output diagnostics after root cause fix`.

## Acceptance
- CI run на `main` после push показывает: `verify` (оба) ✅, `docker` ✅, `lighthouse` ✅ (as before), `update-metrics-badges` ✅ (это главное).
- В последнем коммите от бота `github-actions[bot]` обновлён `badges/lighthouse.json` с числовым score, не `n/a`.
- `gh run view <id> --job <update-metrics-badges-job-id> --log | grep -i "error\|warning"` не содержит "Artifact not found" и "No files were found".
- Локально: `python scripts/run_lighthouse_ci.py && python scripts/collect_badge_metrics.py --lighthouse .lighthouseci/manifest.json --coverage .ci-artifacts/coverage-backend.json --test-results .ci-artifacts/backend-junit.xml --test-results .ci-artifacts/frontend-junit.xml --output badges/metrics.json` → exit 0, `badges/metrics.json` со всеми тремя score.
- Коммиты (в указанном порядке):
  1. `ci(lighthouse): temporary diagnostics step to locate lhci output on runner` (содержит только добавление диагностики)
  2. `fix(ci): preserve lhci manifest for update-metrics-badges job` (содержит реальный фикс)
  3. `chore(ci): remove lighthouse output diagnostics after root cause fix` (удаление диагностики)

## Notes
- НЕ переходить на `lhci upload --target=lhci-server` (это собственный сервер LHCI, требует дополнительной инфраструктуры).
- Не удалять `temporary-public-storage` из `.lighthouserc.json` — пользователи используют публичный URL отчёта для проверки состояния прод UI, это feature, не bug. Filesystem target добавляется ПАРАЛЛЕЛЬНО.
- Если в ходе диагностики обнаружится, что lhci пишет в `/tmp/lhci-*` или `$HOME/.lighthouseci/` — адаптировать upload-artifact path, не перемещать файлы вручную.
- `npx --yes @lhci/cli@0.14.0` в `run_lighthouse_ci.py` можно заменить на прямой `lhci` (глобально установлен в step "Install Lighthouse CI" workflow'а) — возможно, это и есть корень проблемы (npx создаёт sandboxed env). Если так — это часть фикса в шаге 2.
- Отчёт в конце (15-20 строк): что показала диагностика (п. 1), какой путь фикса выбран (A / B1 / B2 / B3), финальный run-id зелёного CI, значение lighthouse score в boots badge'е.
