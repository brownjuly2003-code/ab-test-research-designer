import type { ResultsRequestPayload } from "../../lib/experiment";

// The observed-results form supports the two planned metric types plus alternative tests offered on
// the same data — Mann–Whitney (non-parametric), bootstrap/permutation, quantile treatment effect,
// Yuen–Welch trimmed-means (robust) and TOST equivalence for continuous, Fisher's exact and Boschloo's
// unconditional exact for binary — and a plan-independent Poisson rate test ("count") for
// event-over-exposure data.
export type ObservedMetricType = "binary" | "continuous" | "equivalence" | "mann_whitney" | "bootstrap" | "quantile" | "trimmed_t" | "fisher_exact" | "boschloo_exact" | "count";

// The local toggle selection: "parametric" is the default analysis (t-test / z-test); the rest are
// the alternative tests offered on the same data per base metric type.
export type ObservedTestSelection = "parametric" | "mann_whitney" | "bootstrap" | "quantile" | "trimmed_t" | "equivalence" | "fisher_exact" | "boschloo_exact" | "count";

// The plan's underlying metric type, as resolved from the calculation summary (see
// resolveObservedMetricType). Ratio has no dedicated post-hoc analyzer and is handled specially.
export type ObservedBaseMetricType = "binary" | "continuous" | "ratio";

// Which raw-input form an analyzer reads. Fisher's exact reuses the binary 2x2 form; the rank-based
// tests share the ranked raw-sample form; TOST reuses the continuous summary form plus a margin.
export type ObservedFormKind = "binary" | "continuous" | "equivalence" | "ranked" | "count";

export type BinaryResultsForm = {
  control_conversions: string;
  control_users: string;
  treatment_conversions: string;
  treatment_users: string;
  alpha: string;
};

export type ContinuousResultsForm = {
  control_mean: string;
  control_std: string;
  control_n: string;
  treatment_mean: string;
  treatment_std: string;
  treatment_n: string;
  alpha: string;
  // Only used by the TOST equivalence test (the tolerated mean difference, ±margin); the difference
  // t-test and the non-parametric tests ignore it.
  equivalence_margin: string;
};

// Raw per-unit samples are entered as free text (one value per line, or comma/space separated) and
// parsed at submit time; the rank-sum test needs the observations, not summary statistics. The
// quantile field is only used by the quantile treatment-effect test (which quantile to compare) and
// the trim field only by the Yuen–Welch trimmed-means test (the tail fraction trimmed from each end).
export type RankedResultsForm = {
  control_values: string;
  treatment_values: string;
  alpha: string;
  quantile: string;
  trim: string;
};

// Counts of events accrued over an amount of exposure, for the Poisson rate test.
export type CountResultsForm = {
  control_events: string;
  control_exposure: string;
  treatment_events: string;
  treatment_exposure: string;
  alpha: string;
};

export type ActualResultsState = {
  binary: BinaryResultsForm;
  continuous: ContinuousResultsForm;
  ranked: RankedResultsForm;
  count: CountResultsForm;
};

// Ratio plans (metric_type "ratio") have no dedicated post-hoc analyzer — they are only analyzed via
// the live-stats delta method. Surfacing "ratio" here (instead of silently folding it into "binary")
// lets the caller show a disclaimer and offer a conscious approximation (continuous or count) rather
// than rendering the wrong 2x2-conversions form without warning.
export function resolveObservedMetricType(metricType: string): ObservedBaseMetricType {
  if (metricType === "continuous") return "continuous";
  if (metricType === "ratio") return "ratio";
  return "binary";
}

// --- Test registry -------------------------------------------------------------------------------
//
// A single source of truth for the post-hoc test toggle. Previously three parallel ternary ladders
// (toggle → effective metric type, restore → toggle, toggle → state metric type) each grew by a
// branch with every new analyzer; adding a test meant editing all three plus the button list and the
// hint list, and the ladders were becoming unreadable (audit finding 5.5). Now every analyzer is one
// row here and all of those mappings are derived from it — adding an analyzer is a single entry (plus
// its label/hint i18n keys and, if it needs a new input form, a FORM_BY_METRIC_TYPE row).

