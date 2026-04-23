# CX Task: Публичный docs site на mkdocs-material + GitHub Pages

## Goal
Поднять приличный docs-сайт для проекта на `mkdocs-material`, опубликовать на GitHub Pages (`brownjuly2003-code.github.io/ab-test-research-designer`). Сейчас вся документация разбросана по `docs/*.md`, `README.md`, `CHANGELOG.md`, `docs/plans/codex-tasks/*.md` — нормально для contributors, но для потенциального пользователя (рекрутер / коллега-DS / соискатель-работодатель) это недружественно. Tier 2 roadmap #3 из README.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `1e8472b0`.
- **Существующая документация** (полезная для сайта):
  - `README.md` — top-level overview + badges + roadmap.
  - `CHANGELOG.md` — release log.
  - `docs/API.md` — REST API reference (генерится из FastAPI OpenAPI).
  - `docs/HISTORY.md` — архитектурная история проекта.
  - `docs/RELEASE_CHECKLIST.md` — operational.
  - `docs/RUNBOOK.md` — operational.
  - `docs/case-studies/checkout-redesign.json` + `docs/case-studies/checkout-redesign.md` (если есть).
  - Demo screenshots: `docs/demo/{wizard-overview,review-step,results-dashboard,comparison-dashboard,webhook-manager}.png`.
- **НЕ включать** в публичный site:
  - `docs/plans/codex-tasks/*.md` — внутренние CX ТЗ, dev artefact.
  - `archive/**/*.md` — архивные планы, не для пользователя.
  - `docs/plans/2026-*.md` — внутренние sprint планы.
- **GitHub Pages config.** Репо публичный, Pages сейчас, вероятно, не настроен (проверить через `gh api repos/brownjuly2003-code/ab-test-research-designer/pages` — 404 значит не настроен).
- **Публикация через GitHub Actions.** `mkdocs gh-deploy` в отдельном workflow, trigger на push в `main` + ручной workflow_dispatch. Не лить docs через commit в `gh-pages` branch напрямую из локалки.

## Deliverables

1. **`mkdocs.yml` в корне репо:**
   ```yaml
   site_name: A/B Test Research Designer
   site_description: FastAPI + React A/B-testing experiment designer. Bayesian + frequentist statistics, comparison dashboard, webhooks, multi-language UI.
   site_url: https://brownjuly2003-code.github.io/ab-test-research-designer/
   repo_url: https://github.com/brownjuly2003-code/ab-test-research-designer
   repo_name: brownjuly2003-code/ab-test-research-designer
   edit_uri: edit/main/docs/

   theme:
     name: material
     palette:
       - media: "(prefers-color-scheme: light)"
         scheme: default
         primary: indigo
         toggle:
           icon: material/weather-sunny
           name: Switch to dark mode
       - media: "(prefers-color-scheme: dark)"
         scheme: slate
         primary: indigo
         toggle:
           icon: material/weather-night
           name: Switch to light mode
     features:
       - navigation.instant
       - navigation.tabs
       - navigation.top
       - content.code.copy
       - content.code.annotate

   markdown_extensions:
     - admonition
     - pymdownx.details
     - pymdownx.superfences:
         custom_fences:
           - name: mermaid
             class: mermaid
             format: !!python/name:pymdownx.superfences.fence_code_format
     - pymdownx.highlight
     - pymdownx.inlinehilite
     - pymdownx.tabbed:
         alternate_style: true
     - toc:
         permalink: true

   nav:
     - Home: index.md
     - Getting Started:
         - Quickstart: getting-started/quickstart.md
         - Configuration: getting-started/configuration.md
         - Deploy: getting-started/deploy.md
     - Features:
         - Wizard flow: features/wizard.md
         - Results dashboard: features/results.md
         - Multi-project comparison: features/comparison.md
         - Webhooks: features/webhooks.md
         - Localization: features/localization.md
     - Reference:
         - REST API: reference/api.md
         - Architecture: reference/architecture.md
         - Statistics methods: reference/statistics.md
     - Case Studies:
         - Checkout redesign: case-studies/checkout-redesign.md
     - Operations:
         - Runbook: operations/runbook.md
         - Release checklist: operations/release-checklist.md
     - Changelog: changelog.md

   plugins:
     - search
     - mermaid2
   ```

