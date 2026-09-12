# Evidence должно пережить вендора: проверяемый A/B-анализ на публичном наборе ASOS

> Публичный профиль: [`evidence-0.1`](https://github.com/brownjuly2003-code/ab-test-research-designer/tree/evidence-0.1),
> 12 сентября 2026 года. Trialmark пока экспериментален и не гарантирует
> обратную совместимость.

Результат A/B-теста часто живёт в дашборде ровно столько, сколько живут сам
сервис, его база и контекст команды. Через год число ещё можно найти, но уже
сложно ответить на более важные вопросы: какой протокол был зафиксирован, какие
данные прочитаны, каким методом получена оценка и какое человеческое решение
опиралось именно на неё.

Trialmark проверяет другую модель: результат анализа — это переносимый
content-addressed артефакт `.tmk`, а не строка в изменяемом интерфейсе. Архив
можно проверить офлайн, без исходного Parquet и без работающего сервера. Эта
статья показывает полный путь на aggregate-only данных из публичного набора
ASOS и заканчивается намеренной порчей архива.

## Короткая версия

Один воспроизводимый запуск делает следующее:

1. читает замороженный YAML-протокол и агрегированный Parquet;
2. блокирует конфликт ролей метрики, нарушение распределения трафика и поздние
   события до анализа;
3. считает один поддерживаемый бинарный estimand;
4. упаковывает протокол, provenance источника, SQL, описание метрики, оценку,
   профиль метода и run record в `.tmk`;
5. записывает человеческое решение отдельным дочерним bundle, не меняя
   исходный анализ;
6. проверяет оба архива офлайн;
7. добавляет байт в копию финального архива и требует, чтобы verifier отклонил
   её с `integrity: fail`.

```text
frozen protocol + aggregate source
                 |
                 v
             preflight ---- blockers stop the run
                 |
                 v
          analysis.tmk  <---- offline verify
                 |
          human decision
                 v
          decision.tmk  <---- offline verify
                 |
          append one byte
                 v
 decision-tampered.tmk  <---- integrity fail
```

Это не доказательство продуктового спроса и не независимая экспертиза
статистической корректности всего проекта. Это проверка конкретного контракта:
артефакт воспроизводимо собирается, его связи проверяются, а изменение файла не
проходит как исходный результат.

Короткая запись настоящего Trialmark Workbench показывает тот же переход от
блокера к remediation, анализу, проверяемому bundle и отдельному человеческому
решению:

[![Trialmark Workbench: ASOS blocker → decision](https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/evidence-0.1/docs/demo/trialmark-workbench-demo.png)](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/evidence-0.1/docs/demo/trialmark-workbench-demo.mp4)

## Данные: 78 экспериментов в источнике, три среза в репозитории

[ASOS Digital Experiments Dataset](https://osf.io/64jsb/) содержит 78 реальных
онлайн-экспериментов. Авторы — C. H. Bryan Liu, Angelo Cardoso, Paul Couturier
и Emma J. McCoy; набор опубликован по лицензии CC BY 4.0, DOI
`10.17605/OSF.IO/64JSB`.

Здесь важна точность формулировки. Trialmark пока не прогоняет в демо все 78
экспериментов. В репозитории зафиксированы три среза из 54 полных экспериментов
с одним treatment и четырьмя метриками. Их выбрали без просмотра outcomes: по
ближайшим к 25-му, 50-му и 75-му процентилям терминального размера выборки.
Пятиминутный сценарий использует один из них — `d53f0e`.

Публичный extract содержит агрегированные checkpoints, но не исходный
экспериментальный протокол, семантику метрик и exposure events. Поэтому пример
решает ретроспективную задачу воспроизводимости. Он не восстанавливает намерения
команды ASOS и не выдаёт demo-решение за реальное продуктовое решение.

## Что лежит внутри `.tmk`

`.tmk` — ZIP-контейнер с обычными JSON, SQL и HTML-файлами. Финальный bundle
демо содержит:

```text
manifest.json
decision/statement.dsse.json
estimates/estimate_asos_d53f0e_1.json
methods/profile.json
metrics/metric_asos_1.json
protocol/protocol.json
queries/<digest>.sql
rendered/report.html
run/run.json
sources/source_asos_d53f0e_terminal.json
```

`manifest.json` перечисляет защищённые члены, их размеры и SHA-256. Логическая
идентичность bundle вычисляется из канонического manifest, а не из имени файла.
Verifier отдельно проверяет целостность, schema conformance, внутренние ссылки,
lineage и privacy policy.

Профиль метода тоже находится внутри архива. Для этого сценария это
`binary_pooled_z_newcombe_v1`: pooled z-test для p-value и Newcombe interval для
risk difference. Профиль фиксирует estimand, sidedness, nominal alpha,
асимптотические ограничения, правила округления, версию reference
implementation и digest реализации.

Человеческое решение не перезаписывает analysis bundle. Trialmark создаёт новый
дочерний run с unsigned DSSE envelope и in-toto Statement v1. Subject statement
равен SHA-256 родительского analysis bundle; verifier сверяет его также с
`supersedes`.

Пустой список подписей здесь принципиален: digest binding уже есть, но личности
подписанта и доверенного timestamp нет. Sigstore и key management не входят в
текущий профиль.

## Повторяем сценарий

Нужны Git и Python 3.13+. Docker, облачный сервис и секреты не требуются. Ниже
команды для macOS/Linux; ветка фиксирует ровно тот профиль, на котором получены
результаты статьи:

```bash
git clone --branch evidence-0.1 --single-branch \
  https://github.com/brownjuly2003-code/ab-test-research-designer.git
cd ab-test-research-designer
```

Установка зависимостей выполняется один раз:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r app/backend/requirements.txt
```

Самый короткий запуск:

```bash
bash examples/demo/run_demo.sh
```

Скрипт создаёт временную директорию и печатает один JSON-отчёт. Чтобы сохранить
пути для самостоятельного вызова verifier, зададим свежую директорию явно:

```bash
demo_dir=$(mktemp -d "${TMPDIR:-/tmp}/trialmark-article.XXXXXX")
python -m examples.demo.run_demo --output-dir "$demo_dir"
```

Повторное использование той же директории намеренно запрещено: CLI и demo не
перезаписывают существующие evidence-артефакты.

В секции `faults` должны появиться три точных блокера:

```json
{
  "bad_metric": ["METRIC_ROLE_CONFLICT"],
  "late_exposure": ["TELEMETRY_MAX_LATENESS_EXCEEDED"],
  "seed_imbalance": ["ASSIGNMENT_SAMPLE_RATIO_MISMATCH"]
}
```

Исправленный analysis и человеческое decision проходят проверку. Существенная
часть сокращённого ответа выглядит так:

```json
{
  "valid": true,
  "verdicts": {
    "integrity": "pass",
    "schema_conformance": "pass",
    "reference_integrity": "pass",
    "lineage": "pass",
    "privacy_policy": "pass",
    "signature": "not_present",
    "statistical_validity": "not_asserted"
  }
}
```

Теперь вызываем тот же verifier напрямую:

```bash
python -m app.backend.app.evidence.cli verify \
  "$demo_dir/decision.tmk" --offline --policy strict
```

`--offline` не разрешает DNS, загрузку схем или повторное подключение к
источнику. Для проверки достаточно самого `.tmk` и verifier из checkout.

## Tamper-demo

`run_demo` уже создал `decision-tampered.tmk`: это точная копия финального
bundle с одним добавленным байтом. Проверим её отдельно и сохраним ожидаемый
ненулевой exit code:

```bash
set +e
python -m app.backend.app.evidence.cli verify \
  "$demo_dir/decision-tampered.tmk" --offline --policy strict
tamper_status=$?
set -e
test "$tamper_status" -eq 1
```

Verifier обязан вернуть:

```json
{
  "valid": false,
  "errors": [
    {
      "code": "archive_trailing_bytes",
      "dimension": "integrity"
    }
  ],
  "verdicts": {
    "integrity": "fail",
    "schema_conformance": "not_checked",
    "reference_integrity": "not_checked",
    "lineage": "not_checked",
    "privacy_policy": "not_checked"
  }
}
```

![Фактический результат offline-проверки намеренно повреждённого bundle: archive_trailing_bytes, integrity fail, exit 1](https://raw.githubusercontent.com/brownjuly2003-code/ab-test-research-designer/evidence-0.1/docs/demo/trialmark-tamper-verification.png)

Почему остальные измерения становятся `not_checked`, а не `pass`? После
нарушения транспортной целостности содержимому архива доверять нельзя. Verifier
останавливает более высокоуровневые выводы вместо того, чтобы строить их на
скомпрометированном входе.

## Что получилось в самом анализе

Для терминального checkpoint `d53f0e` bundle фиксирует:

| Поле | Значение |
| --- | ---: |
| Общий размер выборки | 3 480 897 |
| Control rate | 19,1100 % |
| Treatment rate | 19,1902 % |
| Risk difference | +0,0802 п.п. |
| 95 % CI | от −0,0025 до +0,1629 п.п. |
| p-value | 0,057214 |

При двустороннем alpha 0,05 результат незначим. Встроенное demo затем записывает
`ship` как пример механики человеческого решения. Это не рекомендация для ASOS:
исходная бизнес-семантика метрики неизвестна, а proposed verdict анализа —
`inconclusive`.

Такое разделение важно. Статистический результат, автоматическая рекомендация и
человеческое решение — разные сущности. Последняя может не совпасть с первой,
но должна явно назвать автора, rationale и evidence, на которое она ссылается.

## Что этот пример доказывает — и чего не доказывает

| Утверждение | Наблюдаемое доказательство |
| --- | --- |
| Неизменённый bundle самосогласован | Пять проверяемых verdict dimensions возвращают `pass` |
| Изменённый файл не принимается как исходный | Exit code 1, `integrity: fail`, `archive_trailing_bytes` |
| Решение связано с конкретным анализом | in-toto subject совпадает с digest родительского bundle и `supersedes` |
| Решение подписано доверенной личностью | Нет: `signature: not_present`, `signature_count: 0` |
| Вся статистика независимо сертифицирована verifier | Нет: `statistical_validity: not_asserted` |
| Проверено 78 экспериментов | Нет: источник содержит 78, сохранены три среза, demo использует один |
| Есть подтверждённое внешнее использование | Нет: partner cycles = 0 |

`privacy_policy: pass` тоже не означает универсальное «PII-free» или юридическое
соответствие. Это только успешная проверка текущей versioned policy на содержимом
данного bundle.

## Зачем всё это

Проверяемый архив не заменяет хороший дизайн эксперимента, ревью аналитика и
продуктовую ответственность. Он решает более узкую, но неприятную проблему:
не даёт им бесследно раствориться после смены интерфейса, хранилища или
поставщика.

Следующая проверка уже не техническая. Нужны три запуска на подготовленных
aggregate-данных практиков, измеренный time-to-bundle и факт повторного
использования. Пока этого нет, Trialmark остаётся reference implementation с
честным `PIVOT`, а не доказанным продуктом.

## Материалы

- [Код и инструкции профиля `evidence-0.1`](https://github.com/brownjuly2003-code/ab-test-research-designer/tree/evidence-0.1)
- [Ограничения и происхождение ASOS fixtures](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/evidence-0.1/app/backend/tests/fixtures/evidence/asos/README.md)
- [Вопрос и границы demo](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/evidence-0.1/examples/demo/question.md)
- [Замороженный demo-протокол](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/evidence-0.1/examples/demo/protocol.yaml)
- [Воспроизводимый скрипт записи Workbench](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/evidence-0.1/scripts/record_trialmark_demo.py)
- [Архитектура Trialmark](https://github.com/brownjuly2003-code/ab-test-research-designer/blob/evidence-0.1/docs/architecture/TRIALMARK_ARCHITECTURE.md)
- [Вопросы и обратная связь](https://github.com/brownjuly2003-code/ab-test-research-designer/issues/new)
