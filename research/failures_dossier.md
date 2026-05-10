# Dossier: A/B Testing Failures и инструментальные ошибки

> **Назначение**: проверяемые факты с источниками для портфолио-питча open-source A/B testing инструмента.  
> **Правило**: если факт не подтверждён проверенным первоисточником — помечен `[НЕ ПОДТВЕРЖДЕНО]`.

---

## 1. Российские маркетинговые провалы по гендерному / нишевому позиционированию

### «Довгань Дамская» — водка «для женщин»
- **Год / Период**: конец 1990-х
- **Компания / Продукт**: Владимир Довгань, водка «Довгань Дамская»
- **Что произошло**: Продукт позиционировался как женская водка (предположительно с мягким дизайном). Провалился, потому что воспринимался прежде всего как водка «Довгань», и лишь затем как «Дамская». Кроме того, исследователи рынка отмечают: женщины, выбирающие крепкий алкоголь, психологически «практически мужчины» и не принимают «бабочек» на бутылке — продукт воспринимается ими как брутальный.
- **Цифры**: нет точных цифр убытков в открытом доступе
- **Источник**: https://www.sostav.ru/columns/opinion/2008/stat21/ (Sostav.ru, 2008 — колонка о гендерном маркетинге алкоголя, ссылается на кейс 1990-х)

### «Белая пантера» — женская водка РВВК
- **Год / Период**: начало 2000-х
- **Компания / Продукт**: РВВК (Российская водочная компания), водка «Белая пантера»
- **Что произошло**: Запуск «женской» водки. Проект закрыт после выяснения, что «женщинам не нужна женственная водка». Слабый пол воспринимает водку как брутальный продукт и ожидает соответствующего визуального решения.
- **Цифры**: нет точных цифр
- **Источник**: https://www.sostav.ru/columns/opinion/2008/stat21/ (тот же материал Sostav.ru)

### Nestlé Classic for Men / Nestlé For Men — мужской шоколад в России
- **Год / Период**: запуск — **ноябрь 2005**; подарочная упаковка «Неприкосновенный Запас» — **февраль 2008**
- **Компания / Продукт**: Nestlé Россия, шоколад «Nestlé Classic for Men» (позже «Nestlé For Men»)
- **Что произошло**: Nestlé вывела на рынок прямоугольную плитку шоколада с крупными дольками, позиционируемую исключительно для мужчин. Слоган: **«Беречь от женщин»**, на упаковке — «Неприкосновенная мужская собственность». Рекламная кампания (Lowe Adventa, ноябрь–декабрь 2005) была построена как пародия на женские ток-шоу: огороченные жены жаловались, что муж реже бывает дома, предпочитая гараж и рыбалку. Мотивация запуска — стагнация плиточного шоколада и отъём доли конкурентом Ritter Sport, у которого 50% покупателей оказались мужчинами. Masmi Research Group по заказу Nestlé выяснила: 76% мужчин едят шоколад время от времени, но регулярно — только 32%; психологических барьеров нет, «сильный пол не покупает шоколад из-за отсутствия „мужского" варианта». К 2015 году продукт исчез с прилавков (блогер упоминает «his very last Nestle for Men bar», купленный годами ранее). В академических работах продукт фигурирует как пример гендерного маркетинга с недостатками коммуникационной стратегии.
- **Цифры**: доля Nestlé на рынке плиточного шоколада в первом полугодии 2005 сократилась с 35,2% до 33,8% (по данным «Бизнес Аналитики»). Ritter Sport вырос с 2,5% до 4,6% и обогнал Nestlé Classic (4,3%). Точных цифр провала мужского шоколада в открытых источниках нет.
- **Источник**:
  - https://www.kommersant.ru/doc/862352 (Коммерсантъ / «Ниша в шоколаде», 2005/2006 — детали запуска, цифры рынка, цитаты Tarasinkevich, Brener)
  - https://dela.ru/articles/17844/ (Дела.ru — републикация материала Коммерсанта)
  - https://www.sostav.ru/eng/news/2005/12/09/r1/ (Sostav.ru, 2005 — анонс запуска с упоминанием слогана "Protect from women")
  - https://www.sostav.ru/news/2008/02/27/27r/ (Sostav.ru, 2008 — дизайн подарочной упаковки «Неприкосновенный Запас» от бюро «Ауксе Кей Пятрас»; стилизация под военизированный сундучок с пряжкой «беречь от женщин»)
  - https://wanderlustandlipstick.com/blogs/pamperspakhlava/2015/11/06/nestle-for-men/ (Wanderlust and Lipstick, 2015 — блог, подтверждающий, что продукт к 2015 исчез с прилавков)
  - https://cyberleninka.ru/article/n/metodika-primeneniya-delovyh-igr-v-obuchenii-studentov-ekonomicheskih-spetsialnostey (CyberLeninka — академическая работа, анализирующая рекламную кампанию Nestlé Classic FOR MEN как кейс с «недостатками коммуникационной стратегии»)

