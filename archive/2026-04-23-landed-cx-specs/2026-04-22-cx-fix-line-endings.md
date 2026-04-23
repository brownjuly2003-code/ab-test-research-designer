# CX Task: Fix CRLF drift in generated API contract breaking CI on Ubuntu

## Goal
Починить падение GitHub Actions `verify` job на Ubuntu и Windows runner'ах. Root cause — line endings: `app/frontend/src/lib/generated/api-contract.ts` закоммичен с CRLF, но `scripts/generate_frontend_api_types.py` на Linux пишет LF → `--check` ловит diff → CI exit 1. Решение: (1) добавить `.gitattributes` с `* text=auto eol=lf` + исключения для Windows-скриптов, (2) `git add --renormalize .` для нормализации всех текстовых файлов в репо на LF, (3) в `scripts/generate_frontend_api_types.py` при записи явно указать `newline="\n"`, чтобы регенерация на Windows не возвращала CRLF обратно.

## Context
- **Репо.** `D:\AB_TEST\`, `main`, HEAD `914e26ff` (после публикации v1.1.0 и HF demo). Не ветка, не push.
- **Симптом CI.** Run `24785461941` (`https://github.com/brownjuly2003-code/ab-test-research-designer/actions/runs/24785461941`) завершился `failure`. Оба `verify` job падают одинаково:
  ```
  app/frontend/src/lib/generated/api-contract.ts is out of date
  [verify] generated api contracts: python scripts/generate_frontend_api_types.py --check
  Process completed with exit code 1
  ```
  `docker` job зелёный, `lighthouse` skipped (`needs: verify`).
- **Root cause.** Локальная проверка:
  - `file app/frontend/src/lib/generated/api-contract.ts` → `ASCII text, with CRLF line terminators`.
  - `python scripts/generate_frontend_api_types.py --check` → **up to date** (потому что локально Windows: скрипт пишет CRLF, файл в репо CRLF, match).
  - В репо нет `.gitattributes`. Git default на Linux = `core.autocrlf=input`, т. е. git не трогает CRLF при checkout. Скрипт `generate_frontend_api_types.py` использует `Path.write_text(...)` без `newline=` → Python на Linux пишет `\n` → сгенерированный in-memory контент имеет LF, а файл на диске CRLF → `--check` (байт-в-байт сравнение) падает.
  - На Windows CI симметрично: `verify_all.py` делегирует в `.cmd`-flow, где `scripts/verify_all.cmd` запускает `generate_frontend_api_types.py --check`, и хотя Windows пишет CRLF, actions/checkout@v4 на Windows runner может нормализовать EOL по-другому — наблюдается тот же exit 1.
- **НЕ ИЗМЕНЯТЬ** backend OpenAPI schema, НЕ регенерировать сам `api-contract.ts` вручную с новыми типами — он и так правильный, проблема только в формате newlines.
- **Связанные файлы.**
  - `scripts/generate_frontend_api_types.py` — writer, здесь минимальный патч.
  - `scripts/verify_all.py` / `scripts/verify_all.cmd` — вызывают генератор с `--check`. Не трогать.
  - `.github/workflows/test.yml` — не трогать. Должен позеленеть автоматически после фикса.
  - `pytest.ini`, `requirements.txt` — не трогать.

## Deliverables

1. **`.gitattributes` в корне:**
   ```gitattributes
   # Default to LF for all text files; Git converts on checkout to native on platforms
   # that have eol=native, but these explicit rules keep generated artifacts stable.
   * text=auto eol=lf

   # Windows-only scripts must stay CRLF so cmd.exe / powershell parse them cleanly
   *.bat text eol=crlf
   *.cmd text eol=crlf
   *.ps1 text eol=crlf

   # Generated frontend contract is regenerated from backend OpenAPI and must be LF
   app/frontend/src/lib/generated/*.ts text eol=lf

   # Binary artefacts are never normalized
   *.png binary
   *.jpg binary
   *.jpeg binary
   *.gif binary
   *.ico binary
   *.pdf binary
   *.zip binary
   *.tar.gz binary
   *.sqlite3 binary
   *.db binary
   ```
   Комментарии — краткие, без markdown.