// The default ("parametric") test offered for each base plan: the normal-approximation analysis that
// matches the plan — the z-test for binary, the difference t-test for continuous, and a conscious
// continuous approximation for ratio (which has no dedicated post-hoc analyzer, only the live-stats
// delta method). Its label and hint vary by base, so they live here rather than on a toggle value.
type BaseDefaultDescriptor = { metricType: ObservedMetricType; labelKey: string; hintKey: string };

const BASE_DEFAULT_TESTS: Record<ObservedBaseMetricType, BaseDefaultDescriptor> = {
  binary: {
    metricType: "binary",
    labelKey: "results.observedResults.testType.zTest",
    hintKey: "results.observedResults.testType.fisherHint"
  },
  continuous: {
    metricType: "continuous",
    labelKey: "results.observedResults.testType.parametric",
    hintKey: "results.observedResults.testType.hint"
  },
  ratio: {
    metricType: "continuous",
    labelKey: "results.observedResults.testType.continuousApprox",
    hintKey: "results.observedResults.testType.ratioContinuousHint"
  }
};

// Every alternative test offered alongside the default, in toggle display order. `availableFor` lists
// the base plans whose toggle shows the option (count is plan-independent, so all three). Each option
// resolves to the analyzer of the same name.
type AlternativeTestDescriptor = {
  test: Exclude<ObservedTestSelection, "parametric">;
  metricType: ObservedMetricType;
  availableFor: readonly ObservedBaseMetricType[];
  labelKey: string;
  hintKey: string;
};

const ALTERNATIVE_TESTS: readonly AlternativeTestDescriptor[] = [
  { test: "fisher_exact", metricType: "fisher_exact", availableFor: ["binary"], labelKey: "results.observedResults.testType.fisherExact", hintKey: "results.observedResults.testType.fisherHint" },
  { test: "boschloo_exact", metricType: "boschloo_exact", availableFor: ["binary"], labelKey: "results.observedResults.testType.boschloo", hintKey: "results.observedResults.testType.boschlooHint" },
  { test: "mann_whitney", metricType: "mann_whitney", availableFor: ["continuous"], labelKey: "results.observedResults.testType.mannWhitney", hintKey: "results.observedResults.testType.hint" },
  { test: "bootstrap", metricType: "bootstrap", availableFor: ["continuous"], labelKey: "results.observedResults.testType.bootstrap", hintKey: "results.observedResults.testType.bootstrapHint" },
  { test: "quantile", metricType: "quantile", availableFor: ["continuous"], labelKey: "results.observedResults.testType.quantile", hintKey: "results.observedResults.testType.quantileHint" },
  { test: "trimmed_t", metricType: "trimmed_t", availableFor: ["continuous"], labelKey: "results.observedResults.testType.trimmedT", hintKey: "results.observedResults.testType.trimmedTHint" },
  { test: "equivalence", metricType: "equivalence", availableFor: ["continuous"], labelKey: "results.observedResults.testType.equivalence", hintKey: "results.observedResults.testType.equivalenceHint" },
  { test: "count", metricType: "count", availableFor: ["binary", "continuous", "ratio"], labelKey: "results.observedResults.testType.rate", hintKey: "results.observedResults.testType.rateHint" }
];

// The input form each analyzer reads. Consumed by the view to pick which fields to render.
const FORM_BY_METRIC_TYPE: Record<ObservedMetricType, ObservedFormKind> = {
  binary: "binary",
  fisher_exact: "binary",
  boschloo_exact: "binary",
  continuous: "continuous",
  equivalence: "equivalence",
  mann_whitney: "ranked",
  bootstrap: "ranked",
  quantile: "ranked",
  trimmed_t: "ranked",
  count: "count"
};

export type ObservedTestButton = { test: ObservedTestSelection; labelKey: string };

