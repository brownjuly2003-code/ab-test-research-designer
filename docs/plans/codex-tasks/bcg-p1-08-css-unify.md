# T8: CSS унификация

**Phase:** BCG Phase 1
**Depends on:** T7 (error boundaries)
**Effort:** ~2h

## Context

`src/App.css` — 214 строк глобальных классов (`.page`, `.shell`, `.grid`, `.btn`, `.field`, `.card`, `.toast-*`, `.muted`, `.pill`, `.icon` и т.д.). Часть компонентов использует CSS Modules, часть — глобальные классы. Нужна унификация.

Читать:
- `src/App.css`
- `src/styles/tokens.css` (если есть)
- `BCG_plan.md` §1.5.1-1.5.2

## Goal

1. Разделить `App.css` на `layout.css` / `components.css` / `utilities.css`
2. Перевести компоненты без CSS Modules — на модули
3. Визуально без изменений (light + dark mode)

## Steps

### 1. Аудит `App.css`

Разбить классы на три группы:
- **layout.css**: структура страницы — `.page`, `.shell`, `.grid`, breakpoints
- **components.css**: компоненты-атомы — `.btn`, `.field`, `.card`, `.toast-*`, формы, inputs
- **utilities.css**: helper-классы — `.muted`, `.pill`, `.icon`, `.sr-only`, spacing utilities

Создать:
- `src/styles/layout.css`
- `src/styles/components.css`
- `src/styles/utilities.css`

В `src/main.tsx` или `src/index.css` импортировать все три.

### 2. Удалить `App.css` (или оставить пустым для legacy import)

Убедиться: `rg "App\.css" src` → или пусто, или только `App.tsx` → заменить на импорт из `styles/`.

### 3. Компоненты без CSS Modules → модули

Список из `BCG_plan.md` §1.5.2:
- `EmptyState`
- `ToastSystem`
- `Accordion`
- `MetricCard`
- `SliderInput`
- `Spinner`
- `Skeleton`
- `ProgressBar`
- `StatusDot`
- `Tooltip`
- `InlineConfirmButton`

Для каждого:
1. Создать `*.module.css` рядом
2. Перенести соответствующие глобальные правила
3. Импортировать `styles from "./X.module.css"` и заменить `className="..."` на `className={styles.x}`
4. Удалить эти правила из `components.css`

### 4. Dark mode

Проверить, что dark mode работает после миграции. Все `[data-theme="dark"]` селекторы должны переехать вместе со своими правилами.

### 5. Verify

```bash
cd app/frontend
npx vitest run
npx tsc --noEmit
npm run build
rg "App\.css" src  # только импорт в App.tsx или пусто
```

Ручная проверка (критично):
- Light mode: wizard, sidebar, results — визуально идентично до изменений
- Dark mode: то же самое
- Responsive: 375px, 1024px, 1440px
- Все интерактивы (кнопки, инпуты, тултипы, accordion, toast) выглядят как раньше

Скриншоты before/after в `tmp/` для каждого из 3 главных viewport'ов желательны, но не обязательны.

## Done When

- [ ] `src/styles/layout.css`, `components.css`, `utilities.css` созданы
- [ ] 11 компонентов из списка переведены на CSS Modules
- [ ] `App.css` пустой или удалён
- [ ] Визуальная парность (light + dark + responsive)
- [ ] Все тесты зелёные

## Constraints

- Не вводить новые CSS-переменные / токены дизайна — это Phase 2
- Не менять цвета, spacing, shadows — только организация файлов и scope
- Если какой-то класс сложно "scopировать" (глобальный для html/body) — оставить в `layout.css` как глобальный, это ок
