# AB_TEST → production-grade 9.8/10 (2026-06-26)

Цель (запрос Юли): поднять ВСЕ 6 измерений `eval.md` до **9.8/10**, включая
продакшн-готовность — «сделать продукт для реальной работы, по-максимуму».
Это сознательный выход за прежнюю рамку local-first MVP → настоящая платформа.

Деплой seeded-демо на HF **санкционирован** (по готовности → выкатить + live-проверка).

## СТАТУС (2026-06-26, остановка после Phase 2)
- ✅ **Phase 1 ВЛИТА** (PR #27 → merge `f60e84a3`): coverage-гейт enforced ≥88%, ruff-гейт (F,I,B,C4,UP) поверх mypy strict, 0 TODO.
- ✅ **Phase 2 ВЛИТА** (PR #28 → merge `7c26cb83`): `deploy-hf.yml` (workflow_dispatch + tag `v*`, НЕ на push) + `scripts/deploy_hf.py` (зеркало ручного рецепта + /health-smoke). Деплой держится (триггерится только вручную/тегом).
- ⏳ **Phase 3 — СЛЕД. СЕССИЯ начинает здесь** (стат. доборы), затем Phase 4 (главный объём — продакшн), 5 (demo+deploy), 6 (переоценка).
- ⚠️ **Перед первым CI-деплоем**: Юля задаёт repo-секрет `gh secret set HF_TOKEN` (write-токен `liovina`). Без него deploy-job падает с подсказкой (по дизайну).

## Старт (факты на 2026-06-26, main=`abe44277`, ось A полностью влита)
- Coverage **91%** (badge), НЕ гейтится в CI. Tests 622 backend passed.
- Единственный TODO — в тесте `app/frontend/src/components/PosteriorPlot.test.tsx` (не прод).
- Деплой HF — **ручной** (`upload_folder`); workflow'ов: `test.yml`, `docker-publish.yml`, `docs-site.yml` — HF-деплоя нет.
- Ingestion: `exposures UNIQUE(exp,user)` first-write-wins + `conversions UNIQUE(exp,idempotency_key)`; только `created_at` (server-receive), **нет `occurred_at`** (event-time), нет identity resolution, нет bot-фильтра.
- stats: 12 модулей (вкл. `duration.py`). execution: bucketer/experiment_assignment/targeting.

## Текущие баллы → цель
| Измерение | Сейчас | Цель | Главный рычаг |
|---|---|---|---|
| Стат. глубина | 9.5 | 9.8 | F2 sizing/post-hoc + F3b Neyman-дисперсия |
| Качество кода | 9.3 | 9.8 | дожать TODO + ruff/docstring строгость |
| Тестирование | 9.2 | 9.8 | enforced coverage-гейт (≥90) |
| CI/процесс | 9.0 | 9.8 | coverage-гейт + автодеплой HF |
| Подача/демо | 7.5 | 9.8 | seeded-demo (фичи видны без ingest) + деплой |
| Продакшн-готовность | 6.5 | 9.8 | event-time, late events, identity, bot-фильтр, PG-first |

---

## Phase 1 — Гейты качества (дёшево, Windows+CI; Тестирование/CI/Качество)
- [x] **T1.1 Coverage-гейт.** `--cov-fail-under=90` в `verify_all.{py,cmd}` + CI; pytest-cov уже даёт 91%. Порог чуть ниже текущего (буфер на флап). → Verify: CI `verify` падает при <90%, badge живёт.
- [x] **T1.2 Дожать TODO** в `PosteriorPlot.test.tsx` (реальные recharts-ассершены без flat-mock) → 0 TODO/FIXME/HACK в app+src. → Verify: grep пусто, vitest зелёный.
- [x] **T1.3 ruff строгость.** Включить `D` (pydocstyle) на публичных stats/services ИЛИ ruff `--select` расширить (complexity `C901`), без массового шума. → Verify: ruff зелёный, mypy strict цел.
- → Тестирование 9.8, Качество 9.6 (добор в P3/P4), CI 9.5 (автодеплой добьёт в P2).

## Phase 2 — Автоматизация деплоя (CI/процесс → 9.8)
- [x] **T2.1 GH Action `deploy-hf.yml`** — `workflow_dispatch` (+ on tag `v*`): `git archive main` → `upload_folder` на HF Space через секрет `HF_TOKEN` (репо-секрет, токен `liovina`). `ignore_patterns` как в `docs/DEPLOY.md`. → Verify: ручной dispatch зелёный, Space обновился (смена asset-хэша).
- [x] **T2.2** Пост-деплой smoke в workflow (`/health`-poll в `deploy_hf.py`). → Verify: job падает при нездоровом Space.
- ⚠️ Секрет `HF_TOKEN` в репо: Юля задаёт `gh secret set HF_TOKEN` (свой токен — НЕ печатать/коммитить).

## Phase 3 — Стат. глубина доборы (→ 9.8)
- [ ] **T3.1 F2 ratio sizing + post-hoc `/results`.** delta-power для ratio (sample size) + ratio в ручном анализаторе `/results` (сейчас ratio только на live). → Verify: тест sizing vs sim, post-hoc endpoint, i18n×7.
- [ ] **T3.2 F3b Neyman-точная дисперсия** (опц.) — точная стратиф. дисперсия vs текущая conditional (честно задокументирована). → Verify: тест vs ref, не ломает combine.
- Формулы досверять с первоисточником (паттерн оси A).

## Phase 4 — ПРОДАКШН-ГОТОВНОСТЬ (главный объём; dual-SQL → CI verify-postgres + Mac)
Каждая под-фаза = вертикальный срез + свой PR + verify-postgres + i18n×7 где есть UI.
- [ ] **P4.1 Event-time semantics.** Добавить `occurred_at` (client event time) на `exposures`/`conversions` отдельно от `created_at` (server-receive); schema bump; обе БД; ingest принимает occurred_at (default=received). Фундамент для late events. → Verify: round-trip оба бэкенда, verify-postgres.
- [ ] **P4.2 Late / out-of-order events.** Окно атрибуции (experiment window), флаг `is_late`, корректная атрибуция поздних конверсий + индикатор «N late events» в live-stats; watermark в re-estimation. → Verify: тест late-conversion атрибутируется/исключается по окну; dual-SQL.
- [ ] **P4.3 Identity resolution.** Таблица `identity_map (experiment_id, anonymous_id, canonical_id)`; ingest принимает anonymous_id; аналитика резолвит к canonical (предотвращает двойной учёт при anon→login). first-write-wins canonical. → Verify: тест merge не раздувает SRM/конверсии; dual-SQL.
- [ ] **P4.4 Bot / fraud-фильтр.** Флаг `excluded`/`exclusion_reason` на участнике (эвристики: rate-spike, дубль-fingerprint опц., ручной deny-list) + исключение из всех агрегатов; индикатор «N filtered». → Verify: тест отфильтрованные не влияют на эффект; dual-SQL.
- [ ] **P4.5 Postgres-first prod-режим.** Явный prod-config (PG обязателен), health-проверка соединения, гайд `docs/PRODUCTION.md` (deploy PG, env, ретеншн, бэкап-заметки), проверка полноты PG-пути. → Verify: prod-конфиг стартует на PG, mypy/тесты целы.
- [ ] **P4.6 Ingestion-надёжность.** Подтвердить батч-идемпотентность под нагрузкой (тест 10k событий, дедуп-инварианты), документировать пропускную способность/лимиты. → Verify: нагрузочный тест зелёный.
- → Продакшн-готовность 6.5 → 9.8. **Запускать dual-SQL на Mac `deproject-mac` ИЛИ полагаться на CI verify-postgres** (нет Docker на Win).

## Phase 5 — Seeded-demo + деплой (Подача/демо → 9.8)
- [ ] **T5.1 Seed-эксперимент.** Скрипт/стартовый сидинг: демо-эксперимент с ingested exposures/conversions/pre-period/strata так, чтобы **always-valid + ratio + CUPED + stratification + decision-readout видны на дефолтном демо-пути** (без ручного ingest). Изолированный demo-tenant, дефолт-корпус/проекты не трогать. → Verify: live-stats демо показывает все блоки.
- [ ] **T5.2 Деплой + live-проверка.** `deploy-hf.yml` (P2) → Playwright: публичный `/` чист (нет operator-панели), seeded-фичи видны, 0 console-errors, en/ru/dark/mobile. → Verify: прод-Space зелёный, фичи на экране.

## Phase 6 — Верификация и переоценка
- [ ] **T6.1** Полный гейт серийно (Win-thrashing): mypy strict, vitest `--no-file-parallelism`, build, contract `--check`, ruff, locale, coverage. CI на каждом PR: verify ubuntu+windows + verify-postgres + docker + lighthouse + locale + repo-hygiene.
- [ ] **T6.2 Обновить `eval.md`** — новые баллы с обоснованием, учесть F3b + production-фичи; снять «на день устарел».

## Done When
- [ ] Все 6 измерений `eval.md` ≥ 9.8 с честным обоснованием (числа/тесты/CI — не нарисованные).
- [ ] Production-фичи (event-time, late, identity, bot-фильтр, PG-first) влиты, verify-postgres зелёный.
- [ ] Seeded-demo задеплоен, фичи видны на живом HF, публичный вид чист.
- [ ] Coverage-гейт + автодеплой в CI; 0 TODO; eval.md переоценён.

## Notes / constraints
- Не /auto явно, но Юля «по-максимуму» + «реши сам» по AB_TEST → локальные коммиты сама, PR по зелёному CI, деплой санкционирован. Push/merge — паттерн оси A (зелёный CI → merge).
- **Нет Docker на Windows** ([[no-docker-on-windows]]) → dual-backend SQL (вся Phase 4) валидируется в CI `verify-postgres` + прогон на Mac `deproject-mac` (конфиг как CI: postgres:16, db `abtest`, env `AB_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/abtest`).
- Не гонять полный pytest+vitest+build параллельно на Win (thrashing) — серийно; аддитив доверять CI.
- Порядок рычага: P1/P2 дёшевы и разблокируют (гейты+деплой) → P3 (стат) → **P4 (главный объём, production)** → P5 (demo+deploy) → P6 (verify+переоценка).
- Секреты (HF_TOKEN и пр.) — через `gh secret`, НЕ в код/логи.
