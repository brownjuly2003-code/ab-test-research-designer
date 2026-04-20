from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent


ROOT = Path(r"D:\AI_state_new")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, file_name: str) -> str:
    if old not in text:
        raise ValueError(f"{file_name}: expected snippet not found")
    return text.replace(old, new, 1)


def replace_once_or_skip(text: str, old: str, new: str, file_name: str) -> str:
    if new in text:
        return text
    return replace_once(text, old, new, file_name)


def replace_once_if_present(text: str, old: str, new: str) -> str:
    if new in text or old not in text:
        return text
    return text.replace(old, new, 1)


def replace_regex_once(text: str, pattern: str, repl: str, file_name: str) -> str:
    updated, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise ValueError(f"{file_name}: expected one regex match for {pattern!r}, got {count}")
    return updated


def extract_div_block(text: str, start: int) -> tuple[str, int]:
    if not text.startswith("<div", start):
        raise ValueError("extract_div_block must start at <div")
    pos = start
    depth = 0
    while True:
        next_open = text.find("<div", pos)
        next_close = text.find("</div>", pos)
        if next_close == -1:
            raise ValueError("unterminated <div> block")
        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
            continue
        depth -= 1
        pos = next_close + len("</div>")
        if depth == 0:
            return text[start:pos], pos


def append_css() -> None:
    path = ROOT / "css" / "style.css"
    text = read_text(path)
    if ".interpretation {" in text and ".chapter-thesis {" in text:
        return
    addition = dedent(
        """

        /* ── Author interpretation marker ── */
        .interpretation {
          border-left: 3px solid #F5C518;
          padding: 12px 20px;
          margin: 24px 0;
          background: #fefdf0;
          font-size: 0.92rem;
          line-height: 1.7;
        }

        .interpretation::before {
          content: 'Интерпретация данных';
          display: block;
          font-style: normal;
          font-weight: 400;
          font-size: 0.72rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: #b8960a;
          margin-bottom: 8px;
        }

        /* ── Chapter thesis ── */
        .chapter-thesis {
          font-family: var(--heading-font);
          font-size: 1.18rem;
          font-weight: 300;
          color: var(--text);
          border-bottom: 1px solid var(--border);
          padding-bottom: 20px;
          margin: 20px 0 28px;
          line-height: 1.5;
        }
        """
    ).rstrip() + "\n"
    write_text(path, text.rstrip() + addition)


def update_index() -> None:
    path = ROOT / "index.html"
    text = read_text(path)
    if (
        (
            '<div class="hero" style="margin: -36px -64px 28px; padding: 56px 64px 36px;">' in text
            and '<div class="exec-context" style="margin: 16px 0 24px; gap: 20px; align-items: start;">' in text
            and 'style="font-size: 0.88rem; line-height: 1.42;"' in text
        )
        or (
            '<div class="hero">' in text
            and '<div class="exec-context">' in text
            and 'Инференс подешевел в 280 раз. DeepSeek — за $5.6M. 41% кода пишет AI. Gartner: началась фаза разочарования.' in text
            and '<li><strong>Основатели и CTO</strong> — собирать самим или покупать и как выбирать стек</li>' in text
        )
    ):
        return

    text = replace_once_or_skip(
        text,
        "<p>800M еженедельных пользователей ChatGPT. $202B венчурных инвестиций за 2025. Но 95% корпоративных пилотов не дают ROI, 42% компаний свернули AI-инициативы. Технология работает для одного человека с промптом — и ломается, когда её пытаются масштабировать на организацию.</p>",
        "<p>800M пользователей и $202B инвестиций — и одновременно 95% пилотов без ROI. Масштаб и провал существуют одновременно.</p>",
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        "<p>$560B capex за два года. $61B совокупной выручки AI-компаний. NVIDIA получает ~80% прибыли всего сектора. OpenAI тратит $1.69 на каждый $1 дохода. Рынок перевёрнут: продавцы лопат зарабатывают, золотоискатели — нет.</p>",
        "<p>$560B вложено, $61B выручки. NVIDIA забирает 80% прибыли сектора. Золотоискатели платят лопатчикам.</p>",
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        "<p>Inference подешевел в 280x. DeepSeek доказал, что конкурентную модель можно обучить за $5.6M. Вайбкодинг — слово года, 41% кода пишет AI. Gartner Hype Cycle входит в Trough of Disillusionment. Тот, кто инвестирует в реальные use cases, а не в хайп, выиграет к 2028.</p>",
        "<p>Inference подешевел в 280x. DeepSeek — за $5.6M. 41% кода пишет AI. Gartner говорит: Trough of Disillusionment начался.</p>",
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        """<ul>
          <li>DeepSeek R1 — модель уровня GPT-4o за $5.6M, обвал NVIDIA на $600B за день</li>
          <li>41% кода пишет AI, «vibe coding» — слово года Collins Dictionary</li>
          <li>AI-агенты перешли из лабораторий в production, рынок $7.5B</li>
          <li>Inference подешевел в 280x за 2 года, ценовая война началась</li>
          <li>OpenAI конвертировалась в for-profit: $300B → $730B</li>
        </ul>""",
        """<ul>
          <li>DeepSeek R1 — модель уровня GPT-4o за $5.6M, обвал NVIDIA на $600B за день</li>
          <li>41% кода пишет AI, «vibe coding» — слово года Collins Dictionary</li>
          <li>Inference подешевел в 280x за 2 года, ценовая война началась</li>
        </ul>""",
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        '<p>10 профилей компаний: от OpenAI ($730B) до Midjourney ($0 инвестиций). Сильные и слабые стороны каждой.</p>',
        '<p>10 профилей компаний: от OpenAI ($730–830B) до Midjourney ($0 инвестиций). Сильные и слабые стороны каждой.</p>',
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        '<p>Что реально, а что agent-washing. Рынок $7.5B сегодня, прогноз $199B к 2033.</p>',
        '<p>Что реально, а что agent-washing. Рынок $7–8B сегодня, прогноз $199B к 2033.</p>',
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        '<div class="hero">',
        '<div class="hero" style="margin: -36px -64px 28px; padding: 56px 64px 36px;">',
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        '<p class="lead">Факты, деньги и прогнозы — исследование рынка искусственного интеллекта на 250+ источниках</p>',
        '<p class="lead" style="font-size: 1.05rem; line-height: 1.5; margin-bottom: 12px;">Факты, деньги и прогнозы — исследование AI-рынка на 250+ источниках</p>',
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        '<p class="meta">Март 2026</p>',
        '<p class="meta" style="margin-bottom: 0;">Март 2026</p>',
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        '<h2>Три тезиса</h2>',
        '<h2 style="margin-top: 0; margin-bottom: 10px;">Три тезиса</h2>',
        "index.html",
    )
    if 'class="exec-thesis" style="padding: 16px 0;"' not in text:
        text = text.replace('<div class="exec-thesis">', '<div class="exec-thesis" style="padding: 16px 0;">')
    text = replace_once_or_skip(
        text,
        '<div class="exec-context">',
        '<div class="exec-context" style="margin: 16px 0 24px; gap: 20px; align-items: start;">',
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        """<ul>
          <li>DeepSeek R1 — модель уровня GPT-4o за $5.6M, обвал NVIDIA на $600B за день</li>
          <li>41% кода пишет AI, «vibe coding» — слово года Collins Dictionary</li>
          <li>Inference подешевел в 280x за 2 года, ценовая война началась</li>
        </ul>""",
        """<ul style="font-size: 0.82rem; line-height: 1.35; margin: 0; padding-left: 18px;">
          <li>DeepSeek R1: уровень GPT-4o за $5.6M</li>
          <li>41% кода пишет AI, vibe coding стал массовым</li>
          <li>Inference дешевле в 280x, ценовая война началась</li>
        </ul>""",
        "index.html",
    )
    text = replace_once_or_skip(
        text,
        """<ul>
          <li><strong>Founders и CTO</strong> — решения о build vs buy, выбор стека</li>
          <li><strong>Инвесторы</strong> — оценка AI-компаний, где маржа, где пузырь</li>
          <li><strong>Аналитики</strong> — данные, прогнозы, конкурентный ландшафт</li>
          <li><strong>Разработчики</strong> — инструменты, цены, реальная производительность</li>
          <li><strong>Все, кто устал от hype</strong> — факты, цифры, доказательная база</li>
        </ul>""",
        """<ul style="font-size: 0.82rem; line-height: 1.35; margin: 0; padding-left: 18px;">
          <li><strong>Founders и CTO</strong> — build vs buy и выбор стека</li>
          <li><strong>Инвесторы и аналитики</strong> — где маржа, пузырь и устойчивость</li>
          <li><strong>Команды внедрения</strong> — качество, цены и рабочие кейсы</li>
        </ul>""",
        "index.html",
    )
    if 'style="font-size: 0.88rem; line-height: 1.42;"' not in text:
        text = text.replace(
            '<p>800M пользователей и $202B инвестиций — и одновременно 95% пилотов без ROI. Масштаб и провал существуют одновременно.</p>',
            '<p style="font-size: 0.88rem; line-height: 1.42;">800M пользователей и $202B инвестиций — и одновременно 95% пилотов без ROI. Масштаб и провал существуют одновременно.</p>',
        )
        text = text.replace(
            '<p>$560B вложено, $61B выручки. NVIDIA забирает 80% прибыли сектора. Золотоискатели платят лопатчикам.</p>',
            '<p style="font-size: 0.88rem; line-height: 1.42;">$560B вложено, $61B выручки. NVIDIA забирает 80% прибыли сектора. Золотоискатели платят лопатчикам.</p>',
        )
        text = text.replace(
            '<p>Inference подешевел в 280x. DeepSeek — за $5.6M. 41% кода пишет AI. Gartner говорит: Trough of Disillusionment начался.</p>',
            '<p style="font-size: 0.88rem; line-height: 1.42;">Inference подешевел в 280x. DeepSeek — за $5.6M. 41% кода пишет AI. Gartner говорит: Trough of Disillusionment начался.</p>',
        )

    header_idx = text.index("<h2>26 разделов исследования</h2>")
    start = text.index('<div class="section-preview">', header_idx)
    end = text.index('<div class="verdict">', start)
    section = text[start:end]
    blocks: list[str] = []
    cursor = 0
    while True:
        idx = section.find('<div class="section-preview">', cursor)
        if idx == -1:
            break
        block, cursor = extract_div_block(section, idx)
        blocks.append(block.strip())
    if len(blocks) != 26:
        raise ValueError(f"index.html: expected 26 section-preview blocks, got {len(blocks)}")
    ordered = sorted(
        blocks,
        key=lambda block: int(re.search(r'<div class="section-number">(\d+)</div>', block).group(1)),  # type: ignore[union-attr]
    )
    new_section = "    " + "\n\n    ".join(ordered) + "\n\n"
    text = text[:start] + new_section + text[end:]

    write_text(path, text)


