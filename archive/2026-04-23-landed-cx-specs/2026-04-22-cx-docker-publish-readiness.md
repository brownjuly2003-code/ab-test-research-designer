# CX Task: Docker v1.0.0 image — build, verify runtime, prepare for publish

## Goal
Собрать production-ready Docker-образ `ab-test-research-designer:1.0.0` из HEAD `D:\AB_TEST\` (после того как release-таск `2026-04-22-cx-release-v1-revised.md` отработан и tag `v1.0.0` создан), прогнать end-to-end health/smoke против запущенного контейнера, задокументировать команду publish (без реального push). Фикс любых runtime bugs, блокирующих запуск, **в коде**, не в Dockerfile-хаках.

## Context
- Репо: `D:\AB_TEST\`, `main`, HEAD ожидается — release-коммит `v1.0.0` + tag. Если tag `v1.0.0` отсутствует — **остановиться**, этот таск требует релиза.
- Dockerfile в корне репо (ищи `FROM ... ` / `EXPOSE` / `CMD`). Compose: `docker-compose.yml`. Существующий `scripts/verify_docker_compose.py` делает non-destructive verify — использовать его как reference.
- Environment flags, с которыми контейнер реально тестируется (см. README секцию «Docker»):
  - base (open): `docker compose up --build`, должен отдавать `/` (frontend) и `/health`
  - secure: `AB_API_TOKEN=...` — write endpoints требуют Bearer
  - dual-token: `AB_API_TOKEN=...` + `AB_READONLY_API_TOKEN=...`
  - signed: `AB_WORKSPACE_SIGNING_KEY=...` — workspace backup с HMAC
- В `scripts/verify_all.cmd` уже есть `--with-docker` и `--with-docker-preserve` флаги — используются как референс.
- Предыдущие попытки Docker verify (из релиз-таска) могли провалиться в CX-среде из-за недоступности daemon. Этот таск **требует** работающий Docker; если среда CX его не даёт — **остановиться и сообщить**, не маскировать.

## Deliverables
1. **Сборка образа:**
   - `docker build -t ab-test-research-designer:1.0.0 -t ab-test-research-designer:latest .` из корня репо.
   - `docker inspect ab-test-research-designer:1.0.0 --format '{{.Size}}'` — зафиксировать размер в отчёте. Target: `< 500 MB` (мягкий, warning в отчёте если больше).
   - Если build падает — чинить в коде (`Dockerfile`, `requirements.txt`, `package.json` build scripts). **Не** использовать `--no-cache` как workaround.

2. **Runtime smoke (open mode):**
   - `docker run --rm -d --name ab-test-v1 -p 18008:8008 ab-test-research-designer:1.0.0`
   - Ждать `/health` → 200 (timeout 30s).
   - `curl 127.0.0.1:18008/health` → JSON с `"status":"ok"` и `"version":"1.0.0"` (после release-bump версия должна прийти из env default).
   - `curl 127.0.0.1:18008/readyz` → 200 с `"status":"ok"`.
   - `curl 127.0.0.1:18008/api/v1/diagnostics | jq .storage.write_probe_ok` → `true`.
   - `curl 127.0.0.1:18008/` → 200, HTML с title `AB Test Research Designer`.
   - `docker logs ab-test-v1` — нет ERROR / Exception. Если есть — зафиксировать в отчёте, если не блокирует запуск — допустимо.
   - `docker stop ab-test-v1`.

3. **Runtime smoke (secure mode):**
   - `docker run --rm -d --name ab-test-v1-secure -e AB_API_TOKEN=test-write-token -p 18009:8008 ab-test-research-designer:1.0.0`
   - `curl -w "%{http_code}" 127.0.0.1:18009/api/v1/calculate -X POST -H "Content-Type: application/json" -d '{"metric_type":"binary","baseline_value":0.1,"mde_pct":5,"alpha":0.05,"power":0.8,"expected_daily_traffic":1000,"audience_share_in_test":1.0,"traffic_split":[50,50],"variants_count":2}'` — ожидается `401` (без токена).
   - С токеном `-H "Authorization: Bearer test-write-token"` — ожидается `200`.
   - `docker stop ab-test-v1-secure`.

4. **Publish readiness (без реального push):**
   - Составить `docs/DEPLOY.md` (новый файл) с секциями:
     - **Build**: точные команды для сборки образа (скопировать из #1)
     - **Tag for registry**: placeholder `docker tag ab-test-research-designer:1.0.0 <REGISTRY>/ab-test-research-designer:1.0.0`. Явно указать что REGISTRY ставится юзером (ghcr.io, docker.io/user, и т.д.) — не хардкодить.
     - **Push**: `docker push <REGISTRY>/ab-test-research-designer:1.0.0` — **не выполнять**.
     - **Run locally (all modes)**: open / secure / dual-token / signed — команды с понятными env vars.
     - **Health / Verification**: `/health`, `/readyz`, `/api/v1/diagnostics` — ожидаемые ответы.
     - **Rollback**: как вернуться на предыдущий tag / image.
   - Обновить `README.md` — короткая ссылка на `docs/DEPLOY.md` в секции Docker (не дублировать содержимое).

5. **Один коммит** с сообщением:
   ```
   ops: verify v1.0.0 docker image and document deploy procedure
   ```

6. **Отчёт `docs/plans/2026-04-22-docker-publish-readiness-report.md`:**
   - Image size
   - Full smoke output (3 modes: open / secure — плюс опционально dual-token и signed если время позволило)
   - Any runtime warnings из `docker logs`
   - Блок «Publish checklist» — что должно произойти перед `docker push` (credentials, registry URL, image scan)

## Acceptance
- `docker images | grep ab-test-research-designer` содержит теги `1.0.0` и `latest`.
- Smoke-флоу (open + secure) прошли, коды ответов по спецификации выше.
- `docs/DEPLOY.md` присутствует и содержит все 5 секций.
- README содержит ссылку на `docs/DEPLOY.md`.
- Коммит `ops: verify v1.0.0 docker image and document deploy procedure` на HEAD, уникальный subject, с `Co-Authored-By: Codex`.
- `scripts\verify_all.cmd --with-e2e` = 0 после коммита.
- Отчёт присутствует и содержит реальные цифры (не placeholder).

## How
1. Подтвердить, что `git tag -l v1.0.0` возвращает tag. Если нет — **stop**, этот таск зависит от релиза.
2. Подтвердить что Docker daemon доступен: `docker info` — если падает, **stop** и report.
3. `docker build ...` из корня.
4. Запустить smoke open mode. Логировать выводы в `docs/plans/2026-04-22-docker-publish-readiness-report.md` по мере того как получаешь.
5. Запустить smoke secure mode. Логировать.
6. `docker stop`, `docker image prune --filter "dangling=true" -f` (только dangling, не все образы).
7. Написать `docs/DEPLOY.md`.
8. Обновить `README.md` — одна строка на ссылку.
9. `git add docs/DEPLOY.md README.md docs/plans/2026-04-22-docker-publish-readiness-report.md`; **также добавить этот CX-таск файл** `docs/plans/codex-tasks/2026-04-22-cx-docker-publish-readiness.md` (промах прошлых тасков — CX-файлы оставались untracked).
10. Commit с указанным subject.
11. Финальный `scripts\verify_all.cmd --with-e2e`.

## Notes
- **Commit subject hygiene:** `git log --oneline -20 | awk '{$1=""; print}' | sort | uniq -d` должно быть пусто. Если subject коллизит — менять текущий коммит, не rewriting landed.
- **CX-файл hygiene:** стейдж этот файл в свой коммит (прошлые таски часто оставляли CX .md untracked).
- **Runtime bugs:** если в контейнере `/health` возвращает 500 или `/readyz` красный — чинить в коде (`app/backend/**`), не в Dockerfile. Типичные причины: отсутствующая `app/frontend/dist/` в образе (забыли build step), `AB_SERVE_FRONTEND_DIST=false` дефолт, SQLite write-probe падает из-за read-only FS → нужно `VOLUME /data` и writable path.
- **Никаких `--privileged`, `--network host` флагов** в smoke — default bridge + `-p`.
- **НЕ** push'ить образ в registry, **НЕ** логиниться в docker hub / ghcr.
- **НЕ** коммитить `.docker-cli/` артефакты.
- Port pick: `18008` / `18009` выбраны чтобы не столкнуться с локальным uvicorn (8008). Если порты заняты — поменять номер и пометить в отчёте.

## Out of scope
- Реальный `docker push`
- CI для autobuild образа (`.github/workflows/docker-publish.yml`)
- Multi-arch builds (linux/amd64 + linux/arm64)
- Image vulnerability scanning (Trivy / Snyk)
- Demo hosting на внешних сервисах (Fly/Render/Vercel)
- Kubernetes манифесты