---

## 2. Evan Miller и ошибки в онлайн A/B-калькуляторах

### Статья «How Not To Run An A/B Test»
- **Год публикации**: 18 апреля 2010
- **Автор**: Evan Miller
- **Ключевые ошибки, разобранные в статье**:
  1. **Peeking / Optional stopping / Repeated significance testing**: если вы смотрите на результаты теста по ходу дела и останавливаете эксперимент при достижении значимости, все заявленные уровни значимости становятся бессмысленными. При непрерывном подглядывании после каждого наблюдения фактический уровень ложноположительных срабатываний может достигать **26,1%** при заявленных 5%.
  2. **Фиксация sample size**: классическая значимость предполагает, что размер выборки зафиксирован заранее. Нарушение этого предположения делает p-value некорректными.
  3. **Рекомендации по sequential и Bayesian дизайну**: как альтернативы медицинской статистике, которые «кто-то действительно должен адаптировать для веба».
- **Конкретные калькуляторы / платформы, названные по имени**: в оригинальной статье 2010 года **прямо по имени не названы**, но указано: «At least one A/B testing framework out there actually provides code for automatically stopping experiments after there is a significant result. That sounds like a neat trick until you realize it's a statistical abomination.»
- **Реакция индустрии**:
  - Статья стала де-факто индустриальным стандартом, цитируется в десятках академических работ (KDD, ACM, arXiv).
  - **Optimizely** в 2015 году запустила **Stats Engine** на основе sequential testing (mSPRT) и FDR control — прямой ответ на проблему peeking. В whitepaper (Johari et al., KDD 2017) указано, что классические методы дают error rates «well in excess of the nominal desired false positive probability».
  - Появились open-source реализации sequential A/B testing (в том числе обсуждения на основе работы Miller).
- **Источник**:
  - https://www.evanmiller.org/how-not-to-run-an-ab-test.html (Evan Miller, 2010)
  - https://dl.acm.org/doi/pdf/10.1145/3314183.3323853 (KDD 2017, Peeking at A/B Tests — cites Miller 2010)
  - https://www.optimizely.com/insights/blog/statistics-for-the-internet-age-the-story-behind-optimizelys-new-stats-engine/ (Optimizely, 2015)

### Дополнительное: критика one-tailed тестов в коммерческих инструментах
- **Год**: 2014 (оригинал Peter Borden), репост 2021
- **Что произошло**: статья «How Optimizely (Almost) Got Me Fired» разоблачает, что **Optimizely** и **Visual Website Optimizer (VWO)** использовали **one-tailed** тесты (в 2014 г.), в то время как **Adobe Test&Target** и **Monetate** — two-tailed. One-tailed тесты дают в 2 раза больше ложноположительных срабатываний в нежелательном направлении. Автор запустил A/A-тест (две идентичные страницы) в Optimizely и получил «+18,1% improvement» с «100% probability of being accurate».
- **Источник**: https://analythical.com/blog/optimizely-got-me-fired (Analythical, репост статьи Peter Borden / SumAll, 2014)