// The toggle buttons shown for a base plan, in display order (default first, then its alternatives).
export function observedTestButtons(base: ObservedBaseMetricType): ObservedTestButton[] {
  const buttons: ObservedTestButton[] = [{ test: "parametric", labelKey: BASE_DEFAULT_TESTS[base].labelKey }];
  for (const alt of ALTERNATIVE_TESTS) {
    if (alt.availableFor.includes(base)) {
      buttons.push({ test: alt.test, labelKey: alt.labelKey });
    }
  }
  return buttons;
}

// The analyzer metric_type a toggle selection runs on a given base plan. An alternative that is not
// offered for the base falls back to the base default (mirrors the old guard where e.g. mann_whitney
// on a binary plan resolved to binary).
export function resolveEffectiveMetricType(base: ObservedBaseMetricType, test: ObservedTestSelection): ObservedMetricType {
  if (test !== "parametric") {
    const alt = ALTERNATIVE_TESTS.find((option) => option.test === test);
    if (alt && alt.availableFor.includes(base)) {
      return alt.metricType;
    }
  }
  return BASE_DEFAULT_TESTS[base].metricType;
}

// The analyzer metric_types that can be restored for a base plan (default plus its alternatives).
export function supportedObservedMetricTypes(base: ObservedBaseMetricType): ObservedMetricType[] {
  return observedTestButtons(base).map((button) => resolveEffectiveMetricType(base, button.test));
}

// Reverse mapping: turn a persisted analyzer metric_type back into the toggle selection for a base
// plan. A type that no alternative offers for this base (including the base's own default type)
// restores to the default "parametric" toggle.
export function restoreObservedTest(base: ObservedBaseMetricType, persistedType: ObservedMetricType | undefined): ObservedTestSelection {
  if (!persistedType) {
    return "parametric";
  }
  const alt = ALTERNATIVE_TESTS.find((option) => option.metricType === persistedType && option.availableFor.includes(base));
  return alt ? alt.test : "parametric";
}

// The i18n key of the hint shown for the current toggle selection on a base plan.
export function observedTestHintKey(base: ObservedBaseMetricType, test: ObservedTestSelection): string {
  if (test !== "parametric") {
    const alt = ALTERNATIVE_TESTS.find((option) => option.test === test);
    if (alt) {
      return alt.hintKey;
    }
  }
  return BASE_DEFAULT_TESTS[base].hintKey;
}

// The input form an analyzer reads (which fields the view renders).
export function observedFormKind(metricType: ObservedMetricType): ObservedFormKind {
  return FORM_BY_METRIC_TYPE[metricType];
}

// --- "Which test should I use?" chooser ----------------------------------------------------------
//
// A guided selector (audit finding 6.2 §7): at seven continuous options the flat toggle gives no
// guidance, so a few questions map to a recommendation. The questions and the recommendation are
// pure data/logic here (i18n keys + a decision function) so they can be unit-tested and rendered by
// TestChooser without duplicating the branching.

export type ObservedChooserAnswers = {
  // continuous questions
  goal?: "difference" | "equivalence";
  distribution?: "normal" | "skew_outliers" | "small_nonnormal";
  focus?: "mean" | "percentile";
  // binary question
  binarySmall?: "yes" | "no";
};

export type ObservedChooserQuestion = {
  id: keyof ObservedChooserAnswers;
  labelKey: string;
  options: readonly { value: string; labelKey: string }[];
};

const CHOOSER_NS = "results.observedResults.chooser.questions";

const CONTINUOUS_QUESTIONS: readonly ObservedChooserQuestion[] = [
  {
    id: "goal",
    labelKey: `${CHOOSER_NS}.goal.label`,
    options: [
      { value: "difference", labelKey: `${CHOOSER_NS}.goal.options.difference` },
      { value: "equivalence", labelKey: `${CHOOSER_NS}.goal.options.equivalence` }
    ]
  },
  {
    id: "distribution",
    labelKey: `${CHOOSER_NS}.distribution.label`,
    options: [
      { value: "normal", labelKey: `${CHOOSER_NS}.distribution.options.normal` },
      { value: "skew_outliers", labelKey: `${CHOOSER_NS}.distribution.options.skew_outliers` },
      { value: "small_nonnormal", labelKey: `${CHOOSER_NS}.distribution.options.small_nonnormal` }
    ]
  },
  {
    id: "focus",
    labelKey: `${CHOOSER_NS}.focus.label`,
    options: [
      { value: "mean", labelKey: `${CHOOSER_NS}.focus.options.mean` },
      { value: "percentile", labelKey: `${CHOOSER_NS}.focus.options.percentile` }
    ]
  }
];

