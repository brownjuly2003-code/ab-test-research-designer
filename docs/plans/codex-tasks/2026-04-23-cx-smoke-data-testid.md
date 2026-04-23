# CX Task: Migrate compare-smoke locator to data-testid contract

## Goal
Уйти в compare-smoke от accessible-name локатора `get_by_role("checkbox", name="Select for comparison")` на стабильный `data-testid` контракт для панели compare. Задача — chore-hardening: smoke не должен ломаться от изменения copy сайдбара (например, при переводе или A/B тесте названий кнопок). Принцип: user-facing accessibility attrs остаются для пользователей, testid-ы — для smoke-контракта.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `f1316300` (Ubuntu CI green после smoke fix).
- **Текущий smoke.** `scripts/run_local_smoke.py`, функция `run_browser_smoke`, блок "opening comparison dashboard" (~строки 438-460):
  ```python
  page.get_by_role("button", name="Projects", exact=True).click()
  compare_checkboxes = page.get_by_role("checkbox", name="Select for comparison")
  compare_checkboxes.nth(1).wait_for(state="visible", timeout=15000)
  if compare_checkboxes.count() < 2:
      raise RuntimeError("Smoke expected at least two comparison-ready project checkboxes.")
  compare_checkboxes.nth(0).check()
  compare_checkboxes.nth(1).check()
  page.locator("#compare-selected-projects-button:not([disabled])").wait_for(state="visible", timeout=15000)
  page.locator("#compare-selected-projects-button").click()
  ```
  Работает, но привязано к тексту "Select for comparison" — при изменении копирайтинга (en.json key, любой i18n switcher в ходе smoke) селектор сломается.
- **React компонент.** Найти компонент сайдбара, который рендерит список проектов с чекбоксами "Select for comparison" и кнопку `#compare-selected-projects-button`. Точное имя — разобраться самостоятельно через `grep -rn "compare-selected-projects-button" app/frontend/src/`. Скорее всего `SidebarPanel.tsx` или `ProjectCompareList.tsx`.
- **Playwright docs** на этот паттерн: https://playwright.dev/python/docs/locators#locate-by-test-id — `get_by_test_id()` читает `data-testid` по умолчанию.
- **Не трогать** backend, CI workflow `.github/workflows/test.yml`, `.lighthouserc.json`, badges, demo screenshots, e2e-тесты в `app/frontend/e2e/` (если они не ссылаются на compare-flow — там своя accessibility-first стратегия, её сохранить).

## Deliverables

1. **Frontend (TypeScript/React) — добавить data-testid-ы, сохранить все существующие aria/role/id:**
   - Wrapper `<section>` или `<div>`, в котором живёт список compare-чекбоксов + кнопка:
     ```tsx
     data-testid="project-compare-panel"
     ```
   - Каждый чекбокс `<input type="checkbox">` в compare-списке:
     ```tsx
     data-testid="project-compare-checkbox"
     data-project-id={project.id}
     // aria-label / accessible name "Select for comparison" ОСТАЮТСЯ как есть
     ```
   - Кнопка `#compare-selected-projects-button`:
     ```tsx
     data-testid="project-compare-submit"
     // id="compare-selected-projects-button" НЕ удалять — backward compat
     ```
   - Всё остальное в компоненте не трогать.

2. **`scripts/run_local_smoke.py` — переписать блок compare на testid:**
   ```python
   from playwright.sync_api import expect
   # ... в блоке "opening comparison dashboard":
   page.get_by_role("button", name="Projects", exact=True).click()

   compare_panel = page.get_by_test_id("project-compare-panel")
   compare_checkboxes = compare_panel.get_by_test_id("project-compare-checkbox")
   compare_submit = compare_panel.get_by_test_id("project-compare-submit")

   expect(compare_panel, "Compare panel should be visible.").to_be_visible(timeout=10_000)
   expect(
       compare_checkboxes.nth(1),
       "Compare flow should expose at least two visible project checkboxes.",
   ).to_be_visible(timeout=10_000)

   for index in (0, 1):
       checkbox = compare_checkboxes.nth(index)
       expect(checkbox, f"Compare checkbox #{index + 1} should be enabled.").to_be_enabled(timeout=5_000)
       checkbox.check()

   expect(
       compare_panel.locator('[data-testid="project-compare-checkbox"]:checked'),
       "Exactly two compare checkboxes should be selected before submit.",
   ).to_have_count(2, timeout=5_000)

   expect(compare_submit, "Compare submit should be enabled after selecting two projects.").to_be_enabled(timeout=5_000)
   compare_submit.click()
   ```
   Replace — не держать старый локатор закомментированным.

3. **Фронтенд-тесты (unit/RTL), ЕСЛИ они уже покрывают compare-UI:**
   - Найти существующие тесты, которые используют accessible-name селекторы на compare-чекбоксы (`getByRole("checkbox", { name: /comparison/i })` и т. п.).
   - Обновить их на `getByTestId("project-compare-checkbox")` только там, где это делает намерение теста чище (compare-specific assertions). Если тест проверяет именно accessible name — оставить accessible-name селектор, не трогать.
   - **Не добавлять** новый файл теста только ради проверки testid — testid тестируется через smoke.

## Acceptance
- `python scripts/run_local_smoke.py --skip-build` на Windows → exit 0, compare dashboard открывается, скриншоты регенерятся.
- `npm --prefix app/frontend run typecheck` → 0 ошибок.
- `npm --prefix app/frontend run test` → зелёный (unit-тесты не упали от перестановок).
- `grep -rn "role=\"option\"" app/frontend/src` → пусто (не вернули старые роли обратно).
- `grep -rn "\\[role=\\\\\"option\\\\\"\\] input" scripts/ app/frontend/e2e/` → пусто (нет старого локатора нигде).
- `grep -rn "compare-selected-projects-button" app/frontend/src/` → все находки сохраняют старый `id`.
- CI после push: `verify (ubuntu-latest, --with-e2e --with-coverage ...)` зелёный.
- Один коммит: `refactor(smoke): adopt data-testid contract for project-compare panel`.

## Notes
- `id="compare-selected-projects-button"` НЕ удалять — может быть ссылка из e2e-тестов или документации.
- `aria-label` на чекбоксах оставить (скринридеры + debug). testid-ы — только для smoke.
- Backend не трогать.
- Если по ходу обнаружится, что compare-чекбоксы рендерятся в нескольких местах (sidebar + modal + ещё где-то) — добавить testid-ы **только в ту панель, которую ходит smoke** (sidebar). Остальные места оставить.
- Отчёт в конце (5-10 строк): путь найденного компонента, diff testid-ов, какие frontend-тесты обновлены (если есть), финальный smoke exit code.