---

## 3. Провалы и баги в коммерческих инструментах для экспериментов

### Optimizely — «peeking problem» и запуск Stats Engine (2015)
- **Год / Период**: до 2015 — классическая статистика с fixed-horizon t-test; январь 2015 — запуск Stats Engine
- **Компания / Продукт**: Optimizely
- **Что произошло**: До Stats Engine пользователи могли непрерывно мониторить результаты и останавливать тесты при достижении значимости. Optimizely признала, что это приводило к тому, что error rate превышал номинальный в 5–10 раз (например, 57% chance of false declaration при просмотре после каждого посетителя при заявленных 5%). Stats Engine внедрил always-valid p-values на основе mixture Sequential Probability Ratio Test (mSPRT) и False Discovery Rate (FDR) control.
- **Цифры**: снижение false positive rate с >20% (в симуляциях peeking) до <5%; примерно 20% меньше «победителей» при FDR-контроле по сравнению с некорректированным FWER
- **Источник**:
  - https://www.optimizely.com/insights/blog/statistics-for-the-internet-age-the-story-behind-optimizelys-new-stats-engine/ (Optimizely blog, 2015)
  - http://library.usc.edu.ph/ACM/KKD%202017/pdfs/p1517.pdf (KDD 2017, Johari et al., «Peeking at A/B Tests» — technical paper)
  - https://www.optimizely.com/contentassets/9205a8a811e84957a7cca527d4af20be/whitepaper_optimizely_stats_engine.pdf (Optimizely Stats Engine whitepaper)

### Sample Ratio Mismatch (SRM) — публичные кейсы
- **Год / Период**: 2012–2019+
- **Компания / Продукт**: Microsoft (Bing, MSN, Microsoft Store, Teams), Booking.com и др.
- **Что произошло**: SRM — расхождение между ожидаемым и фактическим сплитом трафика. Как отмечает Ronny Kohavi, SRM с p-value < 1/1000 практически всегда означает баг или проблему с данными. В статье Fabijan et al. (KDD 2019) разобрана таксономия SRM на основе реальных кейсов Microsoft:
  - **Bing / MSN**: баг в assignment service — контролю выделялось на 1 bucket меньше, чем нужно (49,9/50,1 вместо 50/50). Проблема выявлена через SRM в A/A-тесте.
  - **Microsoft Store / Homepage**: SRM из-за того, что поисковая кампания имела misconfigured URL, ведущий напрямую на одну из вариаций, форсируя assignment.
  - **Microsoft Teams**: triggered analysis показала SRM, потому что старый дизайн FRE грузился дольше, пользователи в контроле уходили раньше, и telemetry events терялись.
  - **Bot detection**: в одном эксперименте treatment (16 карточек вместо 12) привёл к тому, что самые активные пользователи были классифицированы как боты и удалены из анализа только в treatment-группе, что вызвало SRM и инверсию результатов.
- **Цифры**: при 10 000 пользователей отклонение 51/49 может быть статзначимым и указывать на серьёзный баг
- **Источник**:
  - https://exp-platform.com/Documents/2019_KDDFabijanGupchupFuptaOmhoverVermeerDmitriev.pdf (Fabijan et al., KDD 2019, «Diagnosing Sample Ratio Mismatch in Online Controlled Experiments»)
  - https://www.statsig.com/blog/building-experimentation-infrastructure-and-culture-ronny-kohavi (Statsig blog, интервью с Ronny Kohavi)

### Google Optimize — критика статистического движка
- **Год / Период**: 2016–2023 (sunset в сентябре 2023)
- **Компания / Продукт**: Google Optimize
- **Что произошло**: Google Optimize использовал Bayesian inference, но провайдер не раскрывал полностью, какие именно модели (hierarchical, contextual, restless) применялись к конкретным экспериментам. Критики отмечали, что это создаёт «чёрный ящик»: результаты могут быть сильно смещены ранними эффектами (newness bias), а пользователь не может проверить корректность. Также были опасения, что непрозрачные priors ускоряют выводы за счёт точности.
- **Цифры**: нет публичных цифр конкретных финансовых потерь из-за багов движка
- **Источник**: https://blog.analytics-toolkit.com/2018/google-optimize-statistical-significance-statistical-engine/ (Analytics Toolkit, 2018)