2. **Нормализация существующих файлов:**
   - Выполнить `git add --renormalize .`
   - Проверить `git status --short` — будут изменения для всех файлов, у которых текущие line endings не соответствуют правилам `.gitattributes`. Ожидается, что основной diff — `api-contract.ts` (CRLF → LF) + возможно несколько других text-файлов, которые были закоммичены с CRLF случайно.
   - Просмотреть список через `git diff --cached --stat` перед коммитом; если затрагиваются **binary** файлы (PNG, SQLite, zip) — значит `.gitattributes` недостаточно исчерпывающий, дополнить его и повторить renormalize. Coммит допустим только когда в diff --stat нет binary-файлов.

3. **Patch `scripts/generate_frontend_api_types.py`:**
   - Найти место записи финального TypeScript в файл (скорее всего `Path(...).write_text(content)` или `open(...) as f: f.write(...)`).
   - Передать `newline="\n"` в write/open, чтобы на Windows файл не возвращался к CRLF при регенерации:
     ```python
     output_path.write_text(rendered, encoding="utf-8", newline="\n")
     ```
     или:
     ```python
     with output_path.open("w", encoding="utf-8", newline="\n") as fp:
         fp.write(rendered)
     ```
   - Если в скрипте ещё где-то есть write другого файла (например, промежуточный JSON) — оставить без изменений, это не про него.

4. **Проверка `--check` режима:**
   - В том же скрипте убедиться, что `--check` делает побайтовое сравнение in-memory сгенерированного контента vs прочитанного с диска **без** text-mode нормализации. То есть чтение через `read_bytes()` или `open(..., "rb")`, не `read_text()`. Если сейчас `read_text()` — заменить на `read_bytes()` и сравнивать с `.encode("utf-8")` rendered значения. Это убирает риск повторения EOL-drift bugs в будущем.

5. **Local verify:**
   - `python scripts/generate_frontend_api_types.py --check` → exit 0.
   - `file app/frontend/src/lib/generated/api-contract.ts` → должно быть `ASCII text` БЕЗ `with CRLF line terminators` (т.е. LF).
   - Повторный `python scripts/generate_frontend_api_types.py` (без `--check`, перезапись) → файл остаётся LF, `git diff app/frontend/src/lib/generated/api-contract.ts` пустой.
   - `scripts/verify_all.cmd --with-e2e` → exit 0.

6. **Один коммит:**
   ```
   chore: normalize line endings via .gitattributes to fix api-contract drift on ubuntu ci
   ```
   Co-Authored-By: Codex <noreply@anthropic.com>
   В коммит: `.gitattributes`, `app/frontend/src/lib/generated/api-contract.ts` (renormalized), `scripts/generate_frontend_api_types.py` (patch), любые другие файлы, которые всплыли в `--renormalize` (ожидаемо немного), этот CX-файл, отчёт.

7. **Отчёт `docs/plans/2026-04-22-fix-line-endings-report.md`:**
   - Полный `git diff --cached --stat` перед коммитом (сколько файлов нормализовано).
   - Вывод `file` на `api-contract.ts` до и после.
   - `scripts/verify_all.cmd --with-e2e` exit code.
   - Ссылка на failing CI run (`24785461941`) для истории.
   - Инструкция юзеру: после push на main следующий CI run должен быть зелёным на обеих платформах.

## Acceptance
- `.gitattributes` существует в корне репо с правилами выше.
- `file app/frontend/src/lib/generated/api-contract.ts` не содержит `CRLF`.
- `python scripts/generate_frontend_api_types.py --check` exit 0 локально И должен быть зелёным на Ubuntu CI после push (это проверяет юзер, но логически должно работать).
- `scripts/verify_all.cmd --with-e2e` exit 0.
- `git status --short` пусто после коммита.
- Коммит subject уникальный (`git log --oneline -20 | awk '{$1=""; print}' | sort | uniq -d` == пусто).
- `git log -1 --stat` показывает изменения в `.gitattributes`, `api-contract.ts`, `scripts/generate_frontend_api_types.py` как минимум.
- CX-файл застейджен в коммит.
- **НЕ** push на remote. Юзер делает сам после review.