def update_pricing_tables_sort() -> None:
    path = ROOT / "09-pricing-tables.html"
    text = read_text(path)
    if 'id="compact-sort-styles"' in text and 'class="sort-arrow"' in text:
        return

    sort_script = dedent(
        """
        <script>
        (function() {
          if (!document.getElementById('compact-sort-styles')) {
            document.head.insertAdjacentHTML('beforeend', `
              <style id="compact-sort-styles">
                .sort-arrow {
                  margin-left: 5px;
                  font-size: 0.75em;
                  opacity: 0.5;
                  user-select: none;
                }
                th:hover .sort-arrow {
                  opacity: 1;
                }
                th[data-sort] .sort-arrow {
                  opacity: 1;
                  color: #b8960a;
                }
              </style>
            `);
          }

          var defaultArrow = '⇅';
          var ascArrow = '↑';
          var descArrow = '↓';
          var missingTokens = new Set(['', '—', '-', 'н/д', 'недоступно', 'недоступен']);

          function normalizeText(value) {
            return (value || '').replace(/\\s+/g, ' ').trim();
          }

          function normalizeKey(value) {
            return normalizeText(value).toLowerCase();
          }

          function isMissing(value) {
            return missingTokens.has(normalizeKey(value));
          }

          function isNumericLike(value) {
            var compact = normalizeText(value).replace(/\\s+/g, '');
            return /^[~≈]?[€$£₹]/.test(compact)
              || /^[~≈+\\-]?\\d[\\d.,%/]*$/.test(compact)
              || /^[~≈+\\-]?\\d[\\d.,]*[–-]\\d[\\d.,%/]*$/.test(compact);
          }

          function parseNumber(value) {
            var text = normalizeText(value).replace(/−/g, '-');
            var match = text.match(/[+\\-]?\\d[\\d.,]*/);
            if (!match) {
              return null;
            }

            var token = match[0];
            var hasComma = token.indexOf(',') !== -1;
            var hasDot = token.indexOf('.') !== -1;

            if (hasComma && hasDot) {
              if (token.lastIndexOf(',') > token.lastIndexOf('.')) {
                token = token.replace(/\\./g, '').replace(',', '.');
              } else {
                token = token.replace(/,/g, '');
              }
            } else if (hasComma) {
              var parts = token.split(',');
              if (parts.length > 2 || (parts.length == 2 && parts[1].length == 3 && parts[0].length > 1)) {
                token = parts.join('');
              } else {
                token = token.replace(',', '.');
              }
            }

            var parsed = Number(token);
            return Number.isNaN(parsed) ? null : parsed;
          }

          function getComparable(rawValue) {
            var textValue = normalizeText(rawValue);
            if (isMissing(textValue)) {
              return { kind: 'missing', text: textValue, number: null };
            }

            if (isNumericLike(textValue)) {
              var parsed = parseNumber(textValue);
              if (parsed !== null) {
                return { kind: 'number', text: textValue, number: parsed };
              }
            }

            return { kind: 'text', text: textValue, number: null };
          }

          function getHeaderStartIndex(headers, targetHeader) {
            var offset = 0;
            for (var i = 0; i < headers.length; i += 1) {
              if (headers[i] === targetHeader) {
                return offset;
              }
              offset += Number(headers[i].getAttribute('colspan') || 1);
            }
            return 0;
          }

          function getCellText(row, targetIndex) {
            var cells = Array.prototype.slice.call(row.children);
            var offset = 0;
            for (var i = 0; i < cells.length; i += 1) {
              var cell = cells[i];
              var span = Number(cell.getAttribute('colspan') || 1);
              if (targetIndex >= offset && targetIndex < offset + span) {
                return normalizeText(cell.textContent);
              }
              offset += span;
            }
            return '';
          }

          function compareValues(a, b, direction) {
            var kindOrder = { number: 0, text: 1, missing: 2 };
            if (kindOrder[a.kind] !== kindOrder[b.kind]) {
              return kindOrder[a.kind] - kindOrder[b.kind];
            }

            if (a.kind === 'missing') {
              return 0;
            }

            if (a.kind === 'number') {
              return direction === 'desc' ? b.number - a.number : a.number - b.number;
            }

            var result = a.text.localeCompare(b.text, undefined, {
              numeric: true,
              sensitivity: 'base',
            });
            return direction === 'desc' ? -result : result;
          }

          Array.prototype.slice.call(document.querySelectorAll('table.compact')).forEach(function(table) {
            var thead = table.querySelector('thead');
            var tbody = table.querySelector('tbody');
            if (!thead || !tbody) {
              return;
            }

            var headers = Array.prototype.slice.call(thead.querySelectorAll('th'));
            var bodyRows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
            var state = { column: null, direction: null };

            bodyRows.forEach(function(row, index) {
              row.dataset.index = String(index);
            });

            function resetIndicators() {
              headers.forEach(function(header) {
                header.removeAttribute('data-sort');
                var arrow = header.querySelector('.sort-arrow');
                if (arrow) {
                  arrow.textContent = defaultArrow;
                }
              });
            }

            function renderRows(rows) {
              rows.forEach(function(row) {
                tbody.appendChild(row);
              });
            }

            headers.forEach(function(header) {
              header.style.cursor = 'pointer';

              if (!header.querySelector('.sort-arrow')) {
                header.insertAdjacentHTML('beforeend', '<span class="sort-arrow">' + defaultArrow + '</span>');
              }

              header.addEventListener('click', function() {
                var columnIndex = getHeaderStartIndex(headers, header);
                var nextDirection = 'asc';

                if (state.column === columnIndex) {
                  if (state.direction === 'asc') {
                    nextDirection = 'desc';
                  } else if (state.direction === 'desc') {
                    nextDirection = null;
                  }
                }

                resetIndicators();

                if (!nextDirection) {
                  state.column = null;
                  state.direction = null;
                  renderRows(
                    bodyRows.slice().sort(function(rowA, rowB) {
                      return Number(rowA.dataset.index) - Number(rowB.dataset.index);
                    })
                  );
                  return;
                }

                state.column = columnIndex;
                state.direction = nextDirection;
                header.dataset.sort = nextDirection;
                header.querySelector('.sort-arrow').textContent = nextDirection === 'asc' ? ascArrow : descArrow;

                renderRows(
                  bodyRows.slice().sort(function(rowA, rowB) {
                    var comparableA = getComparable(getCellText(rowA, columnIndex));
                    var comparableB = getComparable(getCellText(rowB, columnIndex));
                    var result = compareValues(comparableA, comparableB, nextDirection);

                    if (result !== 0) {
                      return result;
                    }

                    return Number(rowA.dataset.index) - Number(rowB.dataset.index);
                  })
                );
              });
            });
          });
        })();
        </script>
        """
    ).strip()

    text = replace_once_or_skip(
        text,
        '<script src="js/main.js"></script>\n</body>',
        f'<script src="js/main.js"></script>\n{sort_script}\n</body>',
        "09-pricing-tables.html",
    )
    write_text(path, text)