### VWO, AB Tasty, Adobe Target, GrowthBook — документированные публичные баги
- **VWO / Optimizely (2014)**: использование one-tailed тестов, завышение значимости, A/A-тесты показывали ложные победители (см. раздел 2, Peter Borden).
- **AB Tasty, Adobe Target, GrowthBook**: в открытых источниках **не найдены документированные публичные кейсы крупных багов, искажавших результаты экспериментов на уровне статистического движка**, сопоставимые с Optimizely pre-2015. Adobe Target упоминает «9 Pitfalls of A/B Testing» в своей документации, но это образовательный материал, а не признание бага.
- **GrowthBook**: open-source платформа; в документации предупреждает о false positives в A/A-тестах (10% chance при 1 метрике и дефолтных порогах 95%/5%), но это ожидаемое статистическое поведение, а не баг.
- **Источник**:
  - https://analythical.com/blog/optimizely-got-me-fired (AB Tasty / VWO / Optimizely one-tailed issue)
  - https://docs.growthbook.io/kb/experiments/aa-tests (GrowthBook A/A tests documentation)
  - https://business.adobe.com/assets/pdfs/products/target-beyond-ab-testing/beyond-ab-testing.pdf (Adobe Target whitepaper)

### Simpson's Paradox в реальных A/B-экспериментах
- **Определение**: тренд, наблюдаемый в подгруппах, исчезает или переворачивается при агрегировании данных.
- **Классические подтверждённые кейсы**:
  - **UC Berkeley (1973)**: общие данные показывали дискриминацию против женщин (35% admission vs 44% у мужчин), но по департаментам женщины имели равный или чуть более высокий шанс поступления; женщины просто подавали в более конкурсные департаменты.
  - **Kidney stone treatments (1986)**: Treatment A (open surgery) была эффективнее и при малых, и при больших камнях, но при агрегировании Treatment B казалась лучше, потому что её чаще назначали при малых камнях (менее тяжёлых случаях).
- **Применение к A/B testing**: Ronny Kohavi приводит пример с изменением traffic allocation mid-experiment: treatment выигрывает и в пятницу, и в субботу по отдельности, но проигрывает при агрегировании из-за разного распределения трафика по дням.
- **Источник**:
  - https://conversion.com/blog/3-mistakes-invalidate-ab-test-results/ (Conversion.com, Simpson's Paradox в A/B тестах с примером Kohavi)
  - https://www.statsig.com/perspectives/simpsons-paradox-explained (Statsig, 2025)
  - https://jiahai-feng.github.io/posts/simpsons-paradox/ (Jiahai Feng, 2023 — Berkeley & kidney stones)

---

## 4. Громкие провалы продуктов / редизайнов

### Tropicana — редизайн упаковки 2009
- **Год / Период**: январь 2009 (запуск), откат в феврале 2009 (~47 дней)
- **Компания / Продукт**: Tropicana (PepsiCo), Pure Premium orange juice
- **Что произошло**: Агентство Arnell полностью сменило упаковку: убрали iconic «апельсин с соломинкой», заменили на стакан сока, сделали вертикальный логотип, изменили крышку. Потребители не узнавали продукт на полке, воспринимали как generic бренд супермаркета.
- **Цифры**: продажи упали на **20%** за два месяца; упущенная выручка около **$30 млн**; рекламная кампания + редизайн обошлись в ~$35 млн; общие потери инициативы оцениваются в **> $50 млн**; Tropicana откатила дизайн через 47 дней.
- **Источник**:
  - https://www.thebrandingjournal.com/2015/05/what-to-learn-from-tropicanas-packaging-redesign-failure/ (The Branding Journal, 2015)
  - https://www.greatideasforteachingmarketing.com/tropicanas-packaging-case-study/ (Great Ideas for Teaching Marketing, 2026)

