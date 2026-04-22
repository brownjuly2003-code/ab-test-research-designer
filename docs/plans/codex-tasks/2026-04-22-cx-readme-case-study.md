# CX Task: README case-study section — checkout-redesign worked example

## Goal
Добавить в `README.md` секцию `## Case study: Checkout redesign` с реалистичным сквозным примером использования инструмента: baseline conversion 4.2%, MDE 10%, два варианта + контроль, расчёт sample size и длительности, Bayesian posterior после первого interim check, итоговое решение. Секция — демонстрация ценности, а не tutorial. Все числа получены реальным прогоном backend-эндпоинтов на HEAD — никаких вымышленных значений.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `14259fff` (tag `v1.1.0`). Не ветка, не push.
- **Backend API.** Все расчёты делать реальным вызовом endpoints:
  - `POST /api/v1/calculate` — binary metric sample size.
  - `POST /api/v1/design` — deterministic full report.
  - Bayesian posterior: через `app/backend/app/stats/bayesian.py` (функции `posterior_beta_binomial` или аналог — найти в существующем коде). Если прямого endpoint нет, использовать сервис или выкрутить через `services/analysis_service.py`.
  - Endpoint для group-sequential interim: если есть `POST /api/v1/sequential/...` — использовать; иначе вызвать `stats/sequential.py` напрямую из one-off скрипта.
- **Существующая структура README.**
  - Секция `## Demo` с скринами.
  - Секция `## Product shape`, `## Main capabilities`.
  - `## Case study` должна встать **между** `## Demo` и `## Product shape` — это первое, что видит посетитель после картинок.
- **Тон.** Коротко, по делу, числа на первом плане. НЕ маркетинговый язык. НЕ «revolutionary». Читается как мини-story: «вот бизнес-контекст → вот что посчитал инструмент → вот как выглядят interim-данные → вот решение».
- **Templates.** `app/backend/templates/checkout_conversion.yaml` — базовый пресет. Использовать его параметры как отправную точку, но числа в секции должны соответствовать **фактическому output** расчёта, а не перепечатке YAML.

## Deliverables

1. **Скрипт `scripts/generate_case_study_numbers.py`:**
   - One-shot скрипт, собирает все числа через `TestClient(create_app())` (тот же паттерн что `seed_demo_workspace.py`).
   - Input: hardcoded сценарий checkout redesign:
     - baseline conversion: **4.2%**
     - MDE (relative): **10%**
     - α = 0.05, power = 0.80
     - expected daily traffic: **80 000 visitors**
     - audience share: **50%**
     - variants: 3 (control + 2 treatments), traffic split `[34, 33, 33]`
     - test tail: two-sided
   - Запрашивает:
     1. `POST /api/v1/calculate` → sample size per variant, total sample, duration в днях, Bonferroni note.
     2. `POST /api/v1/design` → full deterministic report (risks, recommendations).
     3. Bayesian posterior: симулирует interim check на 50% от планируемой длительности с gathered data control=1200/16000 (7.5%), variant_A=1272/16000, variant_B=1340/16000. Считает `P(variant_A > control)` и `P(variant_B > control)` через существующий Bayesian helper.
   - Output: печатает структурированный Markdown на stdout + пишет сырой JSON в `docs/case-studies/checkout-redesign.json` (для воспроизводимости).
   - Idempotent: можно запускать повторно, результат стабилен (seed Bayesian если там есть рандом).

2. **Каталог `docs/case-studies/`:**
   - `docs/case-studies/checkout-redesign.json` — результат прогона скрипта.
   - `docs/case-studies/README.md` — короткий индекс (пока один файл): что это, как перезапустить (`python scripts/generate_case_study_numbers.py > /tmp/cs.md`).

3. **Секция `## Case study: Checkout redesign` в `README.md`:**
   - Вставлена между `## Demo` и `## Product shape`.
   - Структура (примерно 250-400 слов + одна табличка):
     ```
     ## Case study: Checkout redesign

     Retailer testing two checkout variants against control to lift conversion from a 4.2% baseline.

     **Setup** — 80k daily visitors, 50% share into test, 3 variants (34/33/33), α = 0.05, power = 0.80, two-sided, relative MDE = 10%.

     **Sizing (from `POST /api/v1/calculate`).**

     | Metric | Value |
     | --- | --- |
     | Per-variant sample | <from script> |
     | Total sample | <from script> |
     | Required duration | <from script> days |
     | Bonferroni adjustment | <note from response> |

     **Design guidance (from `POST /api/v1/design`).**
     - Primary risk: <pick top risk from response, one line>
     - Key recommendation: <pick top recommendation, one line>
     - Guardrail to monitor: <pick from response>

     **Interim check at 50% duration.**
     After <N> days with <observed conversions>:
     - P(variant A beats control) = <x.x%>
     - P(variant B beats control) = <x.x%>
     <one-line interpretation: whether to stop/continue based on numbers>

     **Decision.** <one short paragraph: what a PM using this tool would do given these numbers>

     Full inputs and outputs: [docs/case-studies/checkout-redesign.json](docs/case-studies/checkout-redesign.json). Rerun with `python scripts/generate_case_study_numbers.py`.
     ```
   - **Все числа** в таблице и интерим-секции — из реального прогона, подставленные (CX сам вставляет цифры после прогона скрипта).
   - **НЕ** добавлять скриншот case study в эту итерацию (отдельный таск про regeneration скринов).

