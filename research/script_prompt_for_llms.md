# Промпт: сценарии видео-питча AB Test Research Designer (30 / 60 / 90 сек)

> Скопируй этот файл целиком в ChatGPT / Claude / Gemini / Kimi / Perplexity. Промпт самодостаточный — все факты, цифры и URL даны внутри.

---

Ты — режиссёр short-form тех-видео для портфолио. Напиши **три варианта сценария** одного видео-питча: **30 / 60 / 90 секунд**. Это не три независимых ролика, а одна история, развёрнутая в трёх масштабах. Зритель — нанимающий менеджер в data engineering / analytics / experimentation, который смотрит на 1.5x скорости из вкладки браузера.

## 1. Что за продукт

**AB Test Research Designer** — локально-first инструмент планирования A/B и multi-variant экспериментов. Open-source, MIT.

Стек: FastAPI + React 19 + TypeScript + Vite + SQLite. 350+ backend тестов, 200+ frontend, Playwright E2E, coverage gate 89%, Lighthouse CI, axe a11y.

Что делает:
- Детерминированный расчёт sample size и duration по baseline / MDE / power.
- **Group-sequential design** с always-valid p-values (mSPRT-семейство) — peeking разрешён, ложные сигналы — нет.
- **SRM (Sample Ratio Mismatch) check** — диагностика бага split'а до анализа результатов.
- **CUPED** для variance reduction.
- Bayesian alternative для тех, кому нужен.
- Bonferroni / FDR коррекция при multi-arm.
- Guardrail metrics, heuristic warnings, feasibility checks.
- Сохранение проектов в локальном SQLite, side-by-side сравнение, экспорт decision-ready отчёта.
- Multilang UI: EN, RU, DE, ES, FR, ZH, AR (с RTL).

Live demo: https://liovina-ab-test-research-designer.hf.space (Hugging Face Spaces, бесплатный CPU tier).

## 2. Аудитория и цель видео

Зритель — senior data engineer / analytics lead / experimentation PM, ищущий человека в команду. Видео должно за 30/60/90 сек дать ответ на три вопроса в его голове:
1. **Этот человек понимает статистику A/B-тестов на уровне индустрии?** (а не «сделал калькулятор по формуле из учебника»)
2. **Может ли довести продукт до production-quality?** (тесты, CI, accessibility, multilang, deploy)
3. **Стоит ли с ним поговорить 30 минут?**

Видео НЕ должно продавать продукт как стартап-офер. Это **демонстрация инженерного мышления через продукт**. Tone: calm, technical, restrained — без хайпа, без emoji в overlays, без «🚀 launch your experiments today».

## 3. Подтверждённые факты — что можно использовать как proof / hook

Все цифры верифицированы в досье `failures_dossier.md` с источниками. Используй любые, если они уместны:

**Громкие провалы продуктов / редизайнов (где A/B не сделали или сделали плохо):**
- **Tropicana 2009** — редизайн упаковки, −20% sales за 2 месяца, ~$30M потерь, откат за 47 дней.
- **Snapchat 2018** — редизайн, −5M DAU за 2 квартала, твит Kylie Jenner обвалил капу на $1.3B за день.
- **Digg v4 2010** — −50% трафика, продажа в 2012 за $500K (с пиковой оценки $200M).
- **Bud Light 2023** — −26% sales, −$1.4B выручки North America, потеря #1 в США.

**Баги в коммерческих A/B-инструментах (это самое сильное для бриджа к продукту):**
- **Optimizely до 2015** — peeking problem: при подглядывании после каждого посетителя false positive rate доходил до **57%** при заявленных 5%. Признано самой Optimizely в whitepaper их Stats Engine.
- **Peter Borden, 2014** — запустил **A/A-тест** (две идентичные страницы) в Optimizely, получил «**+18.1% improvement, 100% probability of being accurate**». Реальный коммерческий продукт за деньги. Источник: analythical.com/blog/optimizely-got-me-fired.
- **Microsoft Bing, 2012** (Kohavi KDD): эксперимент со специально ухудшенными результатами поиска дал +10% queries/user и +30% revenue/user — краткосрочный «выигрыш», убийственный для long-term query share.
- **Booking.com** — публично заявляет, что **~90% идей проваливаются** в A/B-тестах. Microsoft — ~66%, Bing — ~85%, Airbnb — ~92%.

**Канонические работы:**
- **Evan Miller, «How Not To Run An A/B Test», 18 апреля 2010** — peeking при заявленных α=5% даёт фактический FPR до 26.1%. Стандартная индустриальная ссылка.
- **Ronny Kohavi et al., KDD 2012, «Trustworthy Online Controlled Experiments: Five Puzzling Outcomes Explained»** — Bing-кейсы.
- **Fabijan et al., KDD 2019** — таксономия SRM на реальных багах Microsoft (Bing, Teams, Store).

## 4. Референсы (10 wow-видео — посмотри 2-3, прежде чем писать)

Эти видео работают. Каждое короткое (≤2 мин). Скопируй приёмы, которые подходят tech/data контексту.