### New Coke — 1985
- **Год / Период**: апрель–июль 1985
- **Компания / Продукт**: The Coca-Cola Company
- **Что произошло**: Coca-Cola заменила классическую формулу на более сладкую New Coke после того, как 190 000 потребителей в blind taste tests предпочли её. Упустили эмоциональную привязанность 10–12% лояльных потребителей. Обратная связь: 8 000 звонков в день, 40 000 писем. Вернул Coca-Cola Classic через 10 недель.
- **Цифры**: New Coke достигла ~15% market share к концу 1985, Coca-Cola Classic ~5,9%; Pepsi временно обогнал оба продукта вместе взятые. К 1986 Classic вернулся на ~18,9%, Pepsi ~18,5%. New Coke (позже Coke II) сошла на нет к <3%.
- **Источник**:
  - https://www.greatideasforteachingmarketing.com/new-coke-story-the-full-case-study/ (Great Ideas for Teaching Marketing, 2026)
  - https://www.thebrandingjournal.com/2025/02/new-coke/ (The Branding Journal, 2025)
  - Pendergrast, M. (1993). *For God, Country & Coca-Cola* (цитируется в case study)

### Bud Light — Dylan Mulvaney, 2023
- **Год / Период**: апрель 2023
- **Компания / Продукт**: Bud Light (Anheuser-Busch InBev)
- **Что произошло**: Партнёрство с трансгендерной инфлюенсеркой Dylan Mulvaney для рекламы на Instagram вызвало бойкот. Kid Rock опубликовал видео с расстрелом банок Bud Light.
- **Цифры**:
  - Продажи Bud Light в США упали на **26,5%** (месяц, закончившийся 15 июля 2023, Nielsen).
  - К октябрю 2023: долларовые продажи Bud Light **−29%** за 4 недели (год к году).
  - За год (2023): упали почти на **19%** year-to-date.
  - Во Q2 2023 выручка AB InBev в США **−10,5%**, EBITDA **−28,2%**.
  - Северноамериканская органическая выручка упала на **$1,4 млрд** за 2023 (по данным CNN, цитируемым Metro Weekly).
  - Bud Light потеряла статус #1 пива в США (удерживала с 2001); уступила Modelo Especial.
  - Рыночная капитализация AB InBev: начальная потеря ~**$4 млрд**.
- **Источник**:
  - https://fortune.com/2023/10/31/bud-light-earnings-dylan-mulvaney-transgender-promotion-backlash/ (Fortune, 2023)
  - https://www.cbsnews.com/news/bud-light-anheuser-busch-dylan-mulvaney-beer-sales/ (CBS News, 2023)
  - https://www.metroweekly.com/2024/03/bud-light-boycott-cost-company-1-4-billion-in-sales/ (Metro Weekly, 2024)
  - https://www.usatoday.com/story/money/2024/05/09/bud-light-boycott-sales-impact/73630487007/ (USA Today, 2024)

### Snapchat — редизайн 2018
- **Год / Период**: январь 2018 (редизайн), Q1–Q3 2018 (последствия)
- **Компания / Продукт**: Snap Inc., Snapchat
- **Что произошло**: Глобальный редизайн, разделяющий контент друзей и брендов/медиа. Пользователи раскритиковали; петиция на Change.org собрала >1,2 млн подписей. Kylie Jenner твитнула 21 февраля 2018: «Sooo does anyone else not open Snapchat anymore?» — после чего акции Snap упали на ~6% (потеря ~$1,3 млрд market cap за день, по данным Bloomberg).
- **Цифры**:
  - Q1 2018: **191 млн** DAU
  - Q2 2018: **188 млн** DAU (−3 млн, первое падение в истории)
  - Q3 2018: **186 млн** DAU (ещё −2 млн)
  - Итого за два квартала: потеря **~5 млн** DAU.
  - CEO Evan Spiegel признал, что падение «primarily driven by a slightly lower frequency of use among our user base due to the disruption caused by our redesign».
