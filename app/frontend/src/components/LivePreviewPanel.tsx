import { useTranslation } from "react-i18next";

import type { CalculationResponse } from "../lib/experiment";
import Spinner from "./Spinner";

type LivePreviewPanelProps = {
  result: CalculationResponse | null;
  isLoading: boolean;
  error: string | null;
};

export default function LivePreviewPanel({ result, isLoading, error }: LivePreviewPanelProps) {
  const { t } = useTranslation();
  const hasCupedEstimate = result?.cuped_sample_size_per_variant !== null && result?.cuped_sample_size_per_variant !== undefined;

  function formatDuration(days: number): string {
    if (days < 1) {
      return t("livePreview.underOneDay");
    }

    return t("livePreview.days", { count: days });
  }

  return (
    <div className="live-preview-panel" aria-live="polite">
      <div className="live-preview-header">
        <span className="live-preview-label">{t("livePreview.label")}</span>
        {isLoading ? (
          <span className="live-preview-status">
            <Spinner />
            {t("livePreview.updating")}
          </span>
        ) : null}
      </div>

      {error ? (
        <span className="live-preview-message live-preview-error">{t(error)}</span>
      ) : result ? (
        <>
          <div className="live-preview-cards">
            <div className="live-preview-card">
              <span className="preview-title">{t("livePreview.sampleSizeTitle")}</span>
              <span className="preview-value">{result.results.sample_size_per_variant.toLocaleString()}</span>
              <span className="preview-unit">{t("livePreview.usersPerVariant")}</span>
            </div>
            <div className="live-preview-card">
              <span className="preview-title">{t("livePreview.durationTitle")}</span>
              <span className="preview-value">{formatDuration(result.results.estimated_duration_days)}</span>
              <span className="preview-unit">{t("livePreview.durationMeta")}</span>
            </div>
            {hasCupedEstimate ? (
              <div className="live-preview-card">
                <span className="preview-title">{t("livePreview.cupedTitle")}</span>
                <span className="preview-value">{result.cuped_sample_size_per_variant?.toLocaleString()}</span>
                <span className="preview-unit">{t("livePreview.usersPerVariant")}</span>
              </div>
            ) : null}
          </div>
          {hasCupedEstimate && result.cuped_variance_reduction_pct !== null && result.cuped_variance_reduction_pct !== undefined ? (
            <span className="preview-badge">{t("livePreview.varianceReductionBadge", { pct: result.cuped_variance_reduction_pct })}</span>
          ) : null}
          {result.bonferroni_note ? <span className="preview-badge">{t("livePreview.bonferroniBadge")}</span> : null}
        </>
      ) : (
        <span className="live-preview-message">{t("livePreview.emptyHint")}</span>
      )}
    </div>
  );
}
