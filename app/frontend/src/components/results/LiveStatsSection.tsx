import { useEffect, useState } from "react";

import { t } from "../../i18n";
import type {
  LiveArmStat,
  LiveComparison,
  LiveCupedBlock,
  LiveCupedComparison,
  LiveStatsResponse
} from "../../lib/api";
import { apiUrl } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import { buildApiRequestHeaders, getDisplayedAnalysis } from "./resultsShared";

function formatPercent(fraction: number | null | undefined): string {
  if (fraction == null) {
    return "—";
  }
  return `${(fraction * 100).toFixed(2)}%`;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value == null) {
    return "—";
  }
  return value.toFixed(digits);
}

function armLine(arm: LiveArmStat, metricType: string): string {
  const base = t("results.liveStats.armExposures", {
    exposed: arm.exposed_users,
    converted: arm.converted_users
  });
  if (metricType === "binary") {
    return `${base} · ${formatPercent(arm.conversion_rate)}`;
  }
  return `${base} · ${t("results.liveStats.armMean", {
    mean: formatNumber(arm.mean),
    std: formatNumber(arm.std)
  })}`;
}

function ComparisonCard({
  comparison,
  metricType,
  variantNames
}: {
  comparison: LiveComparison;
  metricType: string;
  variantNames: string[];
}) {
  const controlName = variantNames[comparison.control.variation_index] ?? `#${comparison.control.variation_index + 1}`;
  const treatmentName = variantNames[comparison.treatment_index] ?? `#${comparison.treatment_index + 1}`;

  return (
    <div
      className="callout"
      style={{
        marginTop: "var(--space-3)",
        borderColor: "var(--color-border-soft)",
        background: "var(--color-surface-muted)",
        display: "grid",
        gap: "6px"
      }}
    >
      <strong>{t("results.liveStats.comparisonTitle", { treatment: treatmentName, control: controlName })}</strong>
      <span className="muted">{controlName}: {armLine(comparison.control, metricType)}</span>
      <span className="muted">{treatmentName}: {armLine(comparison.treatment, metricType)}</span>

      {comparison.status === "insufficient_data" || !comparison.analysis ? (
        <span className="muted">{comparison.note ?? t("results.liveStats.comparisonPending")}</span>
      ) : (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center", marginTop: "2px" }}>
            <span className={`pill ${comparison.analysis.is_significant ? "accent" : ""}`}>
              {comparison.analysis.is_significant
                ? t("results.liveStats.significant")
                : t("results.liveStats.notSignificant")}
            </span>
            <span className="muted">
              {t("results.liveStats.effectLine", {
                effect: formatNumber(comparison.analysis.observed_effect, 4),
                lower: formatNumber(comparison.analysis.ci_lower, 4),
                upper: formatNumber(comparison.analysis.ci_upper, 4),
                p: formatNumber(comparison.analysis.p_value, 4)
              })}
            </span>
          </div>
          {comparison.probability_treatment_beats_control != null ? (
            <span className="muted">
              {t("results.liveStats.bayesianLine", {
                prob: formatPercent(comparison.probability_treatment_beats_control)
              })}
            </span>
          ) : null}
          {comparison.sequential_significant != null ? (
            <span className="muted">
              {comparison.sequential_significant
                ? t("results.liveStats.sequentialCrossed")
                : t("results.liveStats.sequentialNotCrossed")}
            </span>
          ) : null}
        </>
      )}
    </div>
  );
}

function CupedComparisonCard({
  comparison,
  variantNames
}: {
  comparison: LiveCupedComparison;
  variantNames: string[];
}) {
  const controlName =
    variantNames[comparison.control.variation_index] ?? `#${comparison.control.variation_index + 1}`;
  const treatmentName = variantNames[comparison.treatment_index] ?? `#${comparison.treatment_index + 1}`;

  return (
    <div style={{ display: "grid", gap: "4px", marginTop: "6px" }}>
      <span className="muted">
        {controlName}:{" "}
        {t("results.liveStats.cupedArmLine", {
          adjusted: formatNumber(comparison.control.adjusted_mean),
          raw: formatNumber(comparison.control.unadjusted_mean)
        })}
      </span>
      <span className="muted">
        {treatmentName}:{" "}
        {t("results.liveStats.cupedArmLine", {
          adjusted: formatNumber(comparison.treatment.adjusted_mean),
          raw: formatNumber(comparison.treatment.unadjusted_mean)
        })}
      </span>
      {comparison.status === "insufficient_data" || !comparison.analysis ? (
        <span className="muted">{comparison.note ?? t("results.liveStats.cupedComparisonPending")}</span>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
          <span className={`pill ${comparison.analysis.is_significant ? "accent" : ""}`}>
            {comparison.analysis.is_significant
              ? t("results.liveStats.significant")
              : t("results.liveStats.notSignificant")}
          </span>
          <span className="muted">
            {t("results.liveStats.cupedAdjustedEffect", {
              effect: formatNumber(comparison.analysis.observed_effect, 4),
              lower: formatNumber(comparison.analysis.ci_lower, 4),
              upper: formatNumber(comparison.analysis.ci_upper, 4),
              p: formatNumber(comparison.analysis.p_value, 4)
            })}
          </span>
        </div>
      )}
    </div>
  );
}