## How
1. Baseline: `git status --short` → только untracked `docs/plans/codex-tasks/2026-04-22-cx-*.md` (ок, игнорить пока); `git log --oneline -3` подтвердить HEAD = `914e26ff`.
2. Прочитать `scripts/generate_frontend_api_types.py` целиком — понять текущий паттерн write + check.
3. Создать `.gitattributes` по спецификации из #1.
4. `git add .gitattributes`.
5. `git add --renormalize .` — просмотреть `git diff --cached --stat`. Если binary файлы оказались в diff — расширить `.gitattributes` (добавить расширение в binary-секцию) и повторить. Итерировать пока в diff только текст.
6. Патчить `scripts/generate_frontend_api_types.py`: `newline="\n"` в write, `read_bytes()` в check.
7. Прогнать `python scripts/generate_frontend_api_types.py --check` — должен быть up to date.
8. `file app/frontend/src/lib/generated/api-contract.ts` — подтвердить LF.
9. `scripts/verify_all.cmd --with-e2e`.
10. `git add scripts/generate_frontend_api_types.py docs/plans/codex-tasks/2026-04-22-cx-fix-line-endings.md docs/plans/2026-04-22-fix-line-endings-report.md`.
11. Commit с указанным subject.
12. Финальный `git status --short` → пусто.

## Notes
- **НЕ** использовать `dos2unix` как основной инструмент. Git renormalize через `.gitattributes` — канонический путь, воспроизводимый на любом клоне репо.
- **НЕ** запускать `git config core.autocrlf` локально — это меняет глобальный/локальный Git config юзера, что выходит за scope репо. Только `.gitattributes`.
- **НЕ** трогать `*.bat`/`*.cmd`/`*.ps1` содержимое — `.gitattributes` оставляет им CRLF, потому что cmd.exe требует его для многострочных скриптов.
- **НЕ** коммитить `node_modules/`, `.pytest_cache/`, `.lighthouseci/`, `playwright-smoke-artifacts/` — если после renormalize они попали в staging (не должно, они в .gitignore), исключить.
- **НЕ** делать отдельный коммит «.gitattributes only» и отдельный «renormalize» — один коммит удобнее для истории и для `git blame` на api-contract.ts.
- Если после renormalize в diff всплывают `.py` или `.md` файлы массово — это ОК, это одноразовая чистка. Проверить, что их содержание не меняется по смыслу (только EOL).
- Если `.ipynb` / `.json` файлы всплывают — тоже ОК, они тоже text. Но убедиться, что они остаются валидным JSON после нормализации (большинство JSON парсеров EOL-agnostic).
- Если вдруг Python-скрипт где-то использует `subprocess.run(...)` с текстовым парсингом output — `.gitattributes` не влияет на pipe, только на file checkout. Не трогать subprocess-код.
- `scripts/run_local_smoke.py`, `scripts/run_lighthouse_ci.py` — не трогать.
- Windows-specific тесты на CI (verify windows-latest) тоже должны позеленеть после этого фикса, потому что CRLF→LF на Windows runner'е с `.gitattributes eol=lf` работает корректно (Git для Windows уважает gitattributes).
- Если после фикса локальный `verify` на Windows начинает жаловаться на EOL где-то ещё — смотреть stacktrace, допилить `.gitattributes`. Не откатывать.
- Связь с остальными 5 CX-тасками: этот фикс — **пре-реквизит** для публикации v1.2.0 или любого другого tag, т.к. сейчас main красный. Должен landed первым, до всех других тасков из roadmap.

## Out of scope
- Миграция CI на другой runner OS.
- Замена `generate_frontend_api_types.py` на openapi-typescript generator.
- Переход на `pre-commit` hooks для auto-regenerate контракта.
- Добавление `.editorconfig` (отдельный мелкий таск если захочется).
- Chasing down ВСЕ CRLF файлы в истории (renormalize делает snapshot на HEAD, прошлые коммиты не трогаются — так и надо).
- Переписывание git history через `git filter-branch` / `git filter-repo`.
- Релиз v1.1.1 / v1.2.0 — только фикс CI, без bump версии.
