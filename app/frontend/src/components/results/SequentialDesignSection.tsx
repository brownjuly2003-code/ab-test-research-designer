import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";

export default function SequentialDesignSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const displayedAnalysis = selectedHistoryAnalysis ?? analysisResult;
  const sequentialBoundaries = displayedAnalysis?.calculations.sequential_boundaries ?? [];
  const sequentialInflationFactor = displayedAnalysis?.calculations.sequential_inflation_factor ?? null;
  const sequentialAdjustedSampleSize = displayedAnalysis?.calculations.sequential_adjusted_sample_size ?? null;

  if (!displayedAnalysis?.report) {
    return null;
  }

  if (sequentialBoundaries.length === 0 || sequentialInflationFactor === null || sequentialAdjustedSampleSize === null) {
    return (
      <div className="callout">
        <Icon name="info" className="icon icon-inline" />
        <span>Sequential boundaries are not configured for the current analysis.</span>
      </div>
    );
  }

  return (
    <div className="card">
      <h3>Group sequential design (O'Brien-Fleming)</h3>
      <p className="muted">
        Adjusted sample size: <strong>{sequentialAdjustedSampleSize.toLocaleString()}</strong> per variant (
        {((sequentialInflationFactor - 1) * 100).toFixed(1)}% more than fixed horizon)
      </p>
      <div style={{ overflowX: "auto", marginTop: "12px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>Look</th>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>Info fraction</th>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>Cum. α spent</th>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>Z boundary</th>
              <th style={{ textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)" }}>Stop if |Z| ≥</th>
            </tr>
          </thead>
          <tbody>
            {sequentialBoundaries.map((boundary, index) => {
              const look = Number(boundary.look ?? index + 1);
              const infoFraction = Number(boundary.info_fraction ?? 0);
              const cumulativeAlphaSpent = Number(boundary.cumulative_alpha_spent ?? 0);
              const zBoundary = Number(boundary.z_boundary ?? 0);
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
        Stop early at any planned look if the observed absolute Z-statistic crosses the boundary. Otherwise continue to the next analysis.
      </p>
    </div>
  );
}