THESES = {
    "01-evolution.html": "Рынок AI вырос не из прорыва, а из стечения трёх независимых факторов — вычислительной мощности, данных и архитектуры Transformer. Убери любой один — ChatGPT не случился бы.",
    "02-leaders.html": "Из десяти компаний прибыльны единицы: Midjourney зарабатывает больше всех на сотрудника, OpenAI убыточен при $20B ARR.",
    "03-trends.html": "Восемь трендов объединяет одно: то, что год назад стоило $1000, сегодня стоит $3.60. Коммодитизация — не тренд, а закон.",
    "04-agents.html": "«Агент» — самое злоупотребляемое слово 2025–2026. Из тысяч продуктов с этим словом в названии реальную автономию демонстрируют единицы.",
    "05-adoption.html": "78% компаний «внедрили AI» — и 95% не могут показать ROI. Разрыв между внедрением и ценностью — главная бизнес-проблема 2026 года.",
    "06-skeptics.html": "Скептики оказались правы в 5 из 7 ключевых тезисов — но по неправильным причинам.",
    "07-layoffs.html": "AI-увольнения реальны, но паттерн неожиданный: больше всего теряют работу не низкоквалифицированные сотрудники, а junior white-collar.",
    "08-pricing.html": "$20 — не рыночная цена, а якорь, который OpenAI установил в 2023. Первый, кто опустит до $10, изменит всю индустрию.",
    "09-pricing-tables.html": "$20 в прайсе не означает одинаковую цену на рынке: налоги, PPP и региональные скидки превращают AI-подписки в мозаичный, а не глобально единый продукт.",
    "10-grey-market.html": "Серый рынок AI-подписок — это не маргинальное явление: $362B потерь от онлайн-мошенничества финансируют экосистему, в которой AI-аккаунты — один из самых востребованных товаров.",
    "11-cat-and-mouse.html": "Война между вендорами и обходчиками не заканчивается: каждая защита против abuse рождает новый способ арбитража, а контроль доступа становится отдельным продуктом.",
    "12-savings.html": "Экономить на AI можно почти до нуля, но каждая ступень скидки обменивает деньги на риск: от ограничений тарифов до прямого нарушения ToS.",
    "13-predictions.html": "Все прогнозы в этой главе — ставки, а не знание. Разброс по AGI: от 2027 (Musk) до «никогда» (LeCun).",
    "14-appendix.html": "Это приложение показывает, на каких источниках построено исследование и где в нём проходит граница между проверяемым фактом и авторской интерпретацией.",
    "15-geopolitics.html": "Чипы стали новой нефтью: контроль над производством TSMC важнее контроля над любым месторождением XXI века.",
    "16-infrastructure.html": "Главный лимит AI теперь задают не модели, а физическая инфраструктура: чипы, дата-центры и электроэнергия.",
    "17-legal.html": "Суды и регуляторы начинают определять экономику AI не меньше инженеров: правила обучения, дипфейки и liability становятся бизнес-факторами первого порядка.",
    "18-investments.html": "$202B венчурных денег показывают масштаб ставки на AI, но не снимают главный вопрос: где в этой системе появится устойчивая прибыль.",
    "19-vibe-coding.html": "Вайбкодинг ускоряет создание софта на порядок, но переносит главный навык разработчика из написания кода в формулировку задач, проверку и отладку результата.",
    "20-cybercrime.html": "AI делает киберпреступность дешевле, быстрее и правдоподобнее, поэтому преимущество всё чаще у нападающих, а не у защитников.",
    "21-evals.html": "93% на SWE-bench и неспособность посчитать буквы в слове «strawberry» — это не противоречие, это суть проблемы бенчмарков.",
    "22-enterprise.html": "Корпоративный AI провалился не технически, а организационно: 95% пилотов гибнут не от плохих моделей, а от отсутствия данных, governance и чемпиона внутри компании.",
    "23-economics.html": "В AI-стеке деньги текут снизу вверх: чипы прибыльны, облака инвестируют, модели убыточны, приложения только нащупывают маржу.",
    "24-data.html": "Дефицит качественных данных становится таким же стратегическим ограничением для AI, как дефицит чипов: лицензии, синтетика и data moat решают всё больше.",
    "25-industries.html": "AI проникает в отрасли неравномерно: финансы и медицина — лидеры по внедрению, госсектор и образование — по сопротивлению.",
    "26-scenarios.html": "Три сценария 2027–2030 различаются не технологией, а тем, кто из регуляторов, конкурентов и рынка труда окажется сильнее.",
}


def insert_chapter_theses() -> None:
    for file_name, thesis in THESES.items():
        path = ROOT / file_name
        text = read_text(path)
        if 'class="chapter-thesis"' in text:
            continue
        replacement = f"""\\1

    <div class="chapter-thesis">
      {thesis}
    </div>"""
        updated, count = re.subn(r'(<p class="lead">.*?</p>)', replacement, text, count=1, flags=re.S)
        if count != 1:
            raise ValueError(f"{file_name}: lead block not found")
        write_text(path, updated)


def update_appendix() -> None:
    path = ROOT / "14-appendix.html"
    text = read_text(path)

    rows = dedent(
        """
                <tr><td><a href="21-evals.html">Глава 21 — Оценка качества AI</a></td><td>SWE-bench, ARC-AGI, METR, Veracode</td></tr>
                <tr><td><a href="22-enterprise.html">Глава 22 — Enterprise playbook</a></td><td>McKinsey, Gartner Magic Quadrant, Forrester TEI</td></tr>
                <tr><td><a href="23-economics.html">Глава 23 — Экономика AI-стека</a></td><td>SemiAnalysis, Epoch AI, The Information</td></tr>
                <tr><td><a href="24-data.html">Глава 24 — Данные и контент</a></td><td>Epoch AI, MIT Technology Review, Nature</td></tr>
                <tr><td><a href="25-industries.html">Глава 25 — AI по отраслям</a></td><td>FDA, WHO, OECD, McKinsey Global Institute</td></tr>
                <tr><td><a href="26-scenarios.html">Глава 26 — Сценарии 2027–2030</a></td><td>Metaculus, AI Impacts Survey, Samotsvety</td></tr>
        """
    ).strip()

    anchor = """        <tr><td><a href="https://internationalaisafetyreport.org/publication/2026-report-executive-summary">International AI Safety Report 2026</a></td><td>Прогнозы (риски)</td></tr>
      </tbody>"""
    if "Глава 21 — Оценка качества AI" not in text:
        text = replace_once_or_skip(
            text,
            anchor,
            """        <tr><td><a href="https://internationalaisafetyreport.org/publication/2026-report-executive-summary">International AI Safety Report 2026</a></td><td>Прогнозы (риски)</td></tr>
""" + rows + """
      </tbody>""",
            "14-appendix.html",
        )

    text = replace_once_or_skip(
        text,
        "<p>Общий объём: 26 страниц, 250+ источников, 30+ интерактивных визуализаций.</p>",
        "<p>Общий объём: 26 страниц, 250+ источников, 35+ интерактивных визуализаций.</p>",
        "14-appendix.html",
    )
    write_text(path, text)


def update_cross_references() -> None:
    replacements = {
        "02-leaders.html": [
            ("ChatGPT (800 млн WAU)", "ChatGPT (800M WAU)"),
        ],
        "18-investments.html": [
            ("$202 млрд венчурного финансирования в 2025 году.", "$202B венчурного финансирования в 2025 году."),
        ],
        "23-economics.html": [
            ("<td>$300B → $730B</td>", "<td>$300B → $730–830B</td>"),
        ],
    }
    for file_name, pairs in replacements.items():
        path = ROOT / file_name
        text = read_text(path)
        for old, new in pairs:
            text = replace_once_or_skip(text, old, new, file_name)
        write_text(path, text)


def update_interpretations() -> None:
    path = ROOT / "03-trends.html"
    text = read_text(path)
    text = replace_once_or_skip(
        text,
        """<div class="takeaway">
      <div class="takeaway-title">Ключевой вывод</div>
      <p>Стоимость inference упала в 280 раз за 2 года — с $20 до $0.07 за миллион токенов. Это самое быстрое удешевление в истории технологий. Для сравнения: стоимость хранения данных падала в 10 раз за десятилетие, а здесь — в 280 раз за 2 года.</p>
    </div>""",
        """<div class="interpretation">
      <p>Стоимость inference упала в 280 раз за 2 года — с $20 до $0.07 за миллион токенов. Для рынка это означает не просто снижение себестоимости, а быстрый переход моделей в категорию коммодити.</p>
    </div>""",
        "03-trends.html",
    )
    text = replace_once_or_skip(
        text,
        """<div class="takeaway">
      <div class="takeaway-title">Ключевой вывод</div>
      <p>Open-source модели достигли 90% качества закрытых — при нулевой стоимости лицензии. DeepSeek R1, Llama 4, Mistral — все доступны бесплатно. Единственное преимущество закрытых моделей — инфраструктура (API, reliability, enterprise support). Это преимущество тает.</p>
    </div>""",
        """<div class="interpretation">
      <p>Open-source модели достигли 90% качества закрытых при нулевой стоимости лицензии. Данные указывают, что дифференциация всё быстрее смещается от самих моделей к инфраструктуре и продуктовой упаковке.</p>
    </div>""",
        "03-trends.html",
    )
    write_text(path, text)

    path = ROOT / "04-agents.html"
    text = read_text(path)
    text = replace_once_or_skip(
        text,
        """<div class="verdict">
      <div class="verdict-title">Вердикт</div>
      <p>AI-агенты — самый переоценённый и одновременно самый перспективный тренд 2026 года. Переоценённый — потому что 80% текущих 'агентов' не сложнее скриптов с LLM-обёрткой. Перспективный — потому что оставшиеся 20% действительно меняют рабочие процессы. Рынок вырастет с $7.5B до $199B, но <strong>95% текущих агентных стартапов будут поглощены или закрыты</strong>.</p>
    </div>""",
        """<div class="verdict">
      <div class="verdict-title">Вердикт</div>
      <p>AI-агенты — самый переоценённый и одновременно самый перспективный тренд 2026 года. Переоценённый — потому что 80% текущих 'агентов' не сложнее скриптов с LLM-обёрткой. Перспективный — потому что оставшиеся 20% действительно меняют рабочие процессы.</p>
    </div>

    <div class="interpretation">
      <p>По оценке автора, рынок вырастет с $7–8B до $199B, но большая часть текущих агентных стартапов будет поглощена или закрыта до наступления зрелости рынка.</p>
    </div>""",
        "04-agents.html",
    )
    write_text(path, text)

    path = ROOT / "06-skeptics.html"
    text = read_text(path)
    badge = '<p class="source-badge">Оценка автора на основе сопоставления аргументов с данными разделов 01–05</p>\n\n    <div class="takeaway">'
    if "Оценка автора на основе сопоставления аргументов с данными разделов 01–05" not in text:
            text = replace_once_or_skip(text, '<div class="takeaway">\n      <div class="takeaway-title">Ключевой вывод</div>\n      <p>Scorecard скептиков: 5 из 7 ключевых аргументов подтвердились фактами. Галлюцинации не решены, масштабирование буксует, экономика не сходится, внедрение переоценено, признаки пузыря налицо. Скептики были правы чаще, чем оптимисты.</p>\n    </div>', badge + '\n      <div class="takeaway-title">Ключевой вывод</div>\n      <p>Scorecard скептиков: 5 из 7 ключевых аргументов подтвердились фактами. Галлюцинации не решены, масштабирование буксует, экономика не сходится, внедрение переоценено, признаки пузыря налицо. Скептики были правы чаще, чем оптимисты.</p>\n    </div>', "06-skeptics.html")
    write_text(path, text)

    path = ROOT / "13-predictions.html"
    text = read_text(path)
    for heading, source in [
        ("<h3>Gartner</h3>", '<h3>Gartner</h3>\n    <p class="source-badge">Источник: Gartner</p>'),
        ("<h3>Forrester</h3>", '<h3>Forrester</h3>\n    <p class="source-badge">Источник: Forrester</p>'),
        ("<h3>IDC и Goldman Sachs</h3>", '<h3>IDC и Goldman Sachs</h3>\n    <p class="source-badge">Источники: IDC и Goldman Sachs</p>'),
    ]:
        if source not in text:
            text = replace_once_or_skip(text, heading, source, "13-predictions.html")
    duplicate_opinion = """    <div class="opinion">
      <strong>Прогноз автора:</strong> 2026 — Trough of Disillusionment, 30–40% AI-стартапов закроются. 2027 — ценовая война, $20 станет $10. 2028 — коррекция оценок на 40–60%. 2029–2030 — AI станет как электричество: невидимым и вездесущим. AGI к 2030 — маловероятно (25–30%). Это сценарий, не прогноз.
    </div>

"""
    if duplicate_opinion in text:
        text = text.replace(duplicate_opinion, "", 1)
    write_text(path, text)

    path = ROOT / "23-economics.html"
    text = read_text(path)
    text = replace_once_or_skip(
        text,
        """<div class="verdict">
      <div class="verdict-title">Вердикт</div>
      <p>AI-индустрия — это перевёрнутая пирамида: <strong>$560B capex</strong> ради <strong>$61B выручки</strong>. NVIDIA забирает прибыль, облака инвестируют в будущее, модельные компании сжигают кэш, а прикладные компании осторожно выходят на прибыль. Единственный путь к устойчивой экономике — либо модели радикально дешевеют (DeepSeek показал направление), либо AI создаёт новую ценность, которую можно монетизировать (агенты, вайбкодинг, enterprise automation). До тех пор это <strong>самая дорогая лотерея в истории</strong> — с призом в $10T+ рынок, если получится.</p>
    </div>""",
        """<div class="verdict">
      <div class="verdict-title">Вердикт</div>
      <p>AI-индустрия — это перевёрнутая пирамида: <strong>$560B capex</strong> ради <strong>$61B выручки</strong>. NVIDIA забирает прибыль, облака инвестируют в будущее, модельные компании сжигают кэш, а прикладные компании осторожно выходят на прибыль. Единственный путь к устойчивой экономике — либо модели радикально дешевеют (DeepSeek показал направление), либо AI создаёт новую ценность, которую можно монетизировать (агенты, вайбкодинг, enterprise automation).</p>
      <p><em>До тех пор это <strong>самая дорогая лотерея в истории</strong> — с призом в $10T+ рынок, если получится.</em></p>
    </div>
    <p class="source-badge">Авторская интерпретация структуры доходности сектора</p>""",
        "23-economics.html",
    )
    write_text(path, text)

    path = ROOT / "26-scenarios.html"
    text = read_text(path)
    for old in [
        '<h2 id="scenario-a">Сценарий A: Ускорение</h2>\n    <p><strong>Вероятность: ~25%</strong></p>\n\n    <div class="takeaway">',
        '<h2 id="scenario-b">Сценарий B: Плато и специализация</h2>\n    <p><strong>Вероятность: ~50%</strong></p>\n\n    <div class="takeaway">',
        '<h2 id="scenario-c">Сценарий C: Откат</h2>\n    <p><strong>Вероятность: ~25%</strong></p>\n\n    <div class="takeaway">',
    ]:
        if 'Гипотетический сценарий. Не прогноз.' in old:
            continue
        replacement = old.replace(
            "\n\n    <div class=\"takeaway\">",
            '\n    <p class="source-badge">Гипотетический сценарий. Не прогноз.</p>\n\n    <div class="takeaway">',
        )
        if replacement not in text:
            text = replace_once_or_skip(text, old, replacement, "26-scenarios.html")
    write_text(path, text)

    path = ROOT / "21-evals.html"
    text = read_text(path)
    text = replace_once_or_skip(
        text,
        """<div class="opinion">
      Гонка бенчмарков стала маркетинговым инструментом. Компании оптимизируют модели под конкретные тесты, выбирают выгодные конфигурации и скрывают неудобные результаты. Chatbot Arena остаётся единственным бенчмарком, где модели оцениваются «вслепую» реальными пользователями — но и он склоняется к стилю (длинный, подробный ответ побеждает), а не к точности.
    </div>""",
        """<div class="interpretation">
      Гонка бенчмарков стала маркетинговым инструментом. Компании оптимизируют модели под конкретные тесты, выбирают выгодные конфигурации и скрывают неудобные результаты. Chatbot Arena остаётся единственным бенчмарком, где модели оцениваются «вслепую» реальными пользователями — но и он склоняется к стилю (длинный, подробный ответ побеждает), а не к точности.
    </div>""",
        "21-evals.html",
    )
    write_text(path, text)


