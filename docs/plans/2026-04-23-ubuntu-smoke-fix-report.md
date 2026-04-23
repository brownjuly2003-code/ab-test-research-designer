# 2026-04-23 Ubuntu smoke fix report

## Что было root cause

Реальный root cause Ubuntu/Windows smoke failure был **не в seed path**.

- `_read_bool_env("AB_SEED_DEMO_ON_STARTUP", False)` принимает строку `"true"` и возвращает `True`.
- В воспроизведении на Windows backend startup логировал тот же `db_path`, что и `temp_db_path` smoke-run:
  `D:\AB_TEST\archive\smoke-runs\20260423-062722\projects.sqlite3`.
- В том же run backend логировал `demo-seed: completed analyzed_projects=3 created_projects=3 exported_projects=1 skipped_projects=0` до browser flow.
- До UI-шага smoke уже успешно видел seeded проекты через API и дообогащал два проекта observed results + analysis snapshots.

Падал не seed, а **устаревший Playwright selector** в `scripts/run_local_smoke.py`:

- smoke искал comparison checkboxes через `[role="option"] input[type="checkbox"]`;
- фактический DOM dump из `archive/smoke-runs/20260423-062722/smoke-failure.html` показывал 3 реальных checkbox-а в sidebar как обычные
  `<label><input type="checkbox"><span>Select for comparison</span></label>`;
- в текущем UI нет `role="option"`, поэтому locator возвращал `0`, хотя comparison-ready проекты уже были на экране.

Итог: подозрения про bool parser / startup race / SQLite path drift не подтвердились; настоящая причина была в **stale smoke selector against updated sidebar markup**.

## Что изменено

1. `scripts/run_local_smoke.py`
   Перевёл выбор comparison checkbox-ов на актуальный accessible locator
   `get_by_role("checkbox", name="Select for comparison")`.
   Добавил ожидание второго checkbox-а и ожидание enable-state для
   `#compare-selected-projects-button`, чтобы шаг не кликал раньше UI-state update.

2. `.github/workflows/test.yml`
   Добавил `Upload smoke failure dump` под `verify` job для Ubuntu-падений,
   чтобы следующий failure на `main` всегда приносил `archive/smoke-runs/`.

3. `scripts/collect_badge_metrics.py`
   Добавил fallback: если переданный `manifest.json` отсутствует, скрипт
   читает Lighthouse score напрямую из `.lighthouseci/lhr-*.json`.
   Это понадобилось для реальных live badge numbers: локальный `lhci autorun`
   писал `lhr-*.json`, `links.json`, `assertion-results.json`, но не
   `manifest.json`.

4. `badges/*.json`
   Локально пересобраны payload-ы после smoke/e2e/backend/lighthouse прогонов.

## Доказательства

### Падавший run

- `python scripts/run_local_smoke.py --skip-build`
- failure artifacts:
  - `archive/smoke-runs/20260423-062722/smoke-failure.png`
  - `archive/smoke-runs/20260423-062722/smoke-failure.html`
  - `archive/smoke-runs/20260423-062722/smoke.log`

### Успешный run после фикса

- `python scripts/run_local_smoke.py --skip-build`
- passed run:
  - `archive/smoke-runs/20260423-063014/`
- в логе после фикса есть успешный `POST /api/v1/projects/compare` и итоговый
  `Smoke test passed`.

### Локальная верификация

- backend: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m coverage run -m pytest app/backend/tests -q --junitxml .ci-artifacts/backend-junit.xml` -> `236 passed`
- coverage json: `.ci-artifacts/coverage-backend.json`
- frontend typecheck: `npm --prefix app/frontend exec tsc -- --noEmit -p D:\AB_TEST\app\frontend` -> `0`
- frontend unit: `npm --prefix app/frontend run test:unit -- --reporter=junit --outputFile=D:\AB_TEST\.ci-artifacts\frontend-junit.xml` -> `0`
- frontend e2e: `python scripts/run_frontend_e2e.py --skip-build` -> `Playwright E2E passed`
- lighthouse: `python scripts/run_lighthouse_ci.py` -> `0`

Полный `python scripts/verify_all.py --skip-build --with-e2e --with-coverage --artifacts-dir .ci-artifacts`
локально не добежал из-за внешнего env issue: глобальный `schemathesis` pytest plugin
в этом Python окружении требует отсутствующий `_pytest.subtests`.
Это не связано с внесёнными правками; поэтому проверки были прогнаны теми же
составляющими напрямую.

## Badge metrics

Локальная пересборка:

```bash
python scripts/collect_badge_metrics.py \
  --coverage D:\AB_TEST\.ci-artifacts\coverage-backend.json \
  --lighthouse D:\AB_TEST\.lighthouseci\manifest.json \
  --test-results D:\AB_TEST\.ci-artifacts\backend-junit.xml \
  --test-results D:\AB_TEST\.ci-artifacts\frontend-junit.xml \
  --output D:\AB_TEST\badges\metrics.json
```

Итоговый `badges/metrics.json`:

```json
{
  "tests": { "label": "tests", "message": "447 passed", "color": "green" },
  "coverage": { "label": "coverage", "message": "95%", "color": "green" },
  "lighthouse": { "label": "lighthouse", "message": "97", "color": "green" }
}
```

Это подтверждает, что badge payloads больше не placeholder (`"n/a"` /
`"lightgrey"`), если workflow доходит до badge refresh step.