const BINARY_QUESTIONS: readonly ObservedChooserQuestion[] = [
  {
    id: "binarySmall",
    labelKey: `${CHOOSER_NS}.binarySmall.label`,
    options: [
      { value: "yes", labelKey: `${CHOOSER_NS}.binarySmall.options.yes` },
      { value: "no", labelKey: `${CHOOSER_NS}.binarySmall.options.no` }
    ]
  }
];

// The chooser questions for a base plan. Ratio has only two options that need different data, so it
// gets no chooser (the ratio disclaimer already explains the situation).
export function observedChooserQuestions(base: ObservedBaseMetricType): readonly ObservedChooserQuestion[] {
  if (base === "continuous") return CONTINUOUS_QUESTIONS;
  if (base === "binary") return BINARY_QUESTIONS;
  return [];
}

export type ObservedChooserRecommendation = { test: ObservedTestSelection; rationaleKey: string };

const RATIONALE_NS = "results.observedResults.chooser.rationale";

// Map the answers to a recommended toggle selection. Returns null until every question for the base
// is answered. The order of the continuous rules is deliberate: goal (equivalence overrides all),
// then focus on a tail, then distribution shape.
export function recommendObservedTest(
  base: ObservedBaseMetricType,
  answers: ObservedChooserAnswers
): ObservedChooserRecommendation | null {
  if (base === "binary") {
    if (!answers.binarySmall) return null;
    return answers.binarySmall === "yes"
      ? { test: "fisher_exact", rationaleKey: `${RATIONALE_NS}.fisher_exact` }
      : { test: "parametric", rationaleKey: `${RATIONALE_NS}.zTest` };
  }
  if (base === "continuous") {
    if (!answers.goal || !answers.distribution || !answers.focus) return null;
    if (answers.goal === "equivalence") return { test: "equivalence", rationaleKey: `${RATIONALE_NS}.equivalence` };
    if (answers.focus === "percentile") return { test: "quantile", rationaleKey: `${RATIONALE_NS}.quantile` };
    if (answers.distribution === "skew_outliers") return { test: "trimmed_t", rationaleKey: `${RATIONALE_NS}.trimmed_t` };
    if (answers.distribution === "small_nonnormal") return { test: "mann_whitney", rationaleKey: `${RATIONALE_NS}.mann_whitney` };
    return { test: "parametric", rationaleKey: `${RATIONALE_NS}.parametric` };
  }
  return null;
}

// The label key for a toggle selection on a base plan (default label varies by base). Used by the
// chooser to name its recommendation with the same wording as the toggle button.
export function observedTestLabelKey(base: ObservedBaseMetricType, test: ObservedTestSelection): string {
  if (test !== "parametric") {
    const alt = ALTERNATIVE_TESTS.find((option) => option.test === test);
    if (alt) return alt.labelKey;
  }
  return BASE_DEFAULT_TESTS[base].labelKey;
}

export function formatObservedValue(
  value: number,
  metricType: ObservedMetricType,
  options: { signed?: boolean; withUnit?: boolean } = {}
): string {
  const signedPrefix = options.signed && value > 0 ? "+" : "";
  // Binary, Fisher's exact and Boschloo's exact all report a proportion difference in percentage
  // points; they share the "binary" input form, so key the unit off that predicate.
  const usesPercentagePoints = observedFormKind(metricType) === "binary";
  const unit = options.withUnit ? (usesPercentagePoints ? " pp" : "") : "";
  return `${signedPrefix}${value.toFixed(4)}${unit}`;
}

