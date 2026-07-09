---
title: "План: execution-слой (MVP «проводить эксперимент»)"
---

# План: execution-слой (MVP «проводить эксперимент»)

**Дата:** 2026-06-12
**Источник:** `res_07_06_26.md` §5.1–5.3 (оценка execution-слоя; MVP ~3–4 недели, т.к. stats-движок уже написан — не хватает только data-plumbing).
**Решение пользователя:** «go» — строим execution-MVP. Production-grade (§5.3) остаётся осознанным не-целью.

## Рамка

Замкнуть цикл **plan → run → analyze** в одном local-first инструменте: создал эксперимент в визарде → получил deterministic assignment-endpoint и сниппет → exposure/conversion-события льются в SQLite → дашборд показывает live SRM + sequential/Bayesian-читы → стоп по существующим правилам. Уникальная позиция: ни один из топ-20 не делает это локально без облака.

**Явный дисклеймер в UI:** «MVP execution — демонстрация полного цикла, не для high-traffic production» (duck-тип GrowthBook self-host).

Каждая фаза — отдельная ветка/PR с зелёным `verify_all.py --skip-smoke` + ubuntu e2e, как в §5.4-батче. Вертикальный срез: `schemas/api.py` → сервис/модуль → `routes/*` (+ auth) → регенерация контракта/доков → frontend (+ i18n ×7) → тесты → гейт.

---

## Phase A — Bucketer (детерминированное назначение) — LOW, ~1–2 дня — **ЭТА СЕССИЯ**

**Зачем:** фундамент всего execution-слоя; чистая функция без инфраструктуры, тестируется против опубликованных GrowthBook test-векторов.

**Суть:** порт GrowthBook hashing-спеки (MIT). `fnv32a(seed + id)`, hashVersion 2 = двойной хэш `fnv32a(fnv32a(seed + id) + "")`, `% 10000 / 10000` → float `[0,1)`. Диапазоны вариаций из `coverage × weights` (равные веса по умолчанию). `coverage < 1.0` = ramp-up бесплатно (хвост → «не в тесте»). Mutual-exclusion/holdout — второй хэш на общем layer-seed + зарезервированный диапазон (инкремент, следующая фаза).

**Изменения:**
- `app/backend/app/execution/__init__.py` + `app/backend/app/execution/bucketer.py`:
  - `fnv32a(text: str) -> int` (32-bit FNV-1a).
  - `hash_to_unit(seed: str, user_id: str, hash_version: int = 2) -> float` (v1 `%1000/1000`, v2 двойной хэш `%10000/10000`).
  - `get_bucket_ranges(num_variations, coverage, weights) -> list[(lo, hi)]`.
  - `choose_variation(unit_interval, ranges) -> int` (-1 = вне покрытия/не в тесте).
  - `assign_variation(seed, user_id, num_variations, coverage=1.0, weights=None, hash_version=2) -> {variation_index, in_experiment, hash}`.
- `schemas/api.py`: `AssignmentPreviewRequest` (seed, user_ids|count, num_variations, coverage, weights, hash_version) + `AssignmentPreviewResponse` (per-user variation + сводка распределения для sanity-check).
- `routes/analysis.py` (или новый `routes/execution.py`): `POST /api/v1/assignment/preview` (`require_write_auth`) — детерминированный предпросмотр распределения по N синтетическим user_id (планировочный sanity-check, ещё НЕ live-assignment по эксперименту — это Phase B).
- frontend: блок «Assignment preview» (опционально в этой фазе; минимум — backend+contract; UI можно отдельным срезом). i18n ×7 при наличии UI.
- регенерация `api-contract.ts` + `docs/API.md`.

**Тесты (ключевое — known-reference):**
- `fnv32a` и `hash_to_unit` против GrowthBook test-векторов (`packages/sdk-js/src/util.ts` / `__tests__`): сверить константы v1/v2 ДО реализации.
- Детерминизм (тот же seed+id → тот же bucket), стабильность (sticky).
- Равномерность распределения на большом N (χ² к равным весам в допуске).
- `coverage < 1` → доля «вне теста» ≈ `1 - coverage`.
- Неравные `weights` → пропорции совпадают.
- Route-тест preview (детерминизм ответа).

**Объём:** 1–2 дня. **Риск:** низкий — чистая функция; единственная ловушка — точность констант хэша (сверить с MIT-исходником и test-векторами перед портом).

---

## Phase B — REST assignment endpoint + flags-минимум — LOW, ~1–2 дня

`POST /api/v1/experiments/{id}/assign` `{user_id, attributes}` → variation для сохранённого эксперимента (привязка bucketer к `projects`-репозиторию: seed = project_id/experiment_seed, num_variations/weights из experiment_design). Хитрый ход: отдавать **GrowthBook-совместимый JSON payload**, чтобы готовые MIT SDK работали клиентским слоем. Local-eval со streaming-конфигом — вне MVP.

## Phase C — Event ingestion + dedup — MEDIUM, ~1 неделя (основная работа)

Две таблицы: `exposures` (user, experiment, variation, ts) и `conversions` (user, metric, value, ts, idempotency_key). SQLite (наш local-first сегмент; Postgres опц. через `AB_DATABASE_URL`). **Главный риск — dedup:** ровно одна exposure на (experiment, user), first-exposure-wins; дубликаты напрямую *производят* ложный SRM. Batching + батч-insert.

## Phase D — Live-stats + scheduler + «running experiment» UI — LOW–MEDIUM, ~3–5 дней

SRM-guardrail = `COUNT(*) GROUP BY variation` по dedup-exposures + существующий chi-square, гонять постоянно. Sequential/Bayesian — перезапуск существующих функций над текущими агрегатами по расписанию (новой математики нет). **CUPED** — только при наличии pre-period covariate-данных per user (иначе пометить «недоступно»). Дашборд live-эксперимента.

---

## Рекомендуемая последовательность
A (фундамент, эта сессия) → B (привязка к экспериментам) → C (ingestion+dedup — самое ёмкое) → D (live-аналитика). Каждая фаза самостоятельно ценна и заканчивается зелёным гейтом.

## Главные технические риски (из §5.3 / §6)
1. **Exposure-dedup** — источник ложного SRM (Phase C). first-exposure-wins + idempotency.
2. **CUPED на live** — нужны pre-period данные per user (Phase D); честно помечать недоступность.

## Явные НЕ-цели (§5.3 «сюда НЕ идти»)
identity resolution / multi-device stitching · bot-фильтрация · late/out-of-order события, timezone-нормализация · columnar warehouse + streaming at scale · exactly-once dedup на высоком throughput · streaming config refresh для local-eval SDK. Это годы (Bing/Facebook) — фиксируем как осознанное ограничение и дисклеймер в UI.