- **Источник**:
  - https://abcnews.com/GMA/Culture/snapchat-stock-falls-kylie-jenners-tweet/story?id=53287900 (ABC News, 2018)
  - https://9to5mac.com/2018/10/25/snapchat-earnings-q3-2018/ (9to5Mac, 2018)
  - https://beebom.com/snapchat-recorded-a-strong-second-quarter-but-also-lost-3-million-users/ (Beebom, 2018)

### Digg v4 — 2010
- **Год / Период**: август 2010
- **Компания / Продукт**: Digg
- **Что произошло**: Полный редизайн («100% rewrite»), удаление популярных функций (bury button, favorites, upcoming news), приоритизация контента крупных издателей через auto-submit API. Пользователи устроили «Great Digg Migration» — флудили главную страницу Digg ссылками на Reddit.
- **Цифры**:
  - Пик: ~40 млн monthly visitors, оценка $160 млн (2008); слияние с Google обсуждалось на $200 млн.
  - После v4: трафик упал на **50%**; US visits **−26%**, UK visits **−34%**.
  - Digg потерял **5,6 млн** посетителей за месяц (**−30%** аудитории).
  - Reddit вырос на **230%** в 2010.
  - В 2012 Digg продали за **$500 000** (технология + бренд Betaworks) — доля от прежней оценки.
- **Источник**:
  - https://www.startupbooted.com/what-happened-to-digg (Startup Booted, 2025)
  - https://backtofrontshow.com/what-happened-to-digg/ (Back to Front Show, 2025)
  - https://dfarq.homeip.net/digg-v4-and-lessons-not-learned/ (Homeip, 2025)
  - https://www.webpronews.com/diggs-revival-rose-and-ohanian-challenge-reddits-dominion/ (WebProNews, 2026)

### Microsoft Bing — баг, «улучшающий» ключевые метрики
- **Год / Период**: ~2012 (опубликовано в KDD 2012)
- **Компания / Продукт**: Microsoft Bing
- **Что произошло**: В эксперименте случайно показывали очень плохие поисковые результаты. Две ключевые метрики организации значимо улучшились: distinct queries per user **+10%**, revenue per user **+30%**. Объяснение: деградированные результаты заставляли пользователей делать больше запросов и чаще кликать по рекламе — краткосрочный рост, разрушительный для долгосрочной доли запросов (query share).
- **Цифры**: +10% queries/user, +30% revenue/user
- **Источник**:
  - https://notes.stephenholiday.com/Five-Puzzling-Outcomes.pdf (Kohavi et al., KDD 2012, «Trustworthy Online Controlled Experiments: Five Puzzling Outcomes Explained»)
  - https://sites.pitt.edu/~prashk/inf3350/f12/september_19_2.pdf (слайды с презентации Kohavi)

### Bing — click tracking instrumentation bug
- **Год / Период**: ~2012 (тот же KDD 2012 paper)
- **Компания / Продукт**: Microsoft Bing
- **Что произошло**: Добавление JavaScript, обновляющего session-cookie при клике на результат поиска, слегка замедляло переход. A/B-тест показал, что пользователи стали кликать чаще. На самом деле это был instrumentation difference: Chrome/Firefox/Safari прерывают beacon-запросы при навигации, а небольшая задержка давала beacon больше времени на отправку. Internet Explorer не прерывал запросы, и в IE эффекта не было — это был «жёлтый флаг».
- **Цифры**: искусственное увеличение кликов в non-IE браузерах
- **Источник**: https://notes.stephenholiday.com/Five-Puzzling-Outcomes.pdf (Kohavi et al., KDD 2012)