// Parse free-text raw samples into finite numbers, splitting on commas, whitespace and newlines.
// Returns null when fewer than two valid numbers are present or any token is not a finite number,
// mirroring the backend ObservedResultsRanked validation (min length 2, finite values).
export function parseSampleValues(text: string): number[] | null {
  const tokens = text.split(/[\s,;]+/).filter((token) => token.length > 0);
  if (tokens.length < 2) {
    return null;
  }
  const values: number[] = [];
  for (const token of tokens) {
    const value = Number(token);
    if (!Number.isFinite(value)) {
      return null;
    }
    values.push(value);
  }
  return values;
}

function toFieldValue(value: number | undefined): string {
  return value === undefined ? "" : String(value);
}

export function buildActualResultsState(
  metricType: ObservedMetricType,
  alpha: number,
  request: ResultsRequestPayload | null
): ActualResultsState {
  // Fisher's exact and Boschloo's exact share the binary 2x2 input, so all three read request.binary.
  const requestUsesBinaryForm =
    request?.metric_type === "binary" ||
    request?.metric_type === "fisher_exact" ||
    request?.metric_type === "boschloo_exact";
  // Mann–Whitney, bootstrap/permutation, the quantile treatment effect and the Yuen–Welch
  // trimmed-means test all share the ranked raw-sample input.
  const requestUsesRankedForm =
    request?.metric_type === "mann_whitney" ||
    request?.metric_type === "bootstrap" ||
    request?.metric_type === "quantile" ||
    request?.metric_type === "trimmed_t";
  // The difference t-test and the TOST equivalence test both read the continuous summary statistics.
  const requestUsesContinuousForm =
    request?.metric_type === "continuous" || request?.metric_type === "equivalence";
  const matchingAlpha =
    request?.metric_type === metricType
      ? metricType === "binary" || metricType === "fisher_exact" || metricType === "boschloo_exact"
        ? request.binary?.alpha
        : metricType === "continuous" || metricType === "equivalence"
          ? request.continuous?.alpha
          : metricType === "count"
            ? request.count?.alpha
            : request.ranked?.alpha
      : undefined;
  const defaultAlpha = String(matchingAlpha ?? alpha);

  return {
    binary: {
      control_conversions:
        requestUsesBinaryForm ? toFieldValue(request?.binary?.control_conversions) : "",
      control_users:
        requestUsesBinaryForm ? toFieldValue(request?.binary?.control_users) : "",
      treatment_conversions:
        requestUsesBinaryForm ? toFieldValue(request?.binary?.treatment_conversions) : "",
      treatment_users:
        requestUsesBinaryForm ? toFieldValue(request?.binary?.treatment_users) : "",
      alpha: requestUsesBinaryForm ? toFieldValue(request?.binary?.alpha ?? alpha) : defaultAlpha
    },
    continuous: {
      control_mean:
        requestUsesContinuousForm ? toFieldValue(request?.continuous?.control_mean) : "",
      control_std:
        requestUsesContinuousForm ? toFieldValue(request?.continuous?.control_std) : "",
      control_n:
        requestUsesContinuousForm ? toFieldValue(request?.continuous?.control_n) : "",
      treatment_mean:
        requestUsesContinuousForm ? toFieldValue(request?.continuous?.treatment_mean) : "",
      treatment_std:
        requestUsesContinuousForm ? toFieldValue(request?.continuous?.treatment_std) : "",
      treatment_n:
        requestUsesContinuousForm ? toFieldValue(request?.continuous?.treatment_n) : "",
      alpha: requestUsesContinuousForm ? toFieldValue(request?.continuous?.alpha ?? alpha) : defaultAlpha,
      equivalence_margin:
        request?.metric_type === "equivalence"
          ? toFieldValue(request?.continuous?.equivalence_margin ?? undefined)
          : ""
    },
    ranked: {
      control_values:
        requestUsesRankedForm ? (request?.ranked?.control_values ?? []).join("\n") : "",
      treatment_values:
        requestUsesRankedForm ? (request?.ranked?.treatment_values ?? []).join("\n") : "",
      alpha: requestUsesRankedForm ? toFieldValue(request?.ranked?.alpha ?? alpha) : defaultAlpha,
      quantile:
        request?.metric_type === "quantile" ? toFieldValue(request?.ranked?.quantile ?? 0.5) : "0.5",
      trim:
        request?.metric_type === "trimmed_t" ? toFieldValue(request?.ranked?.trim ?? 0.2) : "0.2"
    },
    count: {
      control_events: request?.metric_type === "count" ? toFieldValue(request.count?.control_events) : "",
      control_exposure: request?.metric_type === "count" ? toFieldValue(request.count?.control_exposure) : "",
      treatment_events: request?.metric_type === "count" ? toFieldValue(request.count?.treatment_events) : "",
      treatment_exposure: request?.metric_type === "count" ? toFieldValue(request.count?.treatment_exposure) : "",
      alpha: request?.metric_type === "count" ? toFieldValue(request.count?.alpha ?? alpha) : defaultAlpha
    }
  };
}