function CupedBlock({ cuped, variantNames }: { cuped: LiveCupedBlock; variantNames: string[] }) {
  return (
    <div className="callout" style={{ display: "grid", gap: "6px" }}>
      <strong>{t("results.liveStats.cupedTitle")}</strong>
      {cuped.status === "available" ? (
        <>
          <span className="muted">
            {t("results.liveStats.cupedReduction", {
              theta: formatNumber(cuped.theta, 4),
              reduction: formatNumber(cuped.variance_reduction_pct)
            })}
          </span>
          <span className="muted">
            {t("results.liveStats.cupedCoverage", {
              covariate: cuped.covariate_users_total ?? 0,
              exposed: cuped.exposed_users_total ?? 0
            })}
          </span>
          {(cuped.comparisons ?? []).map((comparison) => (
            <CupedComparisonCard
              key={comparison.treatment_index}
              comparison={comparison}
              variantNames={variantNames}
            />
          ))}
        </>
      ) : (
        <span className="muted">{cuped.note}</span>
      )}
    </div>
  );
}

export default function LiveStatsSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const resultsProjectId = useAnalysisStore((state) => state.resultsProjectId);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const selectedHistoryProjectId = useProjectStore((state) => state.selectedHistoryRun?.project_id ?? null);
  const activeProjectId = useProjectStore((state) => state.activeProjectId);

  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryAnalysis, analysisResult);
  const experimentId = selectedHistoryProjectId ?? resultsProjectId ?? activeProjectId;
  const variantNames = displayedAnalysis?.report?.experiment_design?.variants.map((variant) => variant.name) ?? [];

  const [stats, setStats] = useState<LiveStatsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setStats(null);
    setError("");
    setLoading(false);
  }, [experimentId]);

  async function refresh(): Promise<void> {
    if (!experimentId) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl(`/api/v1/experiments/${encodeURIComponent(experimentId)}/live-stats`), {
        method: "GET",
        headers: buildApiRequestHeaders()
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : t("results.liveStats.serviceUnavailable");
        throw new Error(detail);
      }
      setStats(body as LiveStatsResponse);
    } catch (requestError) {
      setStats(null);
      setError(requestError instanceof Error ? requestError.message : t("results.liveStats.serviceUnavailable"));
    } finally {
      setLoading(false);
    }
  }

  if (!displayedAnalysis?.report) {
    return null;
  }

  const srmPillClass =
    stats?.srm.status === "srm_detected" ? "pill warn" : stats?.srm.status === "ok" ? "pill accent" : "pill";

  return (
    <div className="card">
      <h3>{t("results.liveStats.title")}</h3>
      <p className="muted">{t("results.liveStats.description")}</p>

      {experimentId ? (
        <div className="actions" style={{ marginTop: "var(--space-4)" }}>
          <button className="btn secondary" type="button" onClick={() => void refresh()} disabled={loading}>
            {loading ? t("results.liveStats.refreshing") : t("results.liveStats.refresh")}
          </button>
        </div>
      ) : (
        <div className="callout" style={{ marginTop: "var(--space-4)" }}>
          <Icon name="info" className="icon icon-inline" />
          <span>{t("results.liveStats.saveFirst")}</span>
        </div>
      )}

      {error ? <div className="error">{error}</div> : null}

      {stats ? (
        <div style={{ marginTop: "var(--space-4)", display: "grid", gap: "var(--space-3)" }}>
          <span className="muted">
            {t("results.liveStats.totals", {
              exposures: stats.exposures_total,
              conversions: stats.conversions_total,
              metric: stats.primary_metric_name
            })}
          </span>

          {stats.exposures_total === 0 ? (
            <div className="callout">
              <Icon name="info" className="icon icon-inline" />
              <span>{t("results.liveStats.noData")}</span>
            </div>
          ) : (
            <>
              <div className="callout" style={{ display: "grid", gap: "6px" }}>
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <strong>{t("results.liveStats.srmTitle")}</strong>
                  <span className={srmPillClass}>
                    {stats.srm.status === "srm_detected"
                      ? t("results.liveStats.srmDetected")
                      : stats.srm.status === "ok"
                        ? t("results.liveStats.srmOk")
                        : t("results.liveStats.srmInsufficient")}
                  </span>
                </div>
                <span className="muted">{stats.srm.verdict}</span>
              </div>

              {stats.comparisons.map((comparison) => (
                <ComparisonCard
                  key={comparison.treatment_index}
                  comparison={comparison}
                  metricType={stats.metric_type}
                  variantNames={variantNames}
                />
              ))}

              <div className="callout" style={{ display: "grid", gap: "6px" }}>
                <strong>{t("results.liveStats.sequentialTitle")}</strong>
                {stats.sequential.status === "active" ? (
                  <span className="muted">
                    {t("results.liveStats.sequentialActive", {
                      fraction: formatPercent(stats.sequential.information_fraction),
                      boundary: formatNumber(stats.sequential.current_boundary_z),
                      planned: stats.sequential.planned_sample_size_per_variant ?? "—"
                    })}
                  </span>
                ) : (
                  <span className="muted">{stats.sequential.note}</span>
                )}
              </div>

              <CupedBlock cuped={stats.cuped} variantNames={variantNames} />
            </>
          )}

          <span className="muted" style={{ fontSize: "0.85em" }}>{stats.disclaimer}</span>
        </div>
      ) : null}
    </div>
  );
}