### Airbnb — pricing guidance: short-term vs long-term divergence
- **Год / Период**: 2023 (публикация CIKM)
- **Компания / Продукт**: Airbnb
- **Что произошло**: В pricing experiments часто наблюдается strong novelty effect: метрика revenue трендит сильно в одну сторону (например, отрицательную), а затем меняет направление и стабилизируется только через месяцы. Запуск варианта на основе короткого теста рискован, потому что short-term эффект может быть противоположен long-term.
- **Цифры**: на графике CIKM paper показан пример, где cumulative revenue metric трендит отрицательно месяцами, прежде чем развернуться
- **Источник**: https://airbnb.tech/wp-content/uploads/sites/19/2023/12/CIKM.pdf (Deng et al., CIKM 2023, «The Price is Right: Removing A/B Test Bias in a Marketplace of Expirable Goods»)

### Booking.com — «walkability index» и другие провальные A/B
- **Год / Период**: 2000-е–2010-е
- **Компания / Продукт**: Booking.com
- **Что произошло**: Booking.com запускает ~1000 concurrent experiments. По словам Gillian Tans (ex-CEO), «мы ошибались так много раз». Примеры:
  - **Walkability index**: команда предполагала, что индекс «walkability» (пешая доступность) улучшит букинги — тест провалился.
  - **Travel packages**: предполагали, что клиенты хотят пакеты «отель + другие продукты» — не сработало.
  - **Live chat**: чат для помощи в бронировании — не сработал.
  - **WiFi strength**: баннер «WiFi Strength – Strong» не дал uplift; позже выяснилось, что важен не сам сигнал, а возможность смотреть Netflix / писать email.
- **Цифры**: Booking.com публично заявляет, что **~90% идей проваливаются** в A/B-тестах (по аналогии с Microsoft ~66%, Bing ~85%, Airbnb ~92%).
- **Источник**:
  - https://vwo.com/blog/cro-best-practices-booking/ (VWO blog, 2025 — ссылается на HBR case study)
  - https://www.hustlebadger.com/what-do-product-teams-do/booking-com-experimentation-culture/ (Hustle Badger, 2025)
  - https://www.lennysnewsletter.com/p/the-ultimate-guide-to-ab-testing (Lenny's Podcast / Newsletter, 2023 — интервью с Ronny Kohavi)

---

## 5. Бонус — анти-паттерны процесса A/B

### Недостаточная мощность / тесты на малой выборке
- **Проблема**: запуск тестов без предварительного расчёта sample size приводит к underpowered экспериментам, которые не могут обнаружить реальный эффект. Решение — фиксация MDE и использование калькуляторов sample size.
- **Источник**:
  - https://www.evanmiller.org/how-not-to-run-an-ab-test.html (Evan Miller, 2010)
  - https://exp-platform.com/rules-of-thumb/ (Kohavi et al., «Seven Rules of Thumb for Website Experimenters»)

### Неверная primary metric (OEC) — оптимизировали CTR, упала retention
- **Кейс Microsoft Bing**: при плохих поисковых результатах queries/user и revenue/user растут, но это разрушает long-term query share. Привело к формализации Overall Evaluation Criterion (OEC) для Bing: sessions/user (proxy для удовлетворённости), а не queries/user или revenue/user.
- **Кейс push-уведомлений**: мобильное приложение гонит DAU через агрессивные пуши — краткосрочный рост DAU, но long-term churn и uninstalls.
- **Источник**:
  - https://notes.stephenholiday.com/Five-Puzzling-Outcomes.pdf (Kohavi et al., KDD 2012)
  - https://www.statsig.com/blog/kpi-traps-successful-experiments-can-fail (Statsig, 2025)

### HARKing / p-hacking / «Texas Sharpshooter» в продуктовых командах
- **Определения**:
  - **HARKing** (Hypothesizing After the Results are Known): придумывание гипотезы после просмотра данных.
  - **Texas Sharpshooter**: стреляешь по амбару, потом рисуешь мишень вокруг самых плотных кластеров отверстий. В A/B-тестировании: «мы тестировали net bookings, но увидели рост кликов, поэтому деплоим».
  - **p-hacking**: досрочная остановка, выбор подходящего сегмента post-hoc, добавление метрик до достижения значимости.