// Parse and validate the shared continuous summary-statistics form (used by the difference t-test
// and the TOST equivalence test). Returns null when any field is blank or out of range, mirroring
// the backend ObservedResultsContinuous bounds.
function parseContinuousForm(
  form: ContinuousResultsForm
): { control_mean: number; control_std: number; control_n: number; treatment_mean: number; treatment_std: number; treatment_n: number; alpha: number } | null {
  if (
    form.control_mean.trim() === "" ||
    form.control_std.trim() === "" ||
    form.control_n.trim() === "" ||
    form.treatment_mean.trim() === "" ||
    form.treatment_std.trim() === "" ||
    form.treatment_n.trim() === "" ||
    form.alpha.trim() === ""
  ) {
    return null;
  }
  const continuous = {
    control_mean: Number(form.control_mean),
    control_std: Number(form.control_std),
    control_n: Number(form.control_n),
    treatment_mean: Number(form.treatment_mean),
    treatment_std: Number(form.treatment_std),
    treatment_n: Number(form.treatment_n),
    alpha: Number(form.alpha)
  };
  if (
    !Number.isFinite(continuous.control_mean) ||
    !(continuous.control_std > 0) ||
    !Number.isInteger(continuous.control_n) ||
    !Number.isFinite(continuous.treatment_mean) ||
    !(continuous.treatment_std > 0) ||
    !Number.isInteger(continuous.treatment_n) ||
    continuous.control_n < 1 ||
    continuous.treatment_n < 1 ||
    !(continuous.alpha >= 0.001 && continuous.alpha <= 0.1)
  ) {
    return null;
  }
  return continuous;
}