| # | Продукт / автор | URL | Что украсть |
|---|---|---|---|
| 1 | Eames — *Powers of Ten* | https://www.youtube.com/watch?v=0fKBhvDjuy0 | scale-jump, zoom from macro metric to detail |
| 2 | Pentagram — *Just My Type* trailer | https://vimeo.com/28108942 | hero metric в огромном кегле, 60s typographic hierarchy без голоса |
| 3 | Atipo — *Fontface* | https://vimeo.com/19558725 | macro-to-micro hook: неузнаваемый close-up → reveal |
| 4 | Build — *PureReversal* | https://vimeo.com/21436365 | shape-morphing между состояниями (плохо/хорошо) |
| 5 | iA Presenter Teaser | https://www.youtube.com/watch?v=Ppuf6TCfSvo | restraint = confidence: пустой экран, один курсор, одна мысль |
| 6 | Sparrow — Mail for iPhone | https://vimeo.com/32852176 | device-as-stage, callouts на жесты, single-hand narrative |
| 7 | Dark Noise product video | https://www.youtube.com/watch?v=YEXRx5wZ-cw | self-aware editing, jump-cut energy |
| 8 | Mimestream Teaser | https://www.youtube.com/watch?v=LmtKeKRd5kk | problem→agitation→solution за 45с в три акта |
| 9 | Knudson & Moll — *Colosseo Type* | https://vimeo.com/9971247 | structural analogy: pipeline как архитектура |
| 10 | Ben Barrett-Forrest — *History of Typography* | https://www.youtube.com/watch?v=wOgIkxAfJsk | stop-motion, material metaphor для абстракции |

**Паттерны hook'а из этих 10:** aesthetic shock (Atipo), scale jump (Eames), problem agitation (Mimestream), number drop (Barrett-Forrest), contrast cut (Dark Noise). В 30-90 сек побеждает не объяснение, а *вопрос* «что это?».

**Pacing:** медленный (3-5 сек hold) = authority (iA, Pentagram). Быстрый (15-20 cuts/мин) = dopamine (Sparrow, Mimestream). Для AB_TEST рекомендуется **гибрид**: 3-сек hold на hero metric, 1-сек burst на transitions.

**Voice:** в 9 из 10 примеров — silent. Из бенчмарков Wistia 2023 voice-over даёт +15-25% completion, **но только** если calm/authoritative; AI-TTS robotic и corporate-monotone проваливают. Default для AB_TEST: **silent с kinetic typography**, voice — опция.

## 5. Структура и что должно отличаться по длительностям

Используй каркас **HOOK → REVEAL → PUNCH** для всех трёх. Различие — что отрезать.

### 30 секунд — для cold outreach в LinkedIn / X DM нанимающему менеджеру
- **HOOK 0-5с**: один шок-факт или хирургический визуальный приём.
- **REVEAL 5-22с**: 3-4 микро-сцены, каждая = одна идея за 4-5 сек.
- **PUNCH 22-30с**: одна-фраза-tagline + URL.
- Что **отрезать**: всю историю «почему это важно», все примеры, любую biography.
- Цель: «что это и зачем мне дальше смотреть».

### 60 секунд — для портфолио-сайта / hub-страницы / резюме-ссылки
- **HOOK 0-5с**: тот же или похожий, можно длиннее (до 7с).
- **CONTEXT 5-15с**: один проверяемый кейс провала из секции 3 как причина существования продукта.
- **REVEAL 15-45с**: 4-6 фич с конкретикой (group-sequential, SRM, CUPED, Bayesian) — **показать на UI**, не рассказать.
- **PUNCH 45-60с**: differentiation против Optimizely / Statsig / GrowthBook + URL.
- Что **отрезать**: технологический стек, тесты, CI, accessibility, multilang.
- Цель: «понимаю статистику + умею собрать продукт».

### 90 секунд — для extended view (HR делится с инженером в команде)
- **HOOK 0-5с**: тот же.
- **CONTEXT 5-20с**: 2 кейса провалов (один продуктовый — Tropicana/Snapchat; один инструментальный — Peter Borden A/A или Optimizely 57% FPR).
- **REVEAL 20-65с**: 6-8 микро-сцен, фичи + сценарий использования (как именно пользователь планирует эксперимент через wizard).
- **PROOF 65-80с**: тесты / CI / coverage / accessibility / multilang — **очень коротко, текстовые badges**, не пересказ.
- **PUNCH 80-90с**: tagline + URL + GitHub.
- Цель: «production-grade + статистика + accessibility — стоит говорить».

## 6. Формат ответа

Для каждой длительности (30 / 60 / 90) дай таблицу сцен:

```
## XXс — {назначение}

| t (sec) | On-screen visual | On-screen text | Voiceover (если есть) | Visual notes |
|---------|------------------|----------------|----------------------|--------------|
| 0-3     | ...              | "..."          | (silent)             | ...          |
| 3-7     | ...              | "..."          | ...                  | ...          |
```

Затем краткая мета-секция:
- **Hook formula**: какой паттерн из 5 (aesthetic shock / scale jump / problem agitation / number drop / contrast cut)
- **Pacing**: slow / fast / hybrid
- **Voice**: silent / voiced (с обоснованием)
- **Tagline**: одна фраза для PUNCH
- **Что отрезано** относительно следующей длительности (только для 30 и 60)

В конце — **общий комментарий** (≤150 слов): какое самое сильное место сценария, какое самое слабое, какой кейс из секции 3 ты выбрал и почему, какой референс из 10 повлиял больше всего.

## 7. Что НЕ делать

- Не использовать Довгань / Nestlé For Men / другие FMCG-провалы. Только онлайн / digital / dev-tool кейсы.
- Не выдумывать цифры. Если в секции 3 нет — не используй. Не пиши «65% experiments fail», если этого нет в фактах.
- Не делать slideshow из мелких PNG. Hero shots с callouts (стрелки, обводки).
- Не использовать AI-TTS robotic голос даже в плане-комментарии.
- Не вписывать в overlays «🚀 try now», «👇 link below», «💡 pro tip».
- Не делать talking head автора. Зритель не знает автора и ему всё равно.
- Не пересказывать README. Покажи UI — пусть зритель сам прочитает экран.
- Не делать final-card («GitHub: …, Demo: …») в каждом ролике одинаковой — для 30с достаточно URL мелким шрифтом 2 секунды; для 90с можно отдельный кадр.

---

**Всё. Жду три сценария + meta-секцию + общий комментарий.**
