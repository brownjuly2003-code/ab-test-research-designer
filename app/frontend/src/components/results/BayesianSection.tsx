import { Suspense, lazy } from "react";

import { useDraftStore } from "../../stores/draftStore";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Skeleton from "../Skeleton";
import { getDisplayedAnalysis } from "./resultsShared";
import { resolveMetricType } from "./sensitivityShared";

const PosteriorPlot = lazy(() => import("../PosteriorPlot"));

function normalQuantile(probability: number): number {
  const a = [-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924];
  const b = [-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857];
  const c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878];
  const d = [0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742];
  const plow = 0.02425;
  const phigh = 1 - plow;

  if (probability <= 0) {
    return Number.NEGATIVE_INFINITY;
  }
  if (probability >= 1) {
    return Number.POSITIVE_INFINITY;
  }

  if (probability < plow) {
    const q = Math.sqrt(-2 * Math.log(probability));
    const numerator = ((((((c[0] * q) + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]);
    const denominator = (((((d[0] * q) + d[1]) * q + d[2]) * q + d[3]) * q + 1);
    return numerator / denominator;
  }

  if (probability > phigh) {
    const q = Math.sqrt(-2 * Math.log(1 - probability));
    const numerator = ((((((c[0] * q) + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]);
    const denominator = (((((d[0] * q) + d[1]) * q + d[2]) * q + d[3]) * q + 1);
    return -(numerator / denominator);
  }

  const q = probability - 0.5;
  const r = q * q;
  const numerator = ((((((a[0] * r) + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q;
  const denominator = ((((((b[0] * r) + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r) + 1;
  return numerator / denominator;
}

function parsePrecisionFromNote(note: string | null | undefined): number | null {
  if (typeof note !== "string") {
    return null;
  }

  const match = /half-width <=\s*([0-9]+(?:\.[0-9]+)?)/i.exec(note);
  return match ? Number(match[1]) : null;
}

function clampInterval(
  lower: number,
  upper: number,
  metricType: "binary" | "continuous"
) {
  if (metricType !== "binary") {
    return { lower, upper };
  }

  return {
    lower: Math.max(0, lower),
    upper: Math.min(1, upper)
  };
}

function formatPrecision(value: number, metricType: "binary" | "continuous"): string {
  return metricType === "binary" ? `${value} pp` : `${value} units`;
}

export default function BayesianSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const analysisMode = useDraftStore((state) => state.draft.constraints.analysis_mode ?? "frequentist");
  const fallbackPrecision = useDraftStore((state) => state.draft.constraints.desired_precision ?? null);
  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryAnalysis, analysisResult);

  if (!displayedAnalysis?.report) {
    return null;
  }

  const metricType = resolveMetricType(displayedAnalysis.calculations.calculation_summary.metric_type);
  const bayesianSampleSize = displayedAnalysis.calculations.bayesian_sample_size_per_variant ?? null;
  const credibility = displayedAnalysis.calculations.bayesian_credibility ?? null;
  const note = displayedAnalysis.calculations.bayesian_note ?? null;
  const isBayesianAnalysis = selectedHistoryAnalysis
    ? bayesianSampleSize !== null || credibility !== null || Boolean(note)
    : analysisMode === "bayesian";

  if (!isBayesianAnalysis) {
    return null;
  }

  const precisionValue = parsePrecisionFromNote(note) ?? fallbackPrecision;
  const posteriorMean = displayedAnalysis.calculations.calculation_summary.baseline_value;

  if (bayesianSampleSize === null || credibility === null || precisionValue === null) {
    return (
      <div className="card">
        <h3>Bayesian posterior</h3>
        <p className="muted">{note ?? "Bayesian posterior inputs are unavailable for this analysis."}</p>
      </div>
    );
  }

  const intervalHalfWidth = metricType === "binary" ? precisionValue / 100 : precisionValue;
  const zScore = normalQuantile(1 - (1 - credibility) / 2);
  const posteriorStd = intervalHalfWidth / zScore;
  const interval = clampInterval(
    posteriorMean - intervalHalfWidth,
    posteriorMean + intervalHalfWidth,
    metricType
  );

  return (
    <div className="card">
      <div className="section-heading">
        <div>
          <h3>Bayesian posterior</h3>
          <p className="muted">
            Target sample size: <strong>{bayesianSampleSize.toLocaleString()}</strong> per variant at {Math.round(credibility * 100)}%
            {" "}credibility and {formatPrecision(precisionValue, metricType)} interval half-width.
          </p>
        </div>
      </div>
      {note ? <p className="muted" style={{ marginTop: "12px" }}>{note}</p> : null}
      <div style={{ marginTop: "16px" }}>
        <Suspense fallback={<Skeleton height="260px" />}>
          <PosteriorPlot
            posteriorMean={posteriorMean}
            posteriorStd={posteriorStd}
            credibilityInterval={{ lower: interval.lower, upper: interval.upper, level: credibility }}
            metricType={metricType}
          />
        </Suspense>
      </div>
    </div>
  );
}
