# Production Recipe — AB Test Research Designer demo capture

> Recipe for recording the live demo with deterministic numbers that match story-script v3. Captured via Playwright MCP on 2026-05-10 against `https://liovina-ab-test-research-designer.hf.space`.
>
> All numbers below are **real output from the deployed product** — not invented. Screenshots in `D:\AB_TEST\research\screenshots\`.

## Two parallel configurations (use both during recording)

The product has separate UI for Binary vs Continuous metrics. CUPED only surfaces for Continuous. The video script uses both — Binary as the canonical narrative (sample size + duration + SRM + sequential), Continuous as a side-window for CUPED + Bayesian. Plan recording as two separate wizard runs.

## Configuration A — Binary canonical (use for hero sample-size scene + SRM + sequential)

| Wizard step | Field | Value | Why |
|---|---|---|---|
| 1. Project | (defaults) | Checkout redesign / e-commerce / web app | Demo defaults — no need to change |
| 2. Hypothesis | (defaults) | "Reduce checkout from 4 steps to 2" + auto-filled fields | Ditto |
| 3. Setup | Experiment type | `ab` | |
| 3. Setup | Randomization unit | `user` | |
| 3. Setup | Traffic split | `50,50` | Default — needed for SRM scene |
| 3. Setup | **Expected daily traffic** | **`12000`** | Default — yields 21d duration with the chosen MDE |
| 3. Setup | **Audience share in test** | **`0.6`** | Default; effective traffic = 7,200/day |
| 3. Setup | Variants count | `2` | |
| 4. Metrics | Metric type | `Binary` | |
| 4. Metrics | Primary metric name | `purchase_conversion` | |
| 4. Metrics | **Baseline value** | **`0.042`** (4.2%) | Default — matches v2 script's `baseline 4.2%` framing |
| 4. Metrics | Expected uplift % | `8` | |
| 4. Metrics | **MDE %** | **`7`** | **The lever**: at MDE=7 → 21 days, 75,514/variant. At MDE=8.7 → 14 days, 49,269/variant (alternate). |
| 4. Metrics | Guardrail metrics | (defaults) | `Payment error rate 2.4%`, `Refund value mean 18 ± 6.5` |
| 5. Constraints | Analysis framework | `Frequentist` (default) | Switch to `Bayesian` only for the Bayesian scene |
| 5. Constraints | **Alpha** | **`0.05`** | |
| 5. Constraints | **Power** | **`0.8`** | |
| 5. Constraints | **Interim analyses** | **`4`** | Activates O'Brien-Fleming group-sequential design with 4 looks |

## Configuration B — Continuous + 4 variants (use for CUPED + Bayesian + Multi-arm Bonferroni)

Run a SEPARATE wizard pass with these inputs:

| Wizard step | Field | Value | Why |
|---|---|---|---|
| 3. Setup | Variants count | `4` | Triggers `Bonferroni applied` in Live estimate |
| 3. Setup | Traffic split | `25,25,25,25` | Required when variants=4 |
| 4. Metrics | **Metric type** | **`Continuous`** | CUPED section only renders for continuous |
| 4. Metrics | Baseline value (mean) | `45.20` | Continuous mean |
| 4. Metrics | Std dev | `12` | |
| 4. Metrics | MDE % | `5` | |
| 4. Metrics | **Enable CUPED** | toggle ON | Surfaces `cuped_pre_experiment_std` + `cuped_correlation` fields |
| 4. Metrics | CUPED pre-experiment std dev | `5` | |
| 4. Metrics | CUPED correlation | `0.5` | ρ² = 0.25 → 25% variance reduction |
| 5. Constraints | **Analysis framework** | **`Bayesian`** | Activates posterior plot + credible interval |
| 5. Constraints | Desired precision (units) | `2` | Required in Bayesian mode |
| 5. Constraints | Credibility | `0.95` | Default — keep |
| 5. Constraints | Interim analyses | `4` | (optional, for sequential under Bayesian) |

After Run analysis, the Review page surfaces three new cards in this exact order:
- **CUPED-adjusted estimate**: `Without CUPED 591 → With CUPED (ρ²=25%) 443, −25% sample size`
- **Bayesian estimate**: `Frequentist 591 → Bayesian (95% interval) 277`
- **Bayesian posterior**: PosteriorPlot with target N=277 at 95% credibility and 2 units half-width

Plus Live estimate panel on step 4 already shows `591 / 1 day / CUPED sample size 443 / 25% variance reduction / Bonferroni applied` — single panel covers three of the four extra scenes (CUPED, multi-arm, summary).

## Real numbers that surface (verified live, both configs)

### Live estimate panel (visible from step 4 onward)

```
Sample size per variant: 75,514  users / variant
Estimated duration:      21 days  based on current traffic
```

### Group sequential design (O'Brien-Fleming, 4 looks)

```
Adjusted sample size: 77,402 per variant (2.5% more than fixed horizon)

