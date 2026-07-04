import { useEffect, useState } from "react";

import { t } from "../../i18n";
import type {
  LiveArmStat,
  LiveComparison,
  LiveCupedBlock,
  LiveCupedComparison,
  LiveEventTimingBlock,
  LiveExclusionBlock,
  LiveGuardrailBlock,
  LiveGuardrailComparison,
  LiveGuardrailMetricResult,
  LiveHoldoutArmStat,
  LiveHoldoutBlock,
  LiveIdentityResolutionBlock,
  LiveStatsResponse,
  LiveStratifiedBlock,
  LiveStratifiedComparison
} from "../../lib/api";
import { apiUrl } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import { buildApiRequestHeaders, formatCappedProbabilityPercent, getDisplayedAnalysis } from "./resultsShared";

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
  if (metricType === "ratio") {
    // A ratio metric has no per-user conversion count; show exposed users and the ratio R̂.
    return t("results.liveStats.armRatio", {
      exposed: arm.exposed_users,
      ratio: formatNumber(arm.ratio, 4)
    });
  }
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
                prob: formatCappedProbabilityPercent(comparison.probability_treatment_beats_control)
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
          {comparison.always_valid?.status === "ok" ? (
            <div style={{ display: "grid", gap: "4px", marginTop: "2px" }}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
                <span className="pill">{t("results.liveStats.alwaysValidLabel")}</span>
                <span className={`pill ${comparison.always_valid.is_significant ? "accent" : ""}`}>
                  {comparison.always_valid.is_significant
                    ? t("results.liveStats.alwaysValidSignificant")
                    : t("results.liveStats.alwaysValidNotSignificant")}
                </span>
              </div>
              <span className="muted">
                {t("results.liveStats.alwaysValidLine", {
                  p: formatNumber(comparison.always_valid.always_valid_p_value, 4),
                  level: formatPercent(comparison.always_valid.confidence_level),
                  lower: formatNumber(comparison.always_valid.ci_sequence_lower, 4),
                  upper: formatNumber(comparison.always_valid.ci_sequence_upper, 4)
                })}
              </span>
              <span className="muted" style={{ fontSize: "0.85em" }}>
                {t("results.liveStats.alwaysValidHint")}
              </span>
            </div>
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
          {cuped.covariates && cuped.covariates.length > 1 ? (
            <>
              <span className="muted">
                {t("results.liveStats.cupedReductionMulti", {
                  n: cuped.num_covariates ?? cuped.covariates.length,
                  reduction: formatNumber(cuped.variance_reduction_pct)
                })}
              </span>
              <ul className="cuped-covariates" style={{ margin: 0, paddingLeft: "18px" }}>
                {cuped.covariates.map((covariate) => (
                  <li key={covariate.name} className="muted">
                    {t("results.liveStats.cupedCovariateLine", {
                      name: covariate.name,
                      theta: formatNumber(covariate.theta, 4)
                    })}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <span className="muted">
              {t("results.liveStats.cupedReduction", {
                theta: formatNumber(cuped.theta, 4),
                reduction: formatNumber(cuped.variance_reduction_pct)
              })}
            </span>
          )}
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

function StratifiedComparisonCard({
  comparison,
  variantNames
}: {
  comparison: LiveStratifiedComparison;
  variantNames: string[];
}) {
  const controlName = variantNames[0] ?? "#1";
  const treatmentName = variantNames[comparison.treatment_index] ?? `#${comparison.treatment_index + 1}`;

  return (
    <div style={{ display: "grid", gap: "4px", marginTop: "6px" }}>
      <strong style={{ fontSize: "0.9em" }}>
        {t("results.liveStats.comparisonTitle", { treatment: treatmentName, control: controlName })}
      </strong>
      {comparison.status === "insufficient_data" ? (
        <span className="muted">{comparison.note ?? t("results.liveStats.stratifiedPending")}</span>
      ) : (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
            <span className={`pill ${comparison.is_significant ? "accent" : ""}`}>
              {comparison.is_significant
                ? t("results.liveStats.significant")
                : t("results.liveStats.notSignificant")}
            </span>
            <span className="muted">
              {t("results.liveStats.stratifiedEffect", {
                effect: formatNumber(comparison.effect, 4),
                lower: formatNumber(comparison.ci_lower, 4),
                upper: formatNumber(comparison.ci_upper, 4),
                p: formatNumber(comparison.p_value, 4)
              })}
            </span>
          </div>
          <span className="muted">
            {t("results.liveStats.stratifiedReduction", {
              reduction: formatNumber(comparison.variance_reduction_pct),
              n: comparison.num_strata ?? 0
            })}
          </span>
          <ul className="stratified-strata" style={{ margin: 0, paddingLeft: "18px" }}>
            {(comparison.strata ?? []).map((stratum) => (
              <li key={stratum.stratum} className="muted">
                {t("results.liveStats.stratifiedStratumLine", {
                  stratum: stratum.stratum,
                  users: stratum.users,
                  effect: stratum.effect == null ? "—" : formatNumber(stratum.effect, 4)
                })}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function StratifiedBlock({
  stratified,
  variantNames
}: {
  stratified: LiveStratifiedBlock;
  variantNames: string[];
}) {
  return (
    <div className="callout" style={{ display: "grid", gap: "6px" }}>
      <strong>{t("results.liveStats.stratifiedTitle")}</strong>
      {stratified.status === "available" ? (
        <>
          <span className="muted">
            {t("results.liveStats.stratifiedCoverage", {
              stratified: stratified.stratified_users_total ?? 0,
              exposed: stratified.exposed_users_total ?? 0,
              strata: stratified.num_strata ?? 0
            })}
          </span>
          {(stratified.comparisons ?? []).map((comparison) => (
            <StratifiedComparisonCard
              key={comparison.treatment_index}
              comparison={comparison}
              variantNames={variantNames}
            />
          ))}
        </>
      ) : (
        <span className="muted">{stratified.note}</span>
      )}
    </div>
  );
}

function guardrailStatusPill(status: string): string {
  if (status === "breached") {
    return "pill warn";
  }
  if (status === "ok") {
    return "pill accent";
  }
  return "pill";
}

function guardrailStatusLabel(status: string): string {
  if (status === "breached") {
    return t("results.liveStats.guardrailBreached");
  }
  if (status === "warning") {
    return t("results.liveStats.guardrailWarning");
  }
  if (status === "ok") {
    return t("results.liveStats.guardrailOk");
  }
  return t("results.liveStats.guardrailPending");
}

function guardrailPoint(metricType: string, point: number | null | undefined): string {
  if (point == null) {
    return "—";
  }
  return metricType === "binary" ? formatPercent(point) : formatNumber(point, 4);
}

function GuardrailComparisonLine({
  comparison,
  metricType,
  variantNames
}: {
  comparison: LiveGuardrailComparison;
  metricType: string;
  variantNames: string[];
}) {
  const controlName =
    variantNames[comparison.control.variation_index] ?? `#${comparison.control.variation_index + 1}`;
  const treatmentName = variantNames[comparison.treatment_index] ?? `#${comparison.treatment_index + 1}`;

  return (
    <div style={{ display: "grid", gap: "2px", paddingLeft: "12px" }}>
      <span className="muted">
        {controlName}:{" "}
        {t("results.liveStats.guardrailArmLine", {
          exposed: comparison.control.exposed_users,
          point: guardrailPoint(metricType, comparison.control.point_estimate)
        })}
      </span>
      <span className="muted">
        {treatmentName}:{" "}
        {t("results.liveStats.guardrailArmLine", {
          exposed: comparison.treatment.exposed_users,
          point: guardrailPoint(metricType, comparison.treatment.point_estimate)
        })}
      </span>
      {comparison.status === "insufficient_data" ? (
        <span className="muted">{comparison.note ?? t("results.liveStats.guardrailPending")}</span>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
          <span className={guardrailStatusPill(comparison.status)}>
            {guardrailStatusLabel(comparison.status)}
          </span>
          <span className="muted">
            {t("results.liveStats.guardrailEffectLine", {
              harm: formatNumber(comparison.harm, 4),
              lower: formatNumber(comparison.harm_lower_bound, 4),
              p: formatNumber(comparison.p_value, 4)
            })}
          </span>
        </div>
      )}
    </div>
  );
}

function GuardrailMetricCard({
  metric,
  variantNames
}: {
  metric: LiveGuardrailMetricResult;
  variantNames: string[];
}) {
  const directionLabel =
    metric.direction === "decrease_is_bad"
      ? t("results.liveStats.guardrailDecreaseIsBad")
      : t("results.liveStats.guardrailIncreaseIsBad");

  return (
    <div style={{ display: "grid", gap: "4px", marginTop: "6px" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
        <strong style={{ fontSize: "0.9em" }}>{metric.name}</strong>
        <span className={guardrailStatusPill(metric.status)}>{guardrailStatusLabel(metric.status)}</span>
        <span className="muted" style={{ fontSize: "0.85em" }}>{directionLabel}</span>
      </div>
      {(metric.comparisons ?? []).map((comparison) => (
        <GuardrailComparisonLine
          key={comparison.treatment_index}
          comparison={comparison}
          metricType={metric.metric_type}
          variantNames={variantNames}
        />
      ))}
    </div>
  );
}

function GuardrailBlock({
  guardrail,
  variantNames
}: {
  guardrail: LiveGuardrailBlock | undefined;
  variantNames: string[];
}) {
  if (!guardrail) {
    return null;
  }
  return (
    <div className="callout" style={{ display: "grid", gap: "6px" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
        <strong>{t("results.liveStats.guardrailTitle")}</strong>
        {guardrail.status !== "unavailable" ? (
          <span className={guardrailStatusPill(guardrail.status)}>
            {guardrailStatusLabel(guardrail.status)}
          </span>
        ) : null}
      </div>
      {guardrail.status === "unavailable" ? (
        <span className="muted">{guardrail.note}</span>
      ) : (
        (guardrail.metrics ?? []).map((metric) => (
          <GuardrailMetricCard key={metric.name} metric={metric} variantNames={variantNames} />
        ))
      )}
    </div>
  );
}

function holdoutArmLine(arm: LiveHoldoutArmStat | null | undefined, metricType: string): string {
  if (!arm) {
    return "—";
  }
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

function HoldoutBlock({ holdout, metricType }: { holdout: LiveHoldoutBlock | undefined; metricType: string }) {
  if (!holdout) {
    return null;
  }
  return (
    <div className="callout" style={{ display: "grid", gap: "6px" }}>
      <strong>{t("results.liveStats.holdoutTitle")}</strong>
      {holdout.status === "ok" && holdout.analysis ? (
        <>
          <span className="muted">
            {t("results.liveStats.holdoutTreated")}: {holdoutArmLine(holdout.treated, metricType)}
          </span>
          <span className="muted">
            {t("results.liveStats.holdoutHeldBack")}: {holdoutArmLine(holdout.holdout, metricType)}
          </span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center", marginTop: "2px" }}>
            <span className={`pill ${holdout.analysis.is_significant ? "accent" : ""}`}>
              {holdout.analysis.is_significant
                ? t("results.liveStats.significant")
                : t("results.liveStats.notSignificant")}
            </span>
            <span className="muted">
              {t("results.liveStats.holdoutEffectLine", {
                effect: formatNumber(holdout.analysis.observed_effect, 4),
                lower: formatNumber(holdout.analysis.ci_lower, 4),
                upper: formatNumber(holdout.analysis.ci_upper, 4),
                p: formatNumber(holdout.analysis.p_value, 4)
              })}
            </span>
          </div>
          {holdout.probability_treated_beats_holdout != null ? (
            <span className="muted">
              {t("results.liveStats.holdoutBayesianLine", {
                prob: formatCappedProbabilityPercent(holdout.probability_treated_beats_holdout)
              })}
            </span>
          ) : null}
          {holdout.always_valid?.status === "ok" ? (
            <span className="muted">
              {t("results.liveStats.alwaysValidLine", {
                p: formatNumber(holdout.always_valid.always_valid_p_value, 4),
                level: formatPercent(holdout.always_valid.confidence_level),
                lower: formatNumber(holdout.always_valid.ci_sequence_lower, 4),
                upper: formatNumber(holdout.always_valid.ci_sequence_upper, 4)
              })}
            </span>
          ) : null}
        </>
      ) : (
        <span className="muted">{holdout.note}</span>
      )}
    </div>
  );
}

function EventTimingBlock({ eventTiming }: { eventTiming: LiveEventTimingBlock | undefined }) {
  if (!eventTiming || eventTiming.status !== "ok") {
    return null;
  }
  const late = eventTiming.late ?? 0;
  const outOfOrder = eventTiming.out_of_order ?? 0;
  // A clean event stream needs no callout — only surface the indicator when something is off-window.
  if (late === 0 && outOfOrder === 0) {
    return null;
  }
  return (
    <div className="callout" style={{ display: "grid", gap: "6px" }}>
      <strong>{t("results.liveStats.eventTimingTitle")}</strong>
      <span className="muted">
        {t("results.liveStats.eventTimingSummary", {
          late,
          outOfOrder,
          total: eventTiming.total ?? 0,
          horizon: eventTiming.horizon_days ?? 0
        })}
      </span>
      <span className="muted" style={{ fontSize: "0.85em" }}>
        {t("results.liveStats.eventTimingHint")}
      </span>
    </div>
  );
}

function IdentityResolutionBlock({
  identityResolution
}: {
  identityResolution: LiveIdentityResolutionBlock | undefined;
}) {
  // Only surface the indicator when identity resolution is active (links exist); a run with no
  // anonymous→canonical links needs no callout.
  if (!identityResolution || identityResolution.status !== "active") {
    return null;
  }
  return (
    <div className="callout" style={{ display: "grid", gap: "6px" }}>
      <strong>{t("results.liveStats.identityTitle")}</strong>
      <span className="muted">
        {t("results.liveStats.identitySummary", {
          linked: identityResolution.linked_identities ?? 0,
          merged: identityResolution.merged_users ?? 0,
          events: identityResolution.canonicalized_events ?? 0
        })}
      </span>
      <span className="muted" style={{ fontSize: "0.85em" }}>
        {t("results.liveStats.identityHint")}
      </span>
    </div>
  );
}

function ExclusionBlock({ exclusions }: { exclusions: LiveExclusionBlock | undefined }) {
  // Only surface the indicator when the bot / fraud filter actually removed someone; a run with
  // nothing filtered needs no callout.
  if (!exclusions || exclusions.status !== "active") {
    return null;
  }
  return (
    <div className="callout" style={{ display: "grid", gap: "6px" }}>
      <strong>{t("results.liveStats.exclusionTitle")}</strong>
      <span className="muted">
        {t("results.liveStats.exclusionSummary", {
          total: exclusions.total_filtered ?? 0,
          manual: exclusions.manual_filtered ?? 0,
          rateSpike: exclusions.rate_spike_filtered ?? 0
        })}
      </span>
      <span className="muted" style={{ fontSize: "0.85em" }}>
        {t("results.liveStats.exclusionHint")}
      </span>
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
                  <>
                    {stats.sequential.status === "fixed_horizon" && stats.sequential.information_fraction != null ? (
                      <span className="muted">
                        {t("results.liveStats.fixedHorizonProgress", {
                          fraction: formatPercent(stats.sequential.information_fraction),
                          planned: stats.sequential.planned_sample_size_per_variant ?? "—"
                        })}
                      </span>
                    ) : null}
                    <span className="muted">{stats.sequential.note}</span>
                  </>
                )}
              </div>

              <CupedBlock cuped={stats.cuped} variantNames={variantNames} />

              <StratifiedBlock stratified={stats.stratified} variantNames={variantNames} />

              <GuardrailBlock guardrail={stats.guardrail} variantNames={variantNames} />

              <HoldoutBlock holdout={stats.holdout} metricType={stats.metric_type} />

              <EventTimingBlock eventTiming={stats.event_timing} />
              <IdentityResolutionBlock identityResolution={stats.identity_resolution} />
              <ExclusionBlock exclusions={stats.exclusions} />
            </>
          )}

          <span className="muted" style={{ fontSize: "0.85em" }}>{stats.disclaimer}</span>
        </div>
      ) : null}
    </div>
  );
}
