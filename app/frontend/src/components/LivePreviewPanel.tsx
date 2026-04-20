import type { CalculationResponse } from "../lib/experiment";
import Spinner from "./Spinner";

type LivePreviewPanelProps = {
  result: CalculationResponse | null;
  isLoading: boolean;
  error: string | null;
};

function formatDuration(days: number): string {
  if (days < 1) {
    return "< 1 day";
  }

  return days === 1 ? "1 day" : `${String(days)} days`;
}

export default function LivePreviewPanel({ result, isLoading, error }: LivePreviewPanelProps) {
  const hasCupedEstimate = result?.cuped_sample_size_per_variant !== null && result?.cuped_sample_size_per_variant !== undefined;

  return (
    <div className="live-preview-panel" aria-live="polite">
      <div className="live-preview-header">
        <span className="live-preview-label">Live estimate</span>
        {isLoading ? (
          <span className="live-preview-status">
            <Spinner />
            Updating
          </span>
        ) : null}
      </div>

      {error ? (
        <span className="live-preview-message live-preview-error">{error}</span>
      ) : result ? (
        <>
          <div className="live-preview-cards">
            <div className="live-preview-card">
              <span className="preview-title">Sample size per variant</span>
              <span className="preview-value">{result.results.sample_size_per_variant.toLocaleString()}</span>
              <span className="preview-unit">users / variant</span>
            </div>
            <div className="live-preview-card">
              <span className="preview-title">Estimated duration</span>
              <span className="preview-value">{formatDuration(result.results.estimated_duration_days)}</span>
              <span className="preview-unit">based on current traffic</span>
            </div>
            {hasCupedEstimate ? (
              <div className="live-preview-card">
                <span className="preview-title">CUPED sample size</span>
                <span className="preview-value">{result.cuped_sample_size_per_variant?.toLocaleString()}</span>
                <span className="preview-unit">users / variant</span>
              </div>
            ) : null}
          </div>
          {hasCupedEstimate && result.cuped_variance_reduction_pct !== null && result.cuped_variance_reduction_pct !== undefined ? (
            <span className="preview-badge">{result.cuped_variance_reduction_pct}% variance reduction</span>
          ) : null}
          {result.bonferroni_note ? <span className="preview-badge">Bonferroni applied</span> : null}
        </>
      ) : (
        <span className="live-preview-message">Adjust traffic or metric inputs to see a live estimate.</span>
      )}
    </div>
  );
}
