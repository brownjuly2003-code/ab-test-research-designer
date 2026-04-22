# 2026-04-22 Regenerate Screenshots Report

## Изменённые файлы

- `scripts/run_local_smoke.py`
- `app/frontend/src/components/ComparisonDashboard.tsx`
- `app/frontend/src/components/WebhookManager.tsx`
- `README.md`
- `CHANGELOG.md`
- `docs/demo/wizard-overview.png`
- `docs/demo/review-step.png`
- `docs/demo/results-dashboard.png`
- `docs/demo/comparison-dashboard.png`
- `docs/demo/webhook-manager.png`

## Размеры PNG

Базовые размеры взяты из `HEAD` для уже существовавших файлов. Для новых файлов baseline отсутствует.

| Файл | До | После |
| --- | ---: | ---: |
| `docs/demo/wizard-overview.png` | 621175 B | 394680 B |
| `docs/demo/review-step.png` | 668418 B | 439564 B |
| `docs/demo/results-dashboard.png` | 615454 B | 447688 B |
| `docs/demo/comparison-dashboard.png` | new | 808686 B |
| `docs/demo/webhook-manager.png` | new | 375804 B |

Примечание: `pngquant`/`oxipng` локально недоступны, поэтому для `results-dashboard.png` и `comparison-dashboard.png` применён локальный `magick` с palette PNG8. JPG не использовался.

## Smoke

- Успешный прогон: `archive/smoke-runs/20260422-183520`
- Всего скриншотов: 5
- Архивные копии: `archive/smoke-runs/20260422-183520/screenshots/`
- Общая длительность smoke по `smoke.log`: примерно 37 секунд
- Ключевые точки по логам:
  - `18:35:25` seed demo workspace + comparison snapshot prep
  - `18:35:41` captured `results-dashboard.png`
  - `18:35:52` captured `comparison-dashboard.png`
  - `18:35:56` captured `webhook-manager.png`
  - `18:35:57` smoke run passed

## Verify

- `scripts/verify_all.cmd --with-e2e` exit code: `0`

## UI-нюансы и технические замечания

- Добавлены точечные `data-testid`:
  - `comparison-dashboard`
  - `webhook-manager`
  - `webhook-subscription-row`
- `ComparisonDashboard` рендерится внутри закрытого accordion в results-panel, поэтому smoke явно открывает секцию `Comparison` перед захватом.
- `ComparisonDashboard` и `WebhookManager` lazy-loaded; для корректных переводов в runtime добавлен side-effect import `../i18n`, иначе в скриншоте появлялись raw i18n keys вместо человекочитаемых строк.
- Экспорт Markdown/HTML в results-panel доступен только после открытия меню `Export`; smoke теперь раскрывает его явно перед кликом по `Export Markdown` / `Export HTML`.
- `/api/v1/webhooks` в текущем коде admin-only. Для smoke используется admin session token и актуальная схема webhook payload (`name`, `target_url`, `secret`, `format`, `event_filter`, `scope`).
- Порядок seeded comparison candidates в sidebar не фиксирован, поэтому smoke выбирает первые две доступные карточки с snapshot checkbox, а не жёстко пришитые project names.
- README обновлён на relative `docs/demo/*.png` ссылки. Отдельная hosted-проверка после merge/push не выполнялась в этом локальном прогоне.