4. **Обновить `CHANGELOG.md`:**
   - Под `### Unreleased` (или создать) добавить bullet: «Added Checkout-redesign case study section to README with reproducible numbers from backend calculation and Bayesian interim check.»

5. **Один коммит:**
   ```
   docs: add checkout-redesign case study section with reproducible numbers
   ```
   Co-Authored-By: Codex <noreply@anthropic.com>
   В коммит: `scripts/generate_case_study_numbers.py`, `docs/case-studies/checkout-redesign.json`, `docs/case-studies/README.md`, `README.md`, `CHANGELOG.md`, этот CX-файл.

6. **Отчёт `docs/plans/2026-04-22-readme-case-study-report.md`:**
   - Полный вывод скрипта.
   - Файлы изменённые/созданные.
   - `scripts/verify_all.cmd --with-e2e` exit code.
   - Известные ограничения: Bayesian posterior зависит от precise prior spec — задокументировать какой prior использован (обычно `Beta(1,1)` uniform).

## Acceptance
- `python scripts/generate_case_study_numbers.py` = exit 0, печатает Markdown таблицу со заполненными числами.
- `docs/case-studies/checkout-redesign.json` валидный JSON (`python -m json.tool < docs/case-studies/checkout-redesign.json` = 0).
- `README.md` содержит секцию `## Case study: Checkout redesign` между `## Demo` и `## Product shape`. Все `<from script>` плейсхолдеры заменены на реальные числа.
- Числа в README совпадают с `checkout-redesign.json` (spot-check хотя бы 2 значения).
- `scripts/verify_all.cmd --with-e2e` exit 0.
- Коммит subject уникальный (`git log --oneline -20 | awk '{$1=""; print}' | sort | uniq -d` пусто).
- CX-файл застейджен в тот же коммит.
- `git status --short` пусто.
- **НЕ** push на remote.

## How
1. Baseline: `git status --short` пусто, verify зелёный.
2. Прочитать `app/backend/templates/checkout_conversion.yaml`, `app/backend/app/schemas/api.py` (найти actual schema для `POST /api/v1/calculate`), `app/backend/app/stats/bayesian.py`.
3. Написать `scripts/generate_case_study_numbers.py`. Локальный прогон → stdout + JSON.
4. Скопировать числа в README секцию, чистым Markdown.
5. Обновить CHANGELOG.
6. Коммит с list файлов (include CX-файл и отчёт).
7. `scripts/verify_all.cmd --with-e2e`.

## Notes
- **Честность чисел.** Если реальный расчёт даёт неудобные/некрасивые значения — не подкручивать input. Либо принять как есть, либо чуть изменить setup (например 4.2% → 4.5% baseline), НО заново прогнать скрипт и заново подставить. Никаких ручных правок чисел «чтобы красивее».
- **Язык README.** English (это публичный README). НЕ копировать русский tone.
- **Длина секции.** Целевая — одна scroll-страница на desktop. Не растягивать.
- **Без emoji** в case study. Числа и факты.
- **Bayesian prior.** Документировать явно (`Beta(1,1)`), чтобы было воспроизводимо. Если в коде уже используется conjugate prior — использовать его и задокументировать.
- **Group-sequential interim.** Если в существующем коде нет ready функции для «after N% duration compute Bayesian probability» — собрать это вручную в скрипте через posterior update. Проще, чем тащить новый endpoint.
- **Не** требовать Ollama / внешний LLM. Case study — только deterministic math.
- **Не** коммитить временные файлы (pyc, pytest cache, playwright artifacts).
- Если секция случайно ломает существующие anchor-ссылки в README (TOC, cross-links) — исправить их.

## Out of scope
- Добавление второго case study (e.g. pricing, email subject).
- Интерактивный runnable notebook (отдельный Tier 3 таск).
- Перевод case study на ru/de/es.
- Скриншоты results dashboard специально для case study.
- Новые backend endpoints.
- Изменения в `checkout_conversion.yaml` пресете.
