import type { ResultsRequestPayload } from "../../lib/experiment";

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

export type ActualResultsState = {
  binary: BinaryResultsForm;
  continuous: ContinuousResultsForm;
};

export function resolveObservedMetricType(metricType: string): "binary" | "continuous" {
  return metricType === "continuous" ? "continuous" : "binary";
}

export function formatObservedValue(
  value: number,
  metricType: "binary" | "continuous",
  options: { signed?: boolean; withUnit?: boolean } = {}
): string {
  const signedPrefix = options.signed && value > 0 ? "+" : "";
  const unit = options.withUnit ? (metricType === "binary" ? " pp" : "") : "";
  return `${signedPrefix}${value.toFixed(4)}${unit}`;
}

function toFieldValue(value: number | undefined): string {
  return value === undefined ? "" : String(value);
}

export function buildActualResultsState(
  metricType: "binary" | "continuous",
  alpha: number,
  request: ResultsRequestPayload | null
): ActualResultsState {
  const defaultAlpha = String(request?.metric_type === metricType
    ? request.metric_type === "binary"
      ? request.binary?.alpha ?? alpha
      : request.continuous?.alpha ?? alpha
    : alpha
  );

  return {
    binary: {
      control_conversions:
        request?.metric_type === "binary" ? toFieldValue(request.binary?.control_conversions) : "",
      control_users:
        request?.metric_type === "binary" ? toFieldValue(request.binary?.control_users) : "",
      treatment_conversions:
        request?.metric_type === "binary" ? toFieldValue(request.binary?.treatment_conversions) : "",
      treatment_users:
        request?.metric_type === "binary" ? toFieldValue(request.binary?.treatment_users) : "",
      alpha: request?.metric_type === "binary" ? toFieldValue(request.binary?.alpha ?? alpha) : defaultAlpha
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
    }
  };
}

export function buildResultsRequest(
  metricType: "binary" | "continuous",
  form: ActualResultsState
): ResultsRequestPayload | null {
  if (metricType === "binary") {
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
      metric_type: "binary",
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
