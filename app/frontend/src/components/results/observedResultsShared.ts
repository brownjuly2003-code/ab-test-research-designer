import type { ResultsRequestPayload } from "../../lib/experiment";

// The observed-results form supports the two planned metric types plus alternative tests offered on
// the same data — Mann–Whitney (non-parametric), bootstrap/permutation and quantile treatment effect
// for continuous, Fisher's exact for binary — and a plan-independent Poisson rate test ("count") for
// event-over-exposure data.
export type ObservedMetricType = "binary" | "continuous" | "mann_whitney" | "bootstrap" | "quantile" | "fisher_exact" | "count";

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
};

// Raw per-unit samples are entered as free text (one value per line, or comma/space separated) and
// parsed at submit time; the rank-sum test needs the observations, not summary statistics. The
// quantile field is only used by the quantile treatment-effect test (which quantile to compare).
export type RankedResultsForm = {
  control_values: string;
  treatment_values: string;
  alpha: string;
  quantile: string;
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

export function resolveObservedMetricType(metricType: string): "binary" | "continuous" {
  return metricType === "continuous" ? "continuous" : "binary";
}

export function formatObservedValue(
  value: number,
  metricType: ObservedMetricType,
  options: { signed?: boolean; withUnit?: boolean } = {}
): string {
  const signedPrefix = options.signed && value > 0 ? "+" : "";
  const usesPercentagePoints = metricType === "binary" || metricType === "fisher_exact";
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
  // Fisher's exact shares the binary 2x2 input, so both metric types read from request.binary.
  const requestUsesBinaryForm =
    request?.metric_type === "binary" || request?.metric_type === "fisher_exact";
  // Mann–Whitney, bootstrap/permutation and the quantile treatment effect share the ranked
  // raw-sample input.
  const requestUsesRankedForm =
    request?.metric_type === "mann_whitney" ||
    request?.metric_type === "bootstrap" ||
    request?.metric_type === "quantile";
  const matchingAlpha =
    request?.metric_type === metricType
      ? metricType === "binary" || metricType === "fisher_exact"
        ? request.binary?.alpha
        : metricType === "continuous"
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
        request?.metric_type === "continuous" ? toFieldValue(request.continuous?.control_mean) : "",
      control_std:
        request?.metric_type === "continuous" ? toFieldValue(request.continuous?.control_std) : "",
      control_n:
        request?.metric_type === "continuous" ? toFieldValue(request.continuous?.control_n) : "",
      treatment_mean:
        request?.metric_type === "continuous" ? toFieldValue(request.continuous?.treatment_mean) : "",
      treatment_std:
        request?.metric_type === "continuous" ? toFieldValue(request.continuous?.treatment_std) : "",
      treatment_n:
        request?.metric_type === "continuous" ? toFieldValue(request.continuous?.treatment_n) : "",
      alpha: request?.metric_type === "continuous" ? toFieldValue(request.continuous?.alpha ?? alpha) : defaultAlpha
    },
    ranked: {
      control_values:
        requestUsesRankedForm ? (request?.ranked?.control_values ?? []).join("\n") : "",
      treatment_values:
        requestUsesRankedForm ? (request?.ranked?.treatment_values ?? []).join("\n") : "",
      alpha: requestUsesRankedForm ? toFieldValue(request?.ranked?.alpha ?? alpha) : defaultAlpha,
      quantile:
        request?.metric_type === "quantile" ? toFieldValue(request?.ranked?.quantile ?? 0.5) : "0.5"
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

export function buildResultsRequest(
  metricType: ObservedMetricType,
  form: ActualResultsState
): ResultsRequestPayload | null {
  // Mann–Whitney, bootstrap/permutation and the quantile treatment effect all consume the raw
  // per-unit samples (ranked input) and share the same parse + bounds validation; only the
  // metric_type tag differs. The quantile test additionally carries which quantile to compare.
  if (metricType === "mann_whitney" || metricType === "bootstrap" || metricType === "quantile") {
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

  if (metricType === "binary" || metricType === "fisher_exact") {
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

  if (
    form.continuous.control_mean.trim() === "" ||
    form.continuous.control_std.trim() === "" ||
    form.continuous.control_n.trim() === "" ||
    form.continuous.treatment_mean.trim() === "" ||
    form.continuous.treatment_std.trim() === "" ||
    form.continuous.treatment_n.trim() === "" ||
    form.continuous.alpha.trim() === ""
  ) {
    return null;
  }

  const continuous = {
    control_mean: Number(form.continuous.control_mean),
    control_std: Number(form.continuous.control_std),
    control_n: Number(form.continuous.control_n),
    treatment_mean: Number(form.continuous.treatment_mean),
    treatment_std: Number(form.continuous.treatment_std),
    treatment_n: Number(form.continuous.treatment_n),
    alpha: Number(form.continuous.alpha)
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

  return {
    metric_type: "continuous",
    continuous
  };
}
