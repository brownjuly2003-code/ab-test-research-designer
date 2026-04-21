# Post-Phase-2 Commit Log

Дата: 2026-04-21

База: `c29ab0d7`

## Commit wave

- `319820a0` `feat: experiment template gallery with yaml presets`
- `beb0827a` `chore: ignore archive run artefacts, restore historical docs`
- `0cdfa379` `feat: project list filters and keyboard shortcut help`
- `7eac8f59` `feat: audit log endpoint and request trail persistence`
- `docs: mark post-Phase-2 wave complete and index CX tasks` (this commit)

## Deviation from plan:

- `beb0827a` сделал archive-hygiene таск, но ошибочно включил часть PDF (`pdf_service.py`, `ChartExport*`, правки `export_service.py`, `ResultsPanel.tsx`, `results/*`, `projectStore.test.ts`).
- Templates (`319820a0`) ушёл до archive-hygiene, что отличается от исходного порядка.
- Отдельный PDF-коммит отдельным блоком не делаем: часть scope уже landed в `beb0827a`; остаток PDF (`api-contract.ts`, `projectStore.ts`, `docs/API.md`, возможные hunks в `routes/projects.py`) распределён по фактической принадлежности между коммитами про filters и audit persistence.
- Итог: 5 коммитов поверх `c29ab0d7` вместо плановых 4.
