# CX Task: Publish Docker image to GHCR on tag push

## Goal
Настроить GitHub Actions workflow `docker-publish.yml`, который на каждый push тега `v*` собирает Docker-образ из `Dockerfile` и публикует его на `ghcr.io/brownjuly2003-code/ab-test-research-designer:<tag>` + `:latest`. Поддержка multi-arch (`linux/amd64`, `linux/arm64`). Publish — только на tag push, не на обычных пушах в main. Workflow не мешает существующим (`test.yml`, Lighthouse, Docker verify).

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `14259fff` (tag `v1.1.0` уже опубликован на GitHub: https://github.com/brownjuly2003-code/ab-test-research-designer/releases/tag/v1.1.0). Не ветка, не push на remote.
- **Существующий CI.** `.github/workflows/test.yml` содержит три job: `verify` (ubuntu+windows), `docker` (secure compose verify), `lighthouse`. Ни один не публикует образ куда-либо.
- **Dockerfile.** В корне. Multi-stage (`node:22-alpine` frontend-build → `python:3.13-slim` runtime). Уже поддерживает multi-arch через базовые образы, `docker/setup-buildx-action` достаточно.
- **Реестр.** GitHub Container Registry (`ghcr.io`). Auth через `GITHUB_TOKEN` с правом `packages: write`. Никаких сторонних PAT не нужно.
- **Namespacing.** `ghcr.io/brownjuly2003-code/ab-test-research-designer` (owner = `brownjuly2003-code`, image name = repo name). GHCR package станет public после первого push — задокументировать чек-лист юзера.
- **Существующий Docker flow.** `scripts/verify_docker_compose.py` в CI `docker` job — это только verify, не build-and-push. Не трогать.
- **Тэги.** Только `v*` (не `bcg-*`, не `post-*`). Regex фильтр в workflow trigger: `tags: ['v*']`.

## Deliverables

1. **Новый workflow `.github/workflows/docker-publish.yml`:**
   ```yaml
   name: Publish Docker image

   on:
     push:
       tags:
         - 'v*'
     workflow_dispatch:
       inputs:
         tag:
           description: 'Tag to publish (e.g. v1.1.0). If empty, uses latest git tag.'
           required: false

   permissions:
     contents: read
     packages: write

   jobs:
     publish:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
           with:
             fetch-depth: 0
         - uses: docker/setup-qemu-action@v3
         - uses: docker/setup-buildx-action@v3
         - name: Resolve version
           id: version
           run: |
             if [ -n "${{ inputs.tag }}" ]; then
               echo "version=${{ inputs.tag }}" >> "$GITHUB_OUTPUT"
             else
               echo "version=${GITHUB_REF_NAME}" >> "$GITHUB_OUTPUT"
             fi
         - name: Strip v prefix
           id: semver
           run: |
             version="${{ steps.version.outputs.version }}"
             echo "clean=${version#v}" >> "$GITHUB_OUTPUT"
         - uses: docker/login-action@v3
           with:
             registry: ghcr.io
             username: ${{ github.actor }}
             password: ${{ secrets.GITHUB_TOKEN }}
         - uses: docker/metadata-action@v5
           id: meta
           with:
             images: ghcr.io/${{ github.repository }}
             tags: |
               type=raw,value=${{ steps.version.outputs.version }}
               type=raw,value=${{ steps.semver.outputs.clean }}
               type=raw,value=latest
               type=sha,prefix=sha-
             labels: |
               org.opencontainers.image.title=AB Test Research Designer
               org.opencontainers.image.description=Local-first A/B test research designer (FastAPI + React)
               org.opencontainers.image.licenses=MIT
         - uses: docker/build-push-action@v6
           with:
             context: .
             platforms: linux/amd64,linux/arm64
             push: true
             tags: ${{ steps.meta.outputs.tags }}
             labels: ${{ steps.meta.outputs.labels }}
             cache-from: type=gha
             cache-to: type=gha,mode=max
             provenance: true
             sbom: true
   ```
   Адаптировать к актуальным major-версиям actions (если одна из них deprecated — поднять). Не скачивать deprecated v1/v2.

2. **Пре-flight verify job (опционально, но желательно):**
   - В том же `docker-publish.yml` добавить job `verify-before-publish` с `needs: []`, который прогоняет `python scripts/verify_all.py --with-e2e` перед публикацией. Если падает — публикация не запускается.
   - Если CX посчитает, что это слишком долго для release pipeline (>15 min) — пропустить этот job и оставить только publish, но зафиксировать решение в отчёте.

3. **Обновить `docs/DEPLOY.md`:**
   - В секции «Build» добавить подсекцию «Pulling from GHCR»:
     ```
     docker pull ghcr.io/brownjuly2003-code/ab-test-research-designer:latest
     docker run --rm -p 8008:8008 ghcr.io/brownjuly2003-code/ab-test-research-designer:latest
     ```
   - Добавить подсекцию «Automated publish via GitHub Actions» с описанием trigger и чек-листом для первого release.

4. **README.md:**
   - В секцию `## Demo` (или рядом) добавить один бейдж:
     ```markdown
     [![GHCR](https://img.shields.io/github/v/tag/brownjuly2003-code/ab-test-research-designer?label=ghcr.io&logo=docker)](https://github.com/brownjuly2003-code/ab-test-research-designer/pkgs/container/ab-test-research-designer)
     ```
   - Одна строка в `## Main capabilities` или `## Product shape` — «Container image published to GHCR on each tag (`linux/amd64`, `linux/arm64`).»

5. **Чек-лист для юзера в отчёте:**
   - Первый push тега → workflow запустится автоматически.
   - После первого успешного run — зайти в https://github.com/brownjuly2003-code/ab-test-research-designer/pkgs/container/ab-test-research-designer → Settings → сменить visibility на **Public** (GHCR по умолчанию делает image связанным с репо, но первый push создаёт его как private; нужно один раз переключить).
   - Проверка: `docker pull ghcr.io/brownjuly2003-code/ab-test-research-designer:v1.1.0` с чистой машины без `docker login` должен работать после switch на Public.

6. **Один коммит:**
   ```
   ci: publish docker image to ghcr on tag push with multi-arch build
   ```
   Co-Authored-By: Codex <noreply@anthropic.com>
   В коммит: `.github/workflows/docker-publish.yml`, `docs/DEPLOY.md`, `README.md`, этот CX-файл, отчёт.

7. **Отчёт `docs/plans/2026-04-22-ghcr-publish-report.md`:**
   - Список файлов.
   - Результат локальной dry-run проверки workflow syntax (`actionlint` если доступен; иначе — ручная валидация YAML через `python -c "import yaml; yaml.safe_load(open('.github/workflows/docker-publish.yml'))"` = 0).
   - `scripts/verify_all.cmd --with-e2e` exit 0.
   - Чек-лист юзера для первого publish и переключения visibility на Public.
   - Известные риски: первый run занимает 8-15 min из-за multi-arch build без кэша; cache-from gha выручает на последующих.

## Acceptance
- `.github/workflows/docker-publish.yml` существует, YAML валиден (`python -c "import yaml; yaml.safe_load(open('.github/workflows/docker-publish.yml'))"` exit 0).
- Workflow триггерится только на `push: tags: ['v*']` и `workflow_dispatch`.
- Image references используют `ghcr.io/brownjuly2003-code/ab-test-research-designer` (через `${{ github.repository }}` — норм, но проверить, что it lowercases корректно; иначе hardcode lowercase).
- Multi-arch build: указаны `linux/amd64,linux/arm64`.
- `docs/DEPLOY.md` содержит секцию про GHCR pull.
- `README.md` содержит GHCR badge.
- `scripts/verify_all.cmd --with-e2e` exit 0.
- Коммит subject уникальный, CX-файл застейджен.
- `git status --short` пусто.
- **НЕ** push на remote, **НЕ** создавать новый тег, **НЕ** триггерить workflow. Юзер сам пушит после review.

## How
1. Baseline: `git status --short` пусто, verify = 0.
2. Прочитать `.github/workflows/test.yml` — понять существующий стиль (actions версии, matrix).
3. Написать `docker-publish.yml`. Валидировать YAML.
4. Обновить `docs/DEPLOY.md` — добавить секции про GHCR.
5. Обновить `README.md` — badge.
6. Запустить `scripts/verify_all.cmd --with-e2e` (не ломает существующее).
7. Коммит, отчёт.

## Notes
- **НЕ** использовать PAT / сторонние secrets. `GITHUB_TOKEN` с `packages: write` — достаточно.
- **НЕ** сохранять credentials в workflow или в Dockerfile.
- **НЕ** трогать `test.yml` / `verify_docker_compose.py` — они остаются как есть.
- **НЕ** ставить visibility image через GitHub API в workflow (это требует admin scope, GITHUB_TOKEN не хватает). Юзер переключает вручную один раз.
- **НЕ** публиковать на Docker Hub в этой итерации (отдельный таск если нужно).
- **НЕ** настраивать image signing (cosign / sigstore) в этой итерации — это отдельная security-таска.
- **НЕ** включать semver expansion (`1.1.0`, `1.1`, `1`) в metadata-action без явной продумки backwards compat; сейчас оставить `v1.1.0` и `1.1.0` и `latest`.
- **Retry-safety.** Workflow должен быть idempotent: повторный запуск того же тега перезаписывает теги в GHCR (норма). SHA-тег (`sha-<hash>`) нужен чтобы каждый build был уникально адресуем.
- **Кэш.** `type=gha` кэш работает без доп. настройки, но очищается GitHub через 7 дней неактивности — задокументировать.
- Если `actionlint` установлен у юзера локально (`actionlint --version` не падает) — прогнать, в отчёт результат. Если нет — пометить «actionlint not available, YAML checked manually».
- GHCR package visibility по умолчанию PRIVATE на первый push (связан с user, не репо) — переключение вручную один раз. Зафиксировать в отчёте и в DEPLOY.md.

## Out of scope
- Docker Hub publish.
- Cosign image signing.
- Vulnerability scanning (Trivy / Grype) в workflow.
- Auto-update `:latest` на коммитах в main (только на tag).
- Генерация changelog из commits.
- Kubernetes manifests / Helm chart.
- Image promotion между registries.
