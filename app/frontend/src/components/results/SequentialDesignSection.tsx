import { Suspense, lazy } from "react";

import { t } from "../../i18n";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import Skeleton from "../Skeleton";

const SequentialBoundaryChart = lazy(() => import("../SequentialBoundaryChart"));

type SequentialBoundary = {
  alpha_spent: number;
  info_fraction: number;
  is_final: boolean;
  look: number;
  lower_boundary_z: number;
  sample_size_cumulative: number;
  upper_boundary_z: number;
};

function normalizeSequentialBoundary(boundary: Record<string, unknown>, index: number, total: number): SequentialBoundary {
  const look = Number(boundary.look ?? index + 1);
  const upperBoundary = Number(boundary.upper_boundary_z ?? boundary.z_boundary ?? 0);
  const lowerBoundary = Number(boundary.lower_boundary_z ?? -upperBoundary);

  return {
    look,
    info_fraction: Number(boundary.info_fraction ?? look / Math.max(1, total)),
    alpha_spent: Number(boundary.alpha_spent ?? boundary.cumulative_alpha_spent ?? 0),
    upper_boundary_z: upperBoundary,
    lower_boundary_z: lowerBoundary,
    sample_size_cumulative: Number(boundary.sample_size_cumulative ?? 0),
    is_final: boundary.is_final === true
  };
}

export default function SequentialDesignSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const displayedAnalysis = selectedHistoryAnalysis ?? analysisResult;
  const sequentialBoundaries = (displayedAnalysis?.calculations.sequential_boundaries ?? []).map((boundary, index, items) =>
    normalizeSequentialBoundary(boundary as Record<string, unknown>, index, items.length)
  );
  const sequentialInflationFactor = displayedAnalysis?.calculations.sequential_inflation_factor ?? null;
  const sequentialAdjustedSampleSize = displayedAnalysis?.calculations.sequential_adjusted_sample_size ?? null;

  if (!displayedAnalysis?.report) {
    return null;
  }

  if (sequentialBoundaries.length === 0 || sequentialInflationFactor === null || sequentialAdjustedSampleSize === null) {
    return (
      <div className="callout">
        <Icon name="info" className="icon icon-inline" />
        <span>{t("results.sequentialDesign.unavailable")}</span>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>{t("results.sequentialDesign.title")}</h3>
      <p className="muted">
        {t("results.sequentialDesign.adjustedSampleSize")} <strong>{sequentialAdjustedSampleSize.toLocaleString()}</strong> {t("results.sequentialDesign.perVariant")} (
        {((sequentialInflationFactor - 1) * 100).toFixed(1)}% {t("results.sequentialDesign.moreThanFixedHorizon")})
      </p>
      {sequentialBoundaries.length > 0 ? (
        <div style={{ marginTop: "16px" }}>
          <Suspense fallback={<Skeleton height="240px" />}>
            <SequentialBoundaryChart
              boundaries={sequentialBoundaries.map((boundary) => ({
                look: boundary.look,
                alpha_spent: boundary.alpha_spent,
                upper_boundary_z: boundary.upper_boundary_z,
                lower_boundary_z: boundary.lower_boundary_z,
                sample_size_cumulative: boundary.sample_size_cumulative
              }))}
            />
          </Suspense>
        </div>
      ) : null}
      <div style={{ overflowX: "auto", marginTop: "12px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>{t("results.sequentialDesign.columns.look")}</th>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>{t("results.sequentialDesign.columns.infoFraction")}</th>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>{t("results.sequentialDesign.columns.cumulativeAlphaSpent")}</th>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>{t("results.sequentialDesign.columns.zBoundary")}</th>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>{t("results.sequentialDesign.columns.stopIf")}</th>
            </tr>
          </thead>
          <tbody>
            {sequentialBoundaries.map((boundary, index) => {
              const look = Number(boundary.look ?? index + 1);
              const infoFraction = Number(boundary.info_fraction ?? 0);
              const cumulativeAlphaSpent = Number(boundary.alpha_spent ?? 0);
              const zBoundary = Number(boundary.upper_boundary_z ?? 0);
              const isFinal = boundary.is_final === true;

              return (
                <tr key={look} style={isFinal ? { fontWeight: 600 } : undefined}>
                  <td style={{ padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>{look}</td>
                  <td style={{ padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>{(infoFraction * 100).toFixed(0)}%</td>
                  <td style={{ padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>{cumulativeAlphaSpent.toFixed(4)}</td>
                  <td style={{ padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>{zBoundary.toFixed(2)}</td>
                  <td style={{ padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}><strong>{zBoundary.toFixed(2)}</strong></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ marginTop: "12px" }}>
        {t("results.sequentialDesign.footer")}
      </p>
    </div>
  );
}
