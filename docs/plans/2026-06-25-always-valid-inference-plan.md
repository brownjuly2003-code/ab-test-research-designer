# AB_TEST — Always-valid inference (mSPRT) plan

## Goal
Добавить **anytime-valid** мониторинг живого эксперимента: always-valid p-value и confidence
sequence на базе mixture SPRT (Robbins; Johari, Pekelis & Walsh, *Always Valid Inference*,
arXiv:1512.04922). Это закрывает реальную дыру текущего sequential-слоя: O'Brien-Fleming требует
**заранее фиксированного числа looks**, а аналитик смотрит дашборд в произвольные моменты. mSPRT
контролирует type-I при **непрерывном подглядывании на любой остановке**.

Дифференциатор экспертизы (Optimizely Stats Engine / Statsig / Eppo строят на этом). Осмысленно
дополняет существующий group-sequential, образуя честную пару: pre-planned looks vs anytime-valid.

## Math (закрытая форма, stdlib-only)
Для normal mixing `H = N(0, τ²)` на эффекте, с наблюдаемой разностью `θ̂` и её дисперсией
`V = Var(θ̂)`:

```
Λ_n = sqrt( V / (V + τ²) ) · exp( τ²·θ̂² / (2·V·(V + τ²)) )
```

- **always-valid p-value:** `p = min(1, 1/Λ_n)`. Под H0 `Λ_n` — неотрицательный мартингал с
  `E[Λ_n]=1` → по неравенству Ville `P(∃n: p_n ≤ α) ≤ α` (anytime-valid).
- **(1−α) confidence sequence:** `θ̂ ± r`, где
  `r = sqrt( (2·V·(V+τ²)/τ²) · ( ln(1/α) + ½·ln((V+τ²)/V) ) )`.
  CS исключает 0 ⟺ always-valid `p < α` (дуальность).
- **τ² (mixing variance):** по Johari et al. оптимально ≈ масштаб ожидаемого эффекта (mixture
  концентрируется вокруг правдоподобного θ). Дефолт в live = (ожидаемый абсолютный эффект под MDE)²
  из сохранённого design; honest fallback на наблюдаемый масштаб, если design/MDE недоступен.

`θ̂`, `V` берём из тех же моментов, что и отображаемый CI (unpooled SE) — никакой новой
тест-статистики в существующих путях, как в уроках D-1/E5.

## Phases
- **P1 — stats/always_valid.py** (чистые функции, stdlib-only): `msprt_log_likelihood_ratio`,
  `always_valid_p_value`, `confidence_sequence`, единый `evaluate_always_valid(...)`. Валидация
  входов, докстринг с источником и честными кавеатами (нормальное приближение; plug-in V).
- **P2 — тесты** `test_always_valid.py`: (a) **Monte-Carlo anytime type-I** — под H0 при подглядывании
  на каждом шаге доля «p когда-либо < α» ≤ α (доказывает корректность); (b) confidence sequence
  накрывает истинный эффект ≥ 1−α по времени; (c) сверка Λ/p/r с эталонными числами; (d) краевые
  случаи (V→0, τ²→0, нулевой эффект → p=1) и детерминизм.
- **P3 — интеграция live-stats**: always-valid блок в `_binary_comparison` и `_continuous_comparison`;
  τ² из design MDE; FWER-консистентность (использовать тот же `adjusted_alpha`, что Bonferroni-путь).
- **P4 — схема + контракт**: `LiveAlwaysValidBlock` + поле `always_valid` в `LiveComparison`;
  регенерация `generate_frontend_api_types.py` + `generate_api_docs.py` (`--check` зелёный).
- **P5 — frontend**: блок «Always-valid (anytime) monitoring» в `LiveStatsSection.tsx`
  (p-value + confidence sequence + пояснение «безопасно смотреть в любой момент»); i18n×7
  (`results.liveStats.alwaysValid` + `accordion`), паритет ключей; component-тест.
- **P6 — гейт**: backend pytest (stats/live-stats/routes), vitest `--no-file-parallelism`, tsc, build,
  contract `--check`, locale-parity — серийно (Windows-thrashing). Локальный коммит. Docs-апдейт.

## Done When
- [ ] mSPRT-математика корректна и **эмпирически** контролирует anytime type-I ≤ α (тест).
- [ ] always-valid блок виден в live-stats UI на 7 локалях, FWER-консистентен с Bonferroni-путём.
- [ ] Контракт регенерирован (OpenAPI/TS/API.md `--check`), весь локальный гейт зелёный.

## Notes / constraints
- Не /auto: push/PR/merge/deploy — по согласованию.
- stats-слой dependency-free → только `math` (+ существующие `normal_ppf`/`cdf` при нужде).
- Нормальное приближение и plug-in дисперсия — стандарт индустрии для A/B; кавеат честный в докстринге.
- τ² влияет на мощность, НЕ на валидность type-I (валидность держится при любом фиксированном τ²>0).