- **Академическое исследование**: Miller (2024) в *Information Systems Research* обнаружил систематические признаки p-hacking в e-commerce A/B testing на уровне индустрии через анализ распределения p-values (discontinuity около 0,05).
- **Источник**:
  - https://pubsonline.informs.org/doi/10.1287/isre.2024.0872 (Miller A., «An Investigation of p-Hacking in E-Commerce A/B Testing», Information Systems Research, 2024)
  - https://longform.asmartbear.com/p-hacking/ (Jason Cohen, «p-Hacking your A/B tests», 2024)
  - https://www.hustlebadger.com/what-do-product-teams-do/booking-com-experimentation-culture/ (Booking.com — Texas Sharpshooter problem)

### Primacy / Novelty Effect — краткосрочный победитель, долгосрочный провал
- **Определение**:
  - **Novelty effect**: пользователи кликают на новое просто потому, что оно новое; эффект угасает.
  - **Primacy effect**: пользователи привыкли к старому, новое сначала кажется хуже; со временем адаптируются.
- **Microsoft**: carryover effects от багов Bing длились неделями и даже месяцами; buckets, подвергшиеся плохому опыту, не восстанавливались 3 месяца.
- **Airbnb**: pricing experiments могут показывать отрицательный revenue эффект месяцами, прежде чем стабилизироваться.
- **Рекомендация**: запускать long-running experiments, анализировать delta-графики по времени, смотреть только на new users (исключая primacy/novelty).
- **Источник**:
  - https://notes.stephenholiday.com/Five-Puzzling-Outcomes.pdf (Kohavi et al., KDD 2012)
  - https://ar5iv.labs.arxiv.org/html/2102.12893 (Kohavi et al., arXiv 2021, «Novelty and Primacy: A Long-Term Estimator for Online Experiments»)
  - https://airbnb.tech/wp-content/uploads/sites/19/2023/12/CIKM.pdf (Airbnb, CIKM 2023)
  - https://docs.growthbook.io/open-guide-to-ab-testing.v1.0.pdf (GrowthBook Open Guide)

### A/A-тесты как guardrail
- **Практика**: запуск двух идентичных вариантов для валидации инфраструктуры. Если A/A показывает значимую разницу — баг в assignment, tracking или SRM.
- **Источник**:
  - https://exp-platform.com/Documents/2019_KDDFabijanGupchupFuptaOmhoverVermeerDmitriev.pdf (Fabijan et al., KDD 2019)
  - https://docs.growthbook.io/kb/experiments/aa-tests (GrowthBook docs)

---

## Сводная таблица: ключевые цифры

| Кейс | Год | Потери / Эффект |
|------|-----|-----------------|
| Tropicana редизайн | 2009 | −20% sales, ~$30M потерь, >$50M общих потерь |
| New Coke | 1985 | 10 недель до отката; New Coke → <3% share |
| Bud Light × Mulvaney | 2023 | −26% sales, −$1,4B выручки NA, потеря #1 в США |
| Snapchat редизайн | 2018 | −5M DAU за 2 квартала, −$1,3B market cap (твит) |
| Digg v4 | 2010 | −50% трафика, продажа за $500K (vs $200M оценка) |
| Optimizely pre-Stats Engine | до 2015 | 57% false declaration при peeking (sim), >20% error rate |
| Bing баг (плохие результаты) | ~2012 | +10% queries, +30% revenue — ложный uplift |
| Booking.com fail rate | 2000-е+ | ~90% идей проваливаются в A/B |

---

*Документ составлен на основе проверенных публичных источников: корпоративных блогов (Optimizely, Airbnb, Booking.com, Statsig), научных публикаций (KDD, CIKM, ACM, Information Systems Research), архивов СМИ (Fortune, CBS News, USA Today, ABC News, The Branding Journal) и признанных индустриальных практик (Ronny Kohavi — Microsoft/Amazon/Airbnb, Evan Miller).*