export function buildResultsRequest(
  metricType: ObservedMetricType,
  form: ActualResultsState
): ResultsRequestPayload | null {
  // Mann–Whitney, bootstrap/permutation, the quantile treatment effect and the Yuen–Welch
  // trimmed-means test all consume the raw per-unit samples (ranked input) and share the same parse +
  // bounds validation; only the metric_type tag differs. The quantile test additionally carries which
  // quantile to compare, and the trimmed-means test the tail fraction to trim.
  if (metricType === "mann_whitney" || metricType === "bootstrap" || metricType === "quantile" || metricType === "trimmed_t") {
    if (form.ranked.alpha.trim() === "") {
      return null;
    }
    const control_values = parseSampleValues(form.ranked.control_values);
    const treatment_values = parseSampleValues(form.ranked.treatment_values);
    const alpha = Number(form.ranked.alpha);
    if (
      control_values === null ||
      treatment_values === null ||
      control_values.length > 1000 ||
      treatment_values.length > 1000 ||
      !(alpha >= 0.001 && alpha <= 0.1)
    ) {
      return null;
    }
    if (metricType === "quantile") {
      const quantile = Number(form.ranked.quantile);
      if (form.ranked.quantile.trim() === "" || !(quantile > 0 && quantile < 1)) {
        return null;
      }
      return {
        metric_type: "quantile",
        ranked: { control_values, treatment_values, alpha, quantile }
      };
    }
    if (metricType === "trimmed_t") {
      const trim = Number(form.ranked.trim);
      if (form.ranked.trim.trim() === "" || !(trim >= 0 && trim < 0.5)) {
        return null;
      }
      return {
        metric_type: "trimmed_t",
        ranked: { control_values, treatment_values, alpha, trim }
      };
    }
    return {
      metric_type: metricType,
      ranked: { control_values, treatment_values, alpha }
    };
  }

  // Fisher's exact reuses the binary 2x2 input and validation; only the metric_type tag differs.
  if (metricType === "count") {
    if (
      form.count.control_events.trim() === "" ||
      form.count.control_exposure.trim() === "" ||
      form.count.treatment_events.trim() === "" ||
      form.count.treatment_exposure.trim() === "" ||
      form.count.alpha.trim() === ""
    ) {
      return null;
    }

    const count = {
      control_events: Number(form.count.control_events),
      control_exposure: Number(form.count.control_exposure),
      treatment_events: Number(form.count.treatment_events),
      treatment_exposure: Number(form.count.treatment_exposure),
      alpha: Number(form.count.alpha)
    };

    if (
      !Number.isInteger(count.control_events) ||
      !Number.isInteger(count.treatment_events) ||
      count.control_events < 0 ||
      count.treatment_events < 0 ||
      !(count.control_exposure > 0) ||
      !(count.treatment_exposure > 0) ||
      !Number.isFinite(count.control_exposure) ||
      !Number.isFinite(count.treatment_exposure) ||
      !(count.alpha >= 0.001 && count.alpha <= 0.1)
    ) {
      return null;
    }

    return {
      metric_type: "count",
      count
    };
  }

  if (metricType === "binary" || metricType === "fisher_exact" || metricType === "boschloo_exact") {
    if (
      form.binary.control_conversions.trim() === "" ||
      form.binary.control_users.trim() === "" ||
      form.binary.treatment_conversions.trim() === "" ||
      form.binary.treatment_users.trim() === "" ||
      form.binary.alpha.trim() === ""
    ) {
      return null;
    }

    const binary = {
      control_conversions: Number(form.binary.control_conversions),
      control_users: Number(form.binary.control_users),
      treatment_conversions: Number(form.binary.treatment_conversions),
      treatment_users: Number(form.binary.treatment_users),
      alpha: Number(form.binary.alpha)
    };

    if (
      !Number.isInteger(binary.control_conversions) ||
      !Number.isInteger(binary.control_users) ||
      !Number.isInteger(binary.treatment_conversions) ||
      !Number.isInteger(binary.treatment_users) ||
      binary.control_conversions < 0 ||
      binary.control_users < 1 ||
      binary.treatment_conversions < 0 ||
      binary.treatment_users < 1 ||
      binary.control_conversions > binary.control_users ||
      binary.treatment_conversions > binary.treatment_users ||
      !(binary.alpha >= 0.001 && binary.alpha <= 0.1)
    ) {
      return null;
    }

    return {
      metric_type: metricType,
      binary
    };
  }

  // TOST equivalence reuses the continuous summary statistics plus a positive equivalence margin.
  if (metricType === "equivalence") {
    const continuous = parseContinuousForm(form.continuous);
    const equivalence_margin = Number(form.continuous.equivalence_margin);
    if (
      continuous === null ||
      form.continuous.equivalence_margin.trim() === "" ||
      !Number.isFinite(equivalence_margin) ||
      !(equivalence_margin > 0)
    ) {
      return null;
    }
    return {
      metric_type: "equivalence",
      continuous: { ...continuous, equivalence_margin }
    };
  }

  const continuous = parseContinuousForm(form.continuous);
  if (continuous === null) {
    return null;
  }

  return {
    metric_type: "continuous",
    continuous
  };
}