PAGE_ORDER = [
    "index.html",
    "01-evolution.html",
    "02-leaders.html",
    "03-trends.html",
    "04-agents.html",
    "05-adoption.html",
    "06-skeptics.html",
    "07-layoffs.html",
    "08-pricing.html",
    "09-pricing-tables.html",
    "10-grey-market.html",
    "11-cat-and-mouse.html",
    "12-savings.html",
    "13-predictions.html",
    "14-appendix.html",
    "15-geopolitics.html",
    "16-infrastructure.html",
    "17-legal.html",
    "18-investments.html",
    "19-vibe-coding.html",
    "20-cybercrime.html",
    "21-evals.html",
    "22-enterprise.html",
    "23-economics.html",
    "24-data.html",
    "25-industries.html",
    "26-scenarios.html",
]

PAGE_TITLES = {
    "index.html": "Главная",
    "01-evolution.html": "Эволюция рынка",
    "02-leaders.html": "Лидеры рынка",
    "03-trends.html": "Тенденции",
    "04-agents.html": "Бум агентов",
    "05-adoption.html": "AI в бизнесе и быту",
    "06-skeptics.html": "Скептики и критики",
    "07-layoffs.html": "Увольнения и труд",
    "08-pricing.html": "Цены на AI",
    "09-pricing-tables.html": "Таблицы цен",
    "10-grey-market.html": "Серый рынок",
    "11-cat-and-mouse.html": "Вендоры vs покупатели",
    "12-savings.html": "Как экономят",
    "13-predictions.html": "Прогнозы",
    "14-appendix.html": "Источники и методология",
    "15-geopolitics.html": "AI и геополитика",
    "16-infrastructure.html": "Инфраструктура",
    "17-legal.html": "AI и право",
    "18-investments.html": "Инвестиции",
    "19-vibe-coding.html": "Вайбкодинг",
    "20-cybercrime.html": "AI и киберпреступность",
    "21-evals.html": "Оценка качества AI",
    "22-enterprise.html": "Enterprise playbook",
    "23-economics.html": "Экономика AI-стека",
    "24-data.html": "Данные и контент",
    "25-industries.html": "AI по отраслям",
    "26-scenarios.html": "Сценарии 2027–2030",
}


def update_page_navs() -> None:
    for idx, file_name in enumerate(PAGE_ORDER[1:], start=1):
        prev_file = PAGE_ORDER[idx - 1]
        next_file = "14-appendix.html" if file_name == "26-scenarios.html" else PAGE_ORDER[idx + 1]
        nav = (
            '<div class="page-nav">\n'
            f'      <a href="{prev_file}">&larr; {PAGE_TITLES[prev_file]}</a>\n'
            f'      <a href="{next_file}">{PAGE_TITLES[next_file]} &rarr;</a>\n'
            "    </div>"
        )
        path = ROOT / file_name
        text = read_text(path)
        text = replace_regex_once(text, r'<div class="page-nav">.*?</div>', nav, file_name)
        write_text(path, text)