Look | Info fraction | Cum. α spent | Z boundary | Stop if |Z| ≥
  1  |     25%       |   0.0001     |    4.05    |     4.05
  2  |     50%       |   0.0056     |    2.86    |     2.86
  3  |     75%       |   0.0236     |    2.34    |     2.34
  4  |    100%       |   0.0500     |    2.02    |     2.02
```

Tagline below the table: «Stop early at any planned look if the observed absolute Z-statistic crosses the boundary. Otherwise continue to the next analysis.»

### SRM check («Did traffic split as planned?»)

Inputs:
```
A = 24500
B = 25500
```

Output (red callout):
```
SRM detected
SRM detected — check your randomization or tracking implementation
Chi-square = 20, p = 0.000008
Expected: [25000, 25000] | Observed: [24500, 25500]
```

That gives **49.0% / 51.0% split** — visually subtle, statistically loud. Better story than the original v3 placeholder («46.8% / χ²=8.4») because at this experiment scale (~50K users) a 46.8% deviation would yield χ² > 200 — implausible. The real product correctly surfaces a tiny visual deviation as a critical bug. Keep this combo.

## Captured screenshots (10 total)

### Binary metric flow (`purchase_conversion`, baseline 0.042, MDE 7%, 21 days)

| File | Scene in script | Notes |
|---|---|---|
| `metrics-21days-MDE7.png` | step 4 — sample size + duration callout (60s/90s scenes 15-22s and 24-31s) | Live estimate `75,514 / 21 days` |
| `constraints-sequential-interim4.png` | step 5 — Frequentist/Bayesian + Alpha/Power/Interim=4 (90s scene 31-38s) | Sequential design context |
| `review-deterministic-design.png` | step 6 — top of report | Deterministic experiment design header |
| `group-sequential-obrien-fleming-4looks.png` | 90s scene 31-38s — α-spending boundaries graphic | Z-boundaries `4.05 / 2.86 / 2.34 / 2.02`, adjusted `77,402 / variant` |
| `srm-detected-chi20.png` | SRM scene 30s/60s/90s | Red callout `χ² = 20, p = 0.000008`, Expected `[25000, 25000]`, Observed `[24500, 25500]` |

### Continuous metric flow + CUPED + Bayesian + Multi-arm Bonferroni (separate setup, 4 variants, baseline mean 45.20, std dev 12, MDE 5%)

| File | Scene in script | Notes |
|---|---|---|
| `metrics-cuped-25pct-variance-reduction.png` | CUPED scene — 60s @ 36-43s, 90s @ 45-52s | Live estimate panel: `591 / variant`, `1 day`, `CUPED sample size 443`, `25% variance reduction`, `Bonferroni applied`. Single panel covers CUPED + Multi-arm at once. |
| `constraints-bayesian-mode.png` | Bayesian scene step 5 — 90s @ 52-58s | Bayesian radio selected, desired_precision=2, credibility=0.95, Interim=4 |
| `cuped-adjusted-estimate-591-to-443.png` | CUPED detail — 90s @ 45-52s | Report card: `Without CUPED 591 → With CUPED (ρ²=25%) 443`, `−25% sample size`, `Adjusted std dev: 10.3923` |
| `bayesian-estimate-frequentist-591-vs-bayesian-277.png` | Bayesian estimate — 90s @ 52-58s | Report card: `Frequentist 591 → Bayesian (95% interval) 277` |
| `bayesian-posterior-277-credible.png` | Bayesian posterior plot — 90s @ 52-58s | PosteriorPlot card: `Target sample size: 277 per variant at 95% credibility and 2 units interval half-width`, distribution plot 41.12-49.28 |

## Recording sequence (suggested)

For a single recording session:

1. **Cold start the demo** (HF Spaces free tier — first request takes ~10-30s).
2. Click `New experiment` → walk through wizard (steps 1-3 with defaults are fine).
3. **Step 4 Metrics** — set MDE = 7. **Pause for hero shot** of Live estimate panel (`75,514 / 21 days`). This is the canonical sample-size scene.
4. **Step 5 Constraints** — set Interim analyses = 4. **Pause for hero shot** of Frequentist/Bayesian + Alpha/Power + Interim dropdown. Optional: switch to Bayesian for the Bayesian scene (90s @ 52-58s) — capture posterior view, then switch back.
5. **Step 6 Review** — click `Run analysis`. Wait for results. **Hero shots in this order**:
   - Top of report: «Deterministic experiment design» (transition shot)
   - Scroll to Group sequential design table — **hero shot for sequential boundaries scene**
   - Scroll to SRM card. Type `24500` and `25500`. Click `Check for SRM`. **Hero shot of red callout** (χ² = 20).
6. Optional polish:
   - **Multilang RTL accent** (90s @ 65-70s): top-right language toggle currently shows EN/RU/DE/ES only. The README says 7 languages including AR — need to find the full picker or trigger. **TODO**: confirm where AR/ZH/FR are exposed; if hidden behind a settings menu, document the path. If only RU is easy → switch from EN to RU as a more modest «multilang signal» (less dramatic than RTL but still authentic).
   - **Decision-ready report export** (all durations, ~22-26s in 30s): scroll to the Recommendations / Calculation summary block at the bottom of the Review page; a hero shot of that section is the «report» visual.

## Resolved gaps (verified via source code 2026-05-10, см. `codex_product_gap_check.md`)

- **CUPED**: ✅ есть в `WizardDraftStep.tsx:535` — секция `cuped-section` ниже базовых полей step 4 Metrics. Поля `cuped_pre_experiment_std` + `cuped_correlation`. **Recording action**: на step 4 доскроллить вниз, заполнить CUPED, hero shot.
- **Bayesian**: ✅ полная реализация — `BayesianSection.tsx` + `PosteriorPlot.tsx`. **Recording action**: на step 5 переключить radio Frequentist→Bayesian, Run analysis, hero shot BayesianSection в Review.
- **Multilang 7 langs + RTL**: ✅ в коде (`App.tsx:12` SUPPORTED_LANGUAGES = 7, все 7 locale-файлов в `public/locales/`, `App.tsx:34` AR→RTL flip). ⚠️ live HF demo показывает только 4 кнопки — **stale build или lazy-load fail**. **Recording action**: либо записать с локального dev (`cd app/frontend && npm run dev` — гарантированный 7-flip), либо `git push` для re-deploy HF Space до записи.
- **Multi-arm correction**: ✅ Bonferroni реализован (`bonferroni_note` в API response, рендер в `LivePreviewPanel.tsx` + `SensitivityOverview.tsx`). FDR в frontend не найден — script v3 правлен, везде «Bonferroni», не «FDR». **Recording action**: step 3 Setup → Variants count = 4 → step 4 / step 6 покажут «Adjusted for multiple comparisons.» note.

## Required script v3 patches

`D:\AutoReel\docs\story-scripts-ab-test-v3.md` was written before live numbers were verified. Apply these edits:

| Where | Original | Real | Action |
|---|---|---|---|
| 60s @ 15-22s | `Duration → 14 days` callout | `Duration → 21 days` (use 21 throughout) | Drop the «14 days» variant; keep one canonical example for narrative consistency |
| 90s @ 24-31s | `Duration → 21 days` | `21 days` ✅ | Already correct |
| 30s @ 13-17s, 60s @ 29-36s, 90s @ 38-45s | `χ² = 8.4, p = 0.004 / Expected 50.0% / Observed 46.8%` | `χ² = 20, p = 0.000008 / Expected [25000, 25000] / Observed [24500, 25500]` (= 49.0% / 51.0%) | Replace placeholder with real numbers. The «46.8%» framing is mathematically inconsistent at typical experiment scales — drop it. |
| 90s @ 31-38s | sequential design with «mSPRT family» mention | actual product uses **O'Brien-Fleming** with 4 looks: Z = 4.05 / 2.86 / 2.34 / 2.02 | Update overlay text to «O'Brien-Fleming. 4 looks. α-spending.» mSPRT is a different family — the product doesn't claim it. |
| 90s @ 24-31s | wizard fields show generic | actual: baseline `0.042`, MDE `7%`, alpha `0.05`, power `0.8` | Use these specific numbers in callouts |

After patches, the script's specific number callouts match what will actually appear on screen during recording — no «theatre», pure real-product capture per the user's standing principle.