2. **Создать содержимое страниц под `docs/` (или отдельный `docs-site/` корень — см. Notes):**
   - `index.md` — копия top-part `README.md` (overview + key features + badges), без roadmap / contributor blocks.
   - `getting-started/quickstart.md` — 5-минутный setup (локально через `docker-compose up`, или через `scripts/verify_all.py --skip-build`).
   - `getting-started/configuration.md` — все env vars (`AB_ENV`, `AB_DB_PATH`, `AB_PORT`, `AB_SEED_DEMO_ON_STARTUP`, HF-связанные если задача HF snapshot landed).
   - `getting-started/deploy.md` — Docker + HF Spaces + `ghcr.io` (на базе текущего `Dockerfile` + `docker-compose.yml` + `fly.toml`).
   - `features/wizard.md` — скриншот `wizard-overview.png` + описание шагов Wizard.
   - `features/results.md` — скриншот `results-dashboard.png` + frequentist/Bayesian metrics.
   - `features/comparison.md` — скриншот `comparison-dashboard.png` + multi-project diff.
   - `features/webhooks.md` — скриншот `webhook-manager.png` + HMAC/Slack примеры.
   - `features/localization.md` — список локалей (en/ru full, de/es partial или full в зависимости от того, landed ли translation task), `regional fallback`.
   - `reference/api.md` — включить `docs/API.md` либо через `{% include %}` либо регенерировать из OpenAPI (проверить, как сейчас генерится).
   - `reference/architecture.md` — диаграмма mermaid (`flowchart LR`): React SPA → FastAPI → SQLite; LLM adapters; webhook service; comparison service. Плюс ссылка на `docs/HISTORY.md`.
   - `reference/statistics.md` — краткий overview методов (frequentist t-test, Bayesian beta-binomial, SRM χ², sequential, CUPED). Можно перенести из backend docstrings / статей.
   - `case-studies/checkout-redesign.md` — перенести существующий из `docs/case-studies/`.
   - `operations/runbook.md` — ссылка / mirror `docs/RUNBOOK.md`.
   - `operations/release-checklist.md` — mirror `docs/RELEASE_CHECKLIST.md`.
   - `changelog.md` — включение `CHANGELOG.md` из корня (можно через symlink или через mkdocs include plugin).

   **Не писать страницы с нуля там, где уже есть готовый markdown.** Использовать `{% include %}` через `mkdocs-include-markdown-plugin` (добавить в requirements) или прямой `cp` / симлинк — выбрать один подход и применять везде.

3. **`docs-site-requirements.txt`** (отдельный файл рядом с `mkdocs.yml`):
   ```
   mkdocs==1.6.1
   mkdocs-material==9.5.40
   mkdocs-mermaid2-plugin==1.2.1
   mkdocs-include-markdown-plugin==6.2.2
   ```

4. **`.github/workflows/docs.yml`** — новый workflow:
   ```yaml
   name: Deploy docs

   on:
     push:
       branches: [main]
       paths:
         - docs/**
         - mkdocs.yml
         - docs-site-requirements.txt
         - README.md
         - CHANGELOG.md
     workflow_dispatch:

   permissions:
     contents: write

   concurrency:
     group: pages
     cancel-in-progress: true

   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: "3.13"
         - run: python -m pip install -r docs-site-requirements.txt
         - run: mkdocs gh-deploy --force --clean --verbose
   ```

5. **GitHub Pages включить:**
   ```bash
   gh api -X POST repos/brownjuly2003-code/ab-test-research-designer/pages \
     -f "source[branch]=gh-pages" -f "source[path]=/"
   ```
   (или через Settings → Pages UI — выбрать "Deploy from a branch", `gh-pages`, `/` root). Сделать однократно — дальше workflow пушит в `gh-pages`.

6. **README.md top:**
   - Добавить badge: `[![Docs](https://img.shields.io/badge/docs-mkdocs--material-blue)](https://brownjuly2003-code.github.io/ab-test-research-designer/)`.
   - В секции "Roadmap" у пункта "mkdocs-material documentation site" заменить текст на "✅ Published at brownjuly2003-code.github.io/ab-test-research-designer/".

## Acceptance
- `pip install -r docs-site-requirements.txt && mkdocs serve` локально — http://127.0.0.1:8000 работает, все nav-ссылки открываются, нет 404.
- `mkdocs build --strict` → exit 0 (`--strict` ловит любые broken links / missing files).
- Первый push в `main` триггерит workflow `Deploy docs`, job ✅, `gh-pages` branch создан, https://brownjuly2003-code.github.io/ab-test-research-designer/ возвращает 200 с реальным контентом (проверить через `curl -s -I <url>` и `curl -s <url> | grep -i "ab-test"`).
- Badge в README отображается и ведёт на живой сайт.
- Существующие CI workflows (`test.yml`, `docker-publish.yml`) **не сломаны** — новый `docs.yml` не влияет на них (разные paths-триггеры).
- Один коммит или серия связанных коммитов (по желанию):
  - `docs: initial mkdocs-material site structure`
  - `ci(docs): add github pages deployment workflow`
  - `docs(readme): link to published docs site`

## Notes
- **Docs location.** Можно класть содержимое прямо под `docs/` (mkdocs использует его по умолчанию), ИЛИ перенести в `docs-site/` и указать `docs_dir: docs-site` в `mkdocs.yml` чтобы не конфликтовать с существующим `docs/` (который содержит dev-документацию, plans и т. п.). **Выбрать второй вариант** — `docs-site/`, чтобы `docs/plans/`, `docs/case-studies/` и прочее не попадало в публичный site автоматически. Обновить пути в `nav:` и workflow соответственно.
- **`edit_uri`** должен указывать на `edit/main/docs-site/` (если выбран второй вариант) — чтобы "Edit this page" ссылки в footer открывали редактор GitHub в правильной папке.
- **Images.** Скриншоты из `docs/demo/` — положить под `docs-site/assets/screenshots/` и ссылаться относительно. Если копировать большие PNG — не блочит деплой.
- **Не писать новый README для docs site.** `index.md` — копия / include из `README.md`, чтобы не было дрейфа.
- **Не деплоить в custom домен.** Default `github.io/<repo>/` subpath — достаточно.
- Отчёт (20 строк): live URL, первый deploy commit, `mkdocs build --strict` output, список страниц в nav, замеченные broken links если есть.