def update_infrastructure() -> None:
    path = ROOT / "16-infrastructure.html"
    text = read_text(path)
    text = replace_once_or_skip(
        text,
        "<tr><td>Microsoft</td><td>Three Mile Island — 20-летний PPA, $16B</td><td>835 МВт</td><td>Перезапуск к 2027</td></tr>",
        "<tr><td>Microsoft</td><td>Three Mile Island — 20-летний PPA, $16B</td><td>835 МВт</td><td>Перезапуск с 2028</td></tr>",
        "16-infrastructure.html",
    )

    insert = dedent(
        """

            <h2 id="datacenters">Крупнейшие AI-датацентры и кластеры 2026</h2>

            <table>
              <thead>
                <tr><th>Проект</th><th>Оператор</th><th>Мощность</th><th>Локация</th><th>Статус</th></tr>
              </thead>
              <tbody>
                <tr><td>Stargate I + новые площадки</td><td>OpenAI / Oracle / SoftBank</td><td>почти 7 ГВт в разработке</td><td>Техас + 5 площадок в США</td><td>Абилин запущен частично, ещё пять площадок объявлены</td></tr>
                <tr><td>Fairwater</td><td>Microsoft</td><td>сотни тысяч GPU, 10x Frontier</td><td>Маунт-Плезант, Висконсин</td><td>Строится; начало 2026 обозначалось как целевой срок запуска</td></tr>
                <tr><td>Colossus</td><td>xAI</td><td>200 000 GPU</td><td>Мемфис, Теннесси</td><td>Работает; расширение до 200K завершено</td></tr>
                <tr><td>Mistral Compute</td><td>Mistral AI / Fluidstack / Eclairion</td><td>18 000+ GPU, 40 МВт с ростом до 100+ МВт</td><td>Брюйер-ле-Шатель, Франция</td><td>Первая очередь введена, масштабирование продолжается</td></tr>
              </tbody>
            </table>
            <p class="source-badge">Проверено по OpenAI, Microsoft, xAI и Fluidstack на март 2026.<sup><a href="#fn4">4</a></sup></p>

            <h2 id="energy">Энергетика AI</h2>
            <p>Goldman Sachs ожидает, что к 2030 дата-центры будут потреблять до 8% электроэнергии США против 3% в 2022. По той же оценке, один запрос к ChatGPT требует примерно в 10 раз больше электроэнергии, чем обычный Google-поиск.<sup><a href="#fn-energy">5</a></sup></p>
            <div class="interpretation">
              При текущих темпах роста AI-нагрузки энергетические ограничения могут стать более серьёзным барьером для масштабирования, чем вычислительные.
            </div>

            <h2 id="smr">Малые модульные реакторы: AI-ядерный альянс</h2>
            <p>Microsoft подписал 20-летний PPA с Constellation для перезапуска Three Mile Island Unit 1 на 835 МВт с вводом с 2028 года. Google закрепила соглашение с Kairos Power на до 500 МВт к 2035 году, а Amazon инвестировала в проекты X-energy и Energy Northwest с потенциалом более 5 ГВт новой мощности.<sup><a href="#fn-smr">6</a></sup></p>
        """
    ).rstrip()
    marker = '\n    <div class="verdict">'
    if 'id="datacenters"' not in text:
        text = replace_once_or_skip(text, marker, insert + marker, "16-infrastructure.html")

    if 'id="fn4"' not in text:
        text = replace_once_or_skip(
            text,
            """        <li id="fn3"><a href="https://openai.com/index/announcing-the-stargate-project/">OpenAI — Stargate</a>. <a href="https://www.cnbc.com/2025/09/23/openai-first-data-center-in-500-billion-stargate-project-up-in-texas.html">CNBC — Stargate Texas</a>.</li>
      </ol>""",
            """        <li id="fn3"><a href="https://openai.com/index/announcing-the-stargate-project/">OpenAI — Stargate</a>. <a href="https://www.cnbc.com/2025/09/23/openai-first-data-center-in-500-billion-stargate-project-up-in-texas.html">CNBC — Stargate Texas</a>.</li>
        <li id="fn4"><a href="https://openai.com/index/five-new-stargate-sites">OpenAI — Five New Stargate Sites</a>. <a href="https://blogs.microsoft.com/on-the-issues/2025/09/18/made-in-wisconsin-the-worlds-most-powerful-ai-datacenter/">Microsoft — Fairwater in Wisconsin</a>. <a href="https://x.ai/colossus">xAI — Colossus</a>. <a href="https://www.businesswire.com/news/home/20250303970989/en/Fluidstack-Delivering-Europes-Largest-AI-Supercomputer-to-Mistral-AI-in-2025">Fluidstack — Mistral Compute</a>.</li>
        <li id="fn-energy"><a href="https://www.goldmansachs.com/insights/articles/AI-poised-to-drive-160-increase-in-power-demand">Goldman Sachs — AI and Data Center Power Demand</a>.</li>
        <li id="fn-smr"><a href="https://www.constellationenergy.com/newsroom/2024/Constellation-to-Launch-Crane-Clean-Energy-Center-Restoring-Jobs-and-Carbon-Free-Power-to-The-Grid.html">Constellation — Crane Clean Energy Center</a>. <a href="https://blog.google/company-news/outreach-initiatives/sustainability/google-kairos-power-nuclear-energy-agreement/">Google — Kairos Power Agreement</a>. <a href="https://www.aboutamazon.com/news/sustainability/amazon-nuclear-small-modular-reactor-net-carbon-zero">Amazon — Nuclear Energy Projects</a>.</li>
      </ol>""",
            "16-infrastructure.html",
        )

    write_text(path, text)


def update_legal() -> None:
    path = ROOT / "17-legal.html"
    text = read_text(path)
    if 'id="cases"' in text and 'id="eu-ai-act"' in text:
        return
    for old, new in [
        (
            "В SDNY идёт discovery; после отказа в dismissal продолжается спор о логах ChatGPT и экспертах",
            "В SDNY идёт раскрытие доказательств; после отказа в отклонении иска продолжается спор о логах ChatGPT и экспертах",
        ),
        (
            "4 ноября 2025 High Court отклонил основную copyright-теорию, но оставил ограниченные trademark-вопросы",
            "4 ноября 2025 High Court отклонил основную претензию по авторскому праву, но оставил ограниченные вопросы по товарным знакам",
        ),
        (
            "Входит в consolidated MDL; output-based copyright claim пережил motion to dismiss, discovery продолжается",
            "Входит в consolidated MDL; ключевая претензия к воспроизведению фрагментов пережила motion to dismiss, раскрытие доказательств продолжается",
        ),
        (
            "Входит в consolidated MDL; ключевая претензия к воспроизведению фрагментов пережила motion to dismiss, раскрытие доказательств продолжается",
            "Входит в объединённое производство (MDL); ключевая претензия к воспроизведению фрагментов пережила стадию ходатайства об отклонении иска, раскрытие доказательств продолжается",
        ),
        (
            "В N.D. California дело активно: preliminary injunction отклонён, часть претензий скорректирована, спор продолжается",
            "В N.D. California дело активно: ходатайство о предварительном запрете отклонено, часть претензий уточнена, спор продолжается",
        ),
        (
            "Запрет на prohibited practices и обязанность по AI literacy",
            "Запрет на запрещённые практики и обязанность по базовой AI-грамотности",
        ),
        (
            "Governance rules и обязанности для GPAI-моделей начинают применяться; для уже выпущенных GPAI действует переход до 2 августа 2027",
            "Начинают применяться требования к органам надзора и GPAI-моделям; для уже выпущенных GPAI действует переход до 2 августа 2027",
        ),
        (
            "EU AI Act вводит категории риска: high-risk AI системы (медицина, правоприменение, критическая инфраструктура) подлежат обязательному аудиту и сертификации к августу 2026.",
            "EU AI Act вводит категории риска: AI-системы высокого риска (медицина, правоприменение, критическая инфраструктура) подлежат обязательному аудиту и сертификации к августу 2026.",
        ),
        (
            "AI-компании инвестируют миллиарды в R&D, но копейки в legal compliance.",
            "AI-компании инвестируют миллиарды в R&D, но копейки в юридическую готовность.",
        ),
        (
            "Начинает применяться большая часть оставшегося AI Act; для части high-risk систем, встроенных в регулируемые продукты, действует отдельный переход до 2 августа 2027",
            "Начинает применяться большая часть оставшегося AI Act; для части систем высокого риска, встроенных в регулируемые продукты, действует отдельный переход до 2 августа 2027",
        ),
        (
            "EU AI Act к августу 2026 обяжет аудировать high-risk системы — штрафы до 7% глобального оборота.",
            "EU AI Act к августу 2026 обяжет аудировать системы высокого риска — штрафы до 7% глобального оборота.",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    insert = dedent(
        """

            <h2 id="cases">Ключевые судебные дела</h2>
            <table>
              <thead>
                <tr><th>Дело</th><th>Истец</th><th>Ответчик</th><th>Суть</th><th>Статус (10 марта 2026)</th></tr>
              </thead>
              <tbody>
                <tr><td>NYT v. OpenAI</td><td>New York Times</td><td>OpenAI, Microsoft</td><td>Авторское право и обучающие данные</td><td>В SDNY идёт раскрытие доказательств; после отказа в отклонении иска продолжается спор о логах ChatGPT и экспертах</td></tr>
                <tr><td>Getty v. Stability AI</td><td>Getty Images</td><td>Stability AI</td><td>Авторские права и товарные знаки</td><td>4 ноября 2025 High Court отклонил основную претензию по авторскому праву, но оставил ограниченные вопросы по товарным знакам</td></tr>
                <tr><td>Authors Guild v. OpenAI</td><td>Authors Guild и авторы</td><td>OpenAI, Microsoft</td><td>Книги в обучающих датасетах</td><td>Входит в consolidated MDL; ключевая претензия к воспроизведению фрагментов пережила motion to dismiss, раскрытие доказательств продолжается</td></tr>
                <tr><td>Concord Music v. Anthropic</td><td>Музыкальные правообладатели</td><td>Anthropic</td><td>Тексты песен в Claude</td><td>В N.D. California дело активно: ходатайство о предварительном запрете отклонено, часть претензий уточнена, спор продолжается</td></tr>
              </tbody>
            </table>
            <p class="source-badge">Статусы проверены по судебным документам и официальным решениям на 10 марта 2026.</p>

            <h2 id="eu-ai-act">EU AI Act: что уже применяется</h2>
            <table class="compact">
              <thead><tr><th>Дата</th><th>Что вступает в силу</th></tr></thead>
              <tbody>
                <tr><td>2 февраля 2025</td><td>Запрет на prohibited practices и обязанность по AI literacy</td></tr>
                <tr><td>2 августа 2025</td><td>Начинают применяться требования к органам надзора и GPAI-моделям; для уже выпущенных GPAI действует переход до 2 августа 2027</td></tr>
                <tr><td>2 августа 2026</td><td>Начинает применяться большая часть оставшегося AI Act; для части high-risk систем, встроенных в регулируемые продукты, действует отдельный переход до 2 августа 2027</td></tr>
              </tbody>
            </table>
            <p class="source-badge">Таймлайн сверён с European Commission и AI Office.</p>
        """
    ).rstrip()
    marker = '\n    <div class="verdict">'
    if 'id="cases"' not in text:
        text = replace_once_or_skip(text, marker, insert + marker, "17-legal.html")
    write_text(path, text)


def final_polish() -> None:
    path = ROOT / "17-legal.html"
    text = read_text(path)
    for old, new in [
        (
            "Суды и регуляторы начинают определять экономику AI не меньше инженеров: правила обучения, дипфейки и liability становятся бизнес-факторами первого порядка.",
            "Суды и регуляторы начинают определять экономику AI не меньше инженеров: правила обучения, дипфейки и ответственность становятся бизнес-факторами первого порядка.",
        ),
        (
            "Центральный вопрос: является ли обучение моделей на защищённом контенте fair use?",
            "Центральный вопрос: подпадает ли обучение моделей на защищённом контенте под доктрину fair use (добросовестного использования)?",
        ),
        (
            "OpenAI настаивает на fair use.",
            "OpenAI ссылается на доктрину fair use.",
        ),
        (
            "Если OpenAI докажет fair use — это легализует тренировку на любых данных.",
            "Если OpenAI докажет применимость fair use — это легализует тренировку на любых данных.",
        ),
        (
            "если суд решит, что воспроизведение фрагментов статей — не fair use, индустрии придётся перестраивать обучающие пайплайны.",
            "если суд решит, что воспроизведение фрагментов статей не подпадает под fair use, индустрии придётся перестраивать обучающие пайплайны.",
        ),
        (
            "Одно решение EU о штрафах может стоить компании миллиарды.",
            "Одно решение ЕС о штрафах может стоить компании миллиарды.",
        ),
        (
            "AI-компании инвестируют миллиарды в R&D, но копейки в юридическую готовность.",
            "AI-компании инвестируют миллиарды в исследования и разработку, но копейки в юридическую готовность.",
        ),
        (
            "4 ноября 2025 High Court отклонил основную претензию по авторскому праву, но оставил ограниченные вопросы по товарным знакам",
            "4 ноября 2025 Высокий суд Англии и Уэльса отклонил основную претензию по авторскому праву, но оставил ограниченные вопросы по товарным знакам",
        ),
        (
            "Начинают применяться требования к органам надзора и GPAI-моделям; для уже выпущенных GPAI действует переход до 2 августа 2027",
            "Начинают применяться требования к органам надзора и моделям общего назначения (GPAI); для уже выпущенных таких моделей действует переход до 2 августа 2027",
        ),
        (
            "Таймлайн сверён с European Commission и AI Office.",
            "Таймлайн сверён с материалами Еврокомиссии и AI Office.",
        ),
        (
            "AI-компании инвестируют миллиарды в R&D и копейки в legal compliance.",
            "AI-компании инвестируют миллиарды в исследования и разработку и копейки в юридическую готовность.",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)

    path = ROOT / "13-predictions.html"
    text = read_text(path)
    for old, new in [
        (
            "EU AI Act усложняет compliance для high-risk систем к августу 2026.",
            "EU AI Act усложняет требования к соответствию для систем высокого риска к августу 2026.",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)


def raise_editorial_bar() -> None:
    path = ROOT / "index.html"
    text = read_text(path)
    for old, new in [
        (
            "<li>41% кода пишет AI, vibe coding стал массовым</li>",
            "<li>41% кода пишет AI, «вайбкодинг» стал массовым</li>",
        ),
        (
            "<li><strong>Founders и CTO</strong> — build vs buy и выбор стека</li>",
            "<li><strong>Founders и CTO</strong> — собирать самим или покупать и как выбирать стек</li>",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)

    path = ROOT / "17-legal.html"
    text = read_text(path)
    for old, new in [
        (
            "<p>Самый важный AI-иск десятилетия. В декабре 2023 The New York Times подала иск о нарушении авторских прав. Центральный вопрос: подпадает ли обучение моделей на защищённом контенте под доктрину fair use (добросовестного использования)?</p>",
            "<p>Один из ключевых AI-исков десятилетия. В декабре 2023 The New York Times подала иск о нарушении авторских прав. Центральный вопрос: подпадает ли обучение моделей на защищённом контенте под доктрину fair use (добросовестного использования)?</p>",
        ),
        (
            "<p>20 миллионов логов ChatGPT — беспрецедентное судебное требование. Если NYT докажет, что ChatGPT воспроизводит её статьи, это изменит экономику обучения моделей. Если OpenAI докажет применимость fair use — это легализует тренировку на любых данных. Ставки — сотни миллиардов долларов.</p>",
            "<p>20 миллионов логов ChatGPT — беспрецедентное судебное требование. Если NYT докажет, что ChatGPT воспроизводит её статьи, это изменит экономику обучения моделей. Если OpenAI докажет применимость fair use, это заметно усилит позицию разработчиков моделей, но не снимет других претензий к составу датасетов и воспроизведению фрагментов. Ставки — сотни миллиардов долларов.</p>",
        ),
        (
            "Решение по Getty — поворотный момент. Если модель «не содержит копий», то обучение на любых данных потенциально легально. Это хорошо для AI-компаний и плохо для правообладателей. Но дело NYT может перевернуть эту логику: если суд решит, что воспроизведение фрагментов статей не подпадает под fair use, индустрии придётся перестраивать обучающие пайплайны. Ставки — сотни миллиардов долларов.",
            "Решение по Getty — важный сигнал для отрасли. Если суд исходит из того, что модель сама по себе не содержит копий произведений, это усиливает позицию разработчиков в спорах об обучении, но не даёт универсального иммунитета для любых датасетов и сценариев использования. Дело NYT всё равно может заметно изменить практику: если суд решит, что воспроизведение фрагментов статей не подпадает под fair use, индустрии придётся перестраивать обучающие пайплайны. Ставки — сотни миллиардов долларов.",
        ),
        (
            "<p>EU AI Act вводит категории риска: AI-системы высокого риска (медицина, правоприменение, критическая инфраструктура) подлежат обязательному аудиту и сертификации к августу 2026. Нарушения — до 7% глобального оборота.<sup><a href=\"#fn4\">[4]</a></sup></p>",
            "<p>EU AI Act вводит категории риска: AI-системы высокого риска (медицина, правоприменение, критическая инфраструктура) подпадают под поэтапное применение обязательных требований, часть которых начинает действовать с августа 2026. Потенциальные штрафы — до 7% глобального оборота.<sup><a href=\"#fn4\">[4]</a></sup></p>",
        ),
        (
            "<h2 id=\"eu-ai-act\">EU AI Act: что уже применяется</h2>",
            "<h2 id=\"eu-ai-act\">EU AI Act: что уже действует и что вступит в силу</h2>",
        ),
        (
            "<thead><tr><th>Дата</th><th>Что вступает в силу</th></tr></thead>",
            "<thead><tr><th>Дата</th><th>Что уже действует или вступит в силу</th></tr></thead>",
        ),
        (
            "<p class=\"source-badge\">Таймлайн сверён с материалами Еврокомиссии и AI Office.</p>",
            "<p class=\"source-badge\">На 10 марта 2026 уже действует этап 2 февраля 2025; даты августа 2025 и августа 2026 — следующие этапы применения. Таймлайн сверён с материалами Еврокомиссии и AI Office.</p>",
        ),
        (
            "<p>Право — <strong>спящий гигант AI-индустрии</strong>. Одно решение суда по делу NYT vs OpenAI может изменить экономику обучения моделей на сотни миллиардов. EU AI Act к августу 2026 обяжет аудировать системы высокого риска — штрафы до 7% глобального оборота. 100+ законов штатов создают 'лоскутное одеяло' регулирования. AI-компании инвестируют миллиарды в исследования и разработку и копейки в юридическую готовность. <strong>Это ставка, которая может стоить дороже, чем всё обучение всех моделей вместе взятых.</strong></p>",
            "<p>Право — один из недооценённых ограничителей AI-рынка. Решения по делам вроде NYT vs OpenAI способны заметно изменить экономику обучения моделей, а EU AI Act — стоимость вывода продуктов на европейский рынок. 100+ законов штатов создают «лоскутное одеяло» регулирования. AI-компании инвестируют миллиарды в исследования и разработку и гораздо меньше — в юридическую готовность; поэтому регуляторные и судебные риски уже становятся не фоном, а частью бизнес-модели.</p>",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)

    path = ROOT / "16-infrastructure.html"
    text = read_text(path)
    for old, new in [
        (
            "<p>Big Tech подписали 10+ ГВт новых ядерных мощностей в США за последний год. Constellation Energy получила кредит $1B от DOE на перезапуск Three Mile Island.<sup><a href=\"#fn2\">[2]</a></sup></p>",
            "<p>Big Tech за последний год заключили серию крупных ядерных соглашений — от продления работы действующих станций до портфеля новых проектов. Constellation Energy получила кредит $1B от DOE на перезапуск Three Mile Island.<sup><a href=\"#fn2\">[2]</a></sup></p>\n    <p class=\"source-badge\">Строки по Meta и Clinton основаны на официальных объявлениях Meta и Constellation от 3 июня 2025 и 9 января 2026.<sup><a href=\"#fn-meta\">7</a></sup></p>",
        ),
        (
            "<p>Дата-центры потребляют 460 TWh/год — больше, чем многие страны. К 2030 прогноз: 1000+ TWh, из них 945 TWh — AI. Big Tech подписали 10+ ГВт ядерных мощностей за год. Microsoft перезапускает Three Mile Island — символ ядерной катастрофы 1979 года — для питания серверов. AI буквально возрождает ядерную энергетику.</p>",
            "<p>Дата-центры потребляют 460 TWh/год — больше, чем многие страны. К 2030 прогноз: 1000+ TWh, из них 945 TWh — AI. Big Tech вернули ядерную энергетику в повестку AI-инфраструктуры: речь уже не о единичных пилотах, а о длинных контрактах и расширении действующих мощностей. Microsoft перезапускает Three Mile Island для питания серверов. AI действительно меняет энергетическую повестку сектора.</p>",
        ),
        (
            "<div class=\"opinion\">\n      AI-индустрия совершила невероятный разворот: от «move fast and break things» к переговорам с ядерными регуляторами о перезапуске АЭС. Three Mile Island — символ ядерной катастрофы 1979 года — теперь будет питать серверы Microsoft. Это не ирония, а свидетельство того, что AI действительно меняет энергетическую картину мира. Но возникает вопрос: если для обучения одной модели нужна АЭС, устойчива ли эта модель развития?\n    </div>",
            "<div class=\"interpretation\">\n      Переход Big Tech от разговоров о software scale к переговорам об энергетике показывает, что инфраструктурный потолок больше не абстракция. Сделки вокруг Three Mile Island, Clinton и новых ядерных проектов важны не как символы, а как индикатор: рост AI всё сильнее зависит от длинных капиталоёмких решений в энергетике. Это не означает, что каждой новой модели нужна отдельная АЭС, но означает, что энергосистема становится частью продуктовой стратегии.\n    </div>",
        ),
        (
            "<p>Инфраструктура AI — <strong>физический предел цифровой революции</strong>. 208 млрд транзисторов в Blackwell, $443B capex гиперскейлеров, $500B проект Stargate — числа, которые невозможно осмыслить. Но за ними стоит простой вопрос: хватит ли электричества? 460 TWh сегодня, 1300 TWh через 10 лет. Если AI-индустрия не решит энергетическую проблему (через ядерную энергию, термоядерный синтез или радикальное повышение эффективности), то <strong>физика остановит прогресс раньше, чем алгоритмы</strong>.</p>",
            "<p>Инфраструктура AI — <strong>физический предел цифровой революции</strong>. 208 млрд транзисторов в Blackwell, $443B capex гиперскейлеров, $500B проект Stargate — за этими числами стоит простой вопрос: хватит ли электричества? 460 TWh сегодня, 1300 TWh через 10 лет. Если AI-индустрия не снимет энергетические ограничения через новые мощности и рост эффективности, физическая инфраструктура станет ограничителем прогресса не меньше, чем сами алгоритмы.</p>",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    if 'id="fn-meta"' not in text:
        text = replace_once_or_skip(
            text,
            "        <li id=\"fn-smr\"><a href=\"https://www.constellationenergy.com/newsroom/2024/Constellation-to-Launch-Crane-Clean-Energy-Center-Restoring-Jobs-and-Carbon-Free-Power-to-The-Grid.html\">Constellation — Crane Clean Energy Center</a>. <a href=\"https://blog.google/company-news/outreach-initiatives/sustainability/google-kairos-power-nuclear-energy-agreement/\">Google — Kairos Power Agreement</a>. <a href=\"https://www.aboutamazon.com/news/sustainability/amazon-nuclear-small-modular-reactor-net-carbon-zero\">Amazon — Nuclear Energy Projects</a>.</li>\n      </ol>",
            "        <li id=\"fn-smr\"><a href=\"https://www.constellationenergy.com/newsroom/2024/Constellation-to-Launch-Crane-Clean-Energy-Center-Restoring-Jobs-and-Carbon-Free-Power-to-The-Grid.html\">Constellation — Crane Clean Energy Center</a>. <a href=\"https://blog.google/company-news/outreach-initiatives/sustainability/google-kairos-power-nuclear-energy-agreement/\">Google — Kairos Power Agreement</a>. <a href=\"https://www.aboutamazon.com/news/sustainability/amazon-nuclear-small-modular-reactor-net-carbon-zero\">Amazon — Nuclear Energy Projects</a>.</li>\n        <li id=\"fn-meta\"><a href=\"https://about.fb.com/news/2025/06/meta-constellation-partner-clean-energy-project/\">Meta — Constellation partnership</a>. <a href=\"https://www.constellationenergy.com/news/2025/constellation-meta-sign-20-year-deal-for-clean-reliable-nuclear-energy-in-illinois.html\">Constellation — Clinton deal with Meta</a>. <a href=\"https://about.fb.com/news/2026/01/meta-nuclear-energy-projects-power-american-ai-leadership/\">Meta — Nuclear energy projects</a>.</li>\n      </ol>",
            "16-infrastructure.html",
        )
    write_text(path, text)

    path = ROOT / "13-predictions.html"
    text = read_text(path)
    for old, new in [
        (
            "<p>Sam Altman: «We are now confident we know how to build AGI as we have traditionally understood it.» Вехи: автоматизированный AI research intern к сентябрю 2026, полноценный исследователь к марту 2028.<sup><a href=\"#fn1\">[1]</a></sup></p>",
            "<p>Sam Altman: «We are now confident we know how to build AGI as we have traditionally understood it.» В отраслевых пересказах его более поздних выступлений фигурировали ориентиры вроде «AI research intern» к сентябрю 2026 и более сильной исследовательской системы к марту 2028; это стоит читать как неофициальные ориентиры, а не как публичный roadmap компании.<sup><a href=\"#fn1\">[1]</a></sup></p>",
        ),
        (
            "<p>Dario Amodei (Давос 2026): software-инженеры заменены за 6–12 месяцев, 50% white-collar jobs disrupted за 1–5 лет. AI-системы с интеллектом нобелевских лауреатов — «country of geniuses in a datacenter».<sup><a href=\"#fn2\">[2]</a></sup></p>",
            "<p>Dario Amodei (Давос 2026) говорил о резком росте возможностей моделей в software engineering и о серьёзном влиянии AI на white-collar jobs в горизонте ближайших лет. Это важный сигнал о темпе изменений, но не точный календарный прогноз для всего рынка труда.<sup><a href=\"#fn2\">[2]</a></sup></p>",
        ),
        (
            "<h2 id=\"author\">Прогноз автора</h2>\n\n    <div class=\"opinion\">",
            "<h2 id=\"author\">Прогноз автора</h2>\n\n    <p class=\"source-badge\">Сценарная интерпретация автора, а не консенсусный прогноз.</p>\n\n    <div class=\"opinion\">",
        ),
        (
            "<li id=\"fn1\"><a href=\"https://time.com/7205596/sam-altman-superintelligence-agi/\">TIME — Altman on AGI</a>. <a href=\"https://www.windowscentral.com/software-apps/sam-altman-claims-agi-will-whoosh-by-in-5-years-with-surprisingly-little-societal-change-while-anthropic-ceo-predicts-a-2026-or-2027-breakthrough-theres-no-ceiling-below-the-level-of-humans-theres-a-lot-of-room-at-the-top-for-ais\">Windows Central — AGI Predictions</a>.</li>",
            "<li id=\"fn1\"><a href=\"https://time.com/7205596/sam-altman-superintelligence-agi/\">TIME — Altman on AGI</a>. <a href=\"https://www.theinformation.com/articles/realistic-openais-2028-timeline-automating-ai-research\">The Information — OpenAI’s 2028 Timeline for Automating AI Research</a>.</li>",
        ),
        (
            "<li id=\"fn2\"><a href=\"https://tamiltech.in/article/anthropic-ceo-dario-amodei-davos-2026-interview-agi-predictions\">TamilTech — Amodei Davos 2026</a>.</li>",
            "<li id=\"fn2\"><a href=\"https://www.weforum.org/stories/2026/01/young-people-ai-davos/\">World Economic Forum — Young people and AI: 3 things Davos leaders want everyone to know</a>.</li>",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)


def raise_editorial_bar_v2() -> None:
    path = ROOT / "index.html"
    text = read_text(path)
    for old, new in [
        (
            """<p>AI в марте 2026 — это технология, которая работает лучше, чем думают скептики, но хуже, чем обещают продавцы. $200B+ рынок, который не приносит прибыли почти никому, кроме NVIDIA. 800M пользователей, 95% которых получают развлечение, а не инструмент. И при этом — технология, без которой через 5 лет будет невозможно работать. Не AGI, не революция — но тектонический сдвиг, который уже произошёл.</p>""",
            """<p>AI в марте 2026 — это технология, которая уже даёт рабочие преимущества, но распределяет выгоду неравномерно. Рынок свыше $200B растёт быстрее, чем формируется устойчивая прибыль за пределами NVIDIA. 800M пользователей показывают масштаб спроса, но глубина пользы сильно различается по сценариям. Это ещё не AGI и не универсальная перестройка каждого процесса, но уже долгосрочный сдвиг в том, как компании строят продукты и как люди работают.</p>""",
        ),
    ]:
        text = replace_once_or_skip(text, old, new, "index.html")
    write_text(path, text)

    path = ROOT / "16-infrastructure.html"
    text = read_text(path)
    for old, new in [
        (
            """<p>Инфраструктура AI — <strong>физический предел цифровой революции</strong>. 208 млрд транзисторов в Blackwell, $443B capex гиперскейлеров, $500B проект Stargate — за этими числами стоит простой вопрос: хватит ли электричества? 460 TWh сегодня, 1300 TWh через 10 лет. Если AI-индустрия не снимет энергетические ограничения через новые мощности и рост эффективности, физическая инфраструктура станет ограничителем прогресса не меньше, чем сами алгоритмы.</p>""",
            """<p>Инфраструктура AI становится одним из главных ограничений роста. 208 млрд транзисторов в Blackwell, $443B capex гиперскейлеров и $500B проект Stargate упираются в простой вопрос: хватит ли электричества? 460 TWh сегодня, 1300 TWh через 10 лет. Если AI-индустрия не снимет энергетические ограничения через новые мощности и рост эффективности, физическая инфраструктура станет ограничителем прогресса не меньше, чем сами алгоритмы.</p>""",
        ),
    ]:
        text = replace_once_or_skip(text, old, new, "16-infrastructure.html")
    write_text(path, text)

    path = ROOT / "13-predictions.html"
    text = read_text(path)
    for old, new in [
        (
            """<p>Разброс прогнозов AGI — от 2026 (Musk) до 2033 (Metaculus). Медианный консенсус: 50% к 2033. Но определение AGI настолько размыто, что Altman может объявить 'мы достигли AGI' в любой момент — и формально будет прав по своему определению.</p>""",
            """<p>Разброс прогнозов AGI — от 2026 (Musk) до 2033 (Metaculus). Медианный консенсус: около 50% к 2033. Но само определение AGI остаётся настолько размытым, что спор о моменте его достижения, вероятно, будет идти дольше, чем спор о возможностях конкретных систем.</p>""",
        ),
        (
            """<p>100+ законов штатов об AI в 2025 — «лоскутное одеяло». EU AI Act усложняет требования к соответствию для систем высокого риска к августу 2026. Вопрос авторских прав (NYT vs OpenAI) может изменить экономику обучения моделей.</p>""",
            """<p>100+ законов штатов об AI в 2025 формируют «лоскутное одеяло» требований. EU AI Act поэтапно ужесточает требования к соответствию для систем высокого риска, а часть обязательств начинает действовать с августа 2026. Вопрос авторских прав в делах вроде NYT vs OpenAI способен заметно изменить экономику обучения моделей.</p>""",
        ),
        (
            """<p class="source-badge">Сценарная интерпретация автора, а не консенсусный прогноз.</p>""",
            """<p class="source-badge">Сценарная интерпретация автора, а не консенсусный прогноз. Числа ниже — ориентиры, а не точный таймлайн.</p>""",
        ),
        (
            """<strong>2026:</strong> «Trough of Disillusionment» — массовое разочарование enterprise-клиентов, которые потратили миллионы на AI-пилоты без ROI. 30–40% AI-стартапов закроются или будут поглощены. Цены на подписки начнут снижаться.<br><br>""",
            """<strong>2026:</strong> В базовом сценарии усилится «Trough of Disillusionment»: enterprise-клиенты, потратившие миллионы на AI-пилоты без ROI, станут жёстче отбирать кейсы для масштабирования. Часть AI-стартапов закроется или будет поглощена, а цены на подписки начнут снижаться.<br><br>""",
        ),
        (
            """<strong>2027:</strong> Ценовая война — один из лидеров (вероятно, Google) радикально снизит цену или перейдёт на freemium. $20/мес станет $10 или $5. Open-source модели на устройствах покроют 80% бытовых сценариев.<br><br>""",
            """<strong>2027:</strong> Возможна ценовая война: один из лидеров рынка может радикально снизить цену или перейти на freemium. Якорь в $20/мес окажется под давлением, а open-source модели на устройствах начнут закрывать большую часть бытовых сценариев.<br><br>""",
        ),
        (
            """<strong>2028:</strong> Коррекция инвестиций — оценки AI-компаний упадут на 40–60%. 3–5 крупных игроков выживут. Оставшиеся перестроятся на usage-based pricing.<br><br>""",
            """<strong>2028:</strong> В сценарии коррекции оценки AI-компаний могут заметно просесть, а рынок начнёт жёстче вознаграждать реальную выручку и удержание клиентов. Часть игроков выживет только после перехода на usage-based pricing.<br><br>""",
        ),
        (
            """<strong>2029–2030:</strong> AI станет как электричество — невидимым и вездесущим. Не «AI-продукт», а встроенная функция в каждом приложении. Рынок стабилизируется на ~$500B/год. AGI — маловероятно в этот срок (25–30%), но narrow AI будет решать 90% задач, для которых обещали AGI.<br><br>""",
            """<strong>2029–2030:</strong> В базовом сценарии AI станет инфраструктурной функцией, встроенной в большинство приложений, а не отдельным «AI-продуктом». Рынок может стабилизироваться около ~$500B/год. AGI в этот срок остаётся маловероятным, но более узкие системы будут закрывать большую часть задач, ради которых сегодня обещают AGI.<br><br>""",
        ),
        (
            """<p>Все прогнозы, включая этот, будут частично неправы. Но одно предсказание имеет высокую вероятность: <strong>2026 станет годом отрезвления</strong>. Не краха — а перехода от фазы 'AI может всё' к фазе 'AI может конкретно вот это, и это стоит конкретно столько'. Это болезненный, но необходимый процесс. После него останутся компании с реальными продуктами и реальными клиентами.</p>""",
            """<p>Все прогнозы, включая этот, будут частично неправы. Но один тезис выглядит особенно устойчивым: <strong>2026, скорее всего, станет годом отрезвления</strong>. Не краха, а перехода от фазы «AI может всё» к фазе «AI даёт конкретный результат в конкретном кейсе за конкретную цену». После этого этапа сильнее будут выглядеть компании с реальными продуктами, измеримым ROI и понятной экономикой.</p>""",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)


def raise_editorial_bar_v3() -> None:
    path = ROOT / "index.html"
    text = read_text(path)
    for old, new in [
        (
            """<p style="font-size: 0.88rem; line-height: 1.42;">Inference подешевел в 280x. DeepSeek — за $5.6M. 41% кода пишет AI. Gartner говорит: Trough of Disillusionment начался.</p>""",
            """<p style="font-size: 0.88rem; line-height: 1.42;">Инференс подешевел в 280 раз. DeepSeek — за $5.6M. 41% кода пишет AI. Gartner: началась фаза разочарования.</p>""",
        ),
        (
            """<div class="section-stat">Inference подешевел в 280x</div>""",
            """<div class="section-stat">Инференс подешевел в 280 раз</div>""",
        ),
        (
            """<li><strong>Founders и CTO</strong> — собирать самим или покупать и как выбирать стек</li>""",
            """<li><strong>Основатели и CTO</strong> — собирать самим или покупать и как выбирать стек</li>""",
        ),
        (
            """<p>Коммодитизация, reasoning-модели, open-source revolution, мультимодальность. 8 трендов, определяющих рынок.</p>""",
            """<p>Коммодитизация, reasoning-модели, открытые модели, мультимодальность. 8 трендов, определяющих рынок.</p>""",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)

    path = ROOT / "16-infrastructure.html"
    text = read_text(path)
    for old, new in [
        (
            """Переход Big Tech от разговоров о software scale к переговорам об энергетике показывает, что инфраструктурный потолок больше не абстракция.""",
            """Переход Big Tech от разговоров о чисто программном масштабировании к переговорам об энергетике показывает, что инфраструктурный потолок больше не абстракция.""",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)

    path = ROOT / "17-legal.html"
    text = read_text(path)
    for old, new in [
        (
            """<div class="opinion">
      Правовая неопределённость — главный риск для AI-индустрии в 2026–2028. Не технологический потолок, не конкуренция — а судебные решения. Одно решение по делу NYT может изменить экономику обучения моделей. Одно решение ЕС о штрафах может стоить компании миллиарды. AI-компании инвестируют миллиарды в исследования и разработку, но копейки в юридическую готовность. Это ошибка, которая будет стоить дорого.
    </div>""",
            """<div class="interpretation">
      Правовая неопределённость — один из главных рисков для AI-индустрии в 2026–2028. Не только технологический потолок и не только конкуренция, но и судебные решения будут влиять на экономику рынка. Дело NYT способно изменить подход к обучающим данным, а решения ЕС по штрафам — стоимость вывода продуктов на рынок. Юридическую готовность здесь разумнее рассматривать как часть операционной дисциплины, а не как второстепенную функцию.
    </div>""",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)

    path = ROOT / "13-predictions.html"
    text = read_text(path)
    for old, new in [
        (
            """<p>Sam Altman: «We are now confident we know how to build AGI as we have traditionally understood it.» В отраслевых пересказах его более поздних выступлений фигурировали ориентиры вроде «AI research intern» к сентябрю 2026 и более сильной исследовательской системы к марту 2028; это стоит читать как неофициальные ориентиры, а не как публичный roadmap компании.<sup><a href="#fn1">[1]</a></sup></p>""",
            """<p>Sam Altman: «We are now confident we know how to build AGI as we have traditionally understood it.» В отраслевых пересказах его более поздних выступлений фигурировали ориентиры вроде системы уровня исследовательского стажёра к сентябрю 2026 и более сильной исследовательской системы к марту 2028; это стоит читать как неофициальные ориентиры, а не как публичный план компании.<sup><a href="#fn1">[1]</a></sup></p>""",
        ),
        (
            """<p>Dario Amodei (Давос 2026) говорил о резком росте возможностей моделей в software engineering и о серьёзном влиянии AI на white-collar jobs в горизонте ближайших лет. Это важный сигнал о темпе изменений, но не точный календарный прогноз для всего рынка труда.<sup><a href="#fn2">[2]</a></sup></p>""",
            """<p>Dario Amodei (Давос 2026) говорил о резком росте возможностей моделей в разработке ПО и о серьёзном влиянии AI на офисные профессии в горизонте ближайших лет. Это важный сигнал о темпе изменений, но не точный календарный прогноз для всего рынка труда.<sup><a href="#fn2">[2]</a></sup></p>""",
        ),
        (
            """<li>AI в «Trough of Disillusionment» в 2026 — от хайпа к реальности</li>""",
            """<li>AI в фазе разочарования («Trough of Disillusionment») в 2026 — от хайпа к реальности</li>""",
        ),
        (
            """<li>Деньги «ходят по кругу» — hyperscalers покупают друг у друга</li>""",
            """<li>Деньги «ходят по кругу» — гиперскейлеры покупают друг у друга</li>""",
        ),
        (
            """<strong>2026:</strong> В базовом сценарии усилится «Trough of Disillusionment»: enterprise-клиенты, потратившие миллионы на AI-пилоты без ROI, станут жёстче отбирать кейсы для масштабирования. Часть AI-стартапов закроется или будет поглощена, а цены на подписки начнут снижаться.<br><br>""",
            """<strong>2026:</strong> В базовом сценарии усилится фаза разочарования: корпоративные заказчики, потратившие миллионы на AI-пилоты без ROI, станут жёстче отбирать кейсы для масштабирования. Часть AI-стартапов закроется или будет поглощена, а цены на подписки начнут снижаться.<br><br>""",
        ),
        (
            """<strong>2027:</strong> Возможна ценовая война: один из лидеров рынка может радикально снизить цену или перейти на freemium. Якорь в $20/мес окажется под давлением, а open-source модели на устройствах начнут закрывать большую часть бытовых сценариев.<br><br>""",
            """<strong>2027:</strong> Возможна ценовая война: один из лидеров рынка может радикально снизить цену или перейти на условно-бесплатную модель. Якорь в $20/мес окажется под давлением, а открытые модели на устройствах начнут закрывать большую часть бытовых сценариев.<br><br>""",
        ),
        (
            """<strong>2028:</strong> В сценарии коррекции оценки AI-компаний могут заметно просесть, а рынок начнёт жёстче вознаграждать реальную выручку и удержание клиентов. Часть игроков выживет только после перехода на usage-based pricing.<br><br>""",
            """<strong>2028:</strong> В сценарии коррекции оценки AI-компаний могут заметно просесть, а рынок начнёт жёстче вознаграждать реальную выручку и удержание клиентов. Часть игроков выживет только после перехода на оплату по использованию.<br><br>""",
        ),
    ]:
        text = replace_once_if_present(text, old, new)
    write_text(path, text)


def main() -> None:
    append_css()
    update_index()
    update_pricing_tables_sort()
    insert_chapter_theses()
    update_appendix()
    update_cross_references()
    update_interpretations()
    update_page_navs()
    update_infrastructure()
    update_legal()
    final_polish()
    raise_editorial_bar()
    raise_editorial_bar_v2()
    raise_editorial_bar_v3()


if __name__ == "__main__":
    main()
