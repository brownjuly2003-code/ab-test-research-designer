import { useTranslation } from "react-i18next";

import type { ProjectComparison } from "../../../lib/experiment";
import Icon from "../../Icon";
import MetricCard from "../../MetricCard";
import styles from "../../ResultsPanel.module.css";
import { formatDelta, formatResultTimestamp } from "../resultsShared";

function comparisonWarningTone(severity: string): "default" | "warning" {
  return severity === "high" || severity === "medium" ? "warning" : "default";
}

function joinOrNone(values: string[], noneLabel: string): string {
  return values.join(", ") || noneLabel;
}

export default function ComparisonDetails({ projectComparison }: { projectComparison: ProjectComparison }) {
  const { t } = useTranslation();
  const none = t("results.comparison.details.none");

  return (
    <>
      <span className="pill">{t("results.comparison.details.pill")}</span>
      <h3>{t("results.comparison.details.title")}</h3>
      <p className="muted">{projectComparison.summary}</p>
      <div className={styles["metric-grid"]}>
        <MetricCard
          icon="check"
          title={projectComparison.base_project.project_name}
          value={String(projectComparison.base_project.total_sample_size)}
          subtitle={t("results.comparison.details.durationDays", {
            value: String(projectComparison.base_project.estimated_duration_days)
          })}
          meta={t("results.comparison.details.warningLevel", {
            severity: projectComparison.base_project.warning_severity
          })}
          tone={comparisonWarningTone(projectComparison.base_project.warning_severity)}
        />
        <MetricCard
          icon="activity"
          title={projectComparison.candidate_project.project_name}
          value={String(projectComparison.candidate_project.total_sample_size)}
          subtitle={t("results.comparison.details.durationDays", {
            value: String(projectComparison.candidate_project.estimated_duration_days)
          })}
          meta={t("results.comparison.details.warningLevel", {
            severity: projectComparison.candidate_project.warning_severity
          })}
          tone={comparisonWarningTone(projectComparison.candidate_project.warning_severity)}
        />
        <MetricCard
          icon="clock"
          title={t("results.comparison.details.durationDelta")}
          value={formatDelta(projectComparison.deltas.estimated_duration_days, "d")}
          subtitle={t("results.comparison.details.candidateVsBase")}
          meta={projectComparison.metric_alignment_note}
        />
        <MetricCard
          icon="warning"
          title={t("results.comparison.details.warningsDelta")}
          value={formatDelta(projectComparison.deltas.warnings_count)}
          subtitle={t("results.comparison.details.candidateVsBase")}
          meta={t("results.comparison.details.sharedCount", {
            count: String(projectComparison.shared_warning_codes.length)
          })}
          tone={projectComparison.deltas.warnings_count > 0 ? "warning" : "default"}
        />
      </div>
      <div className={`callout ${styles["callout-info"]}`}>
        <Icon name="info" className="icon icon-inline" />
        <span>{projectComparison.metric_alignment_note}</span>
      </div>
      <div className="two-col">
        <div className="card">
          <strong>{projectComparison.base_project.project_name}</strong>
          <ul className="list">
            <li>
              {t("results.comparison.details.snapshot", {
                value: formatResultTimestamp(projectComparison.base_project.analysis_created_at)
              })}
            </li>
            <li>
              {t("results.comparison.details.primaryMetric", {
                value: projectComparison.base_project.primary_metric
              })}
            </li>
            <li>
              {t("results.comparison.details.executiveSummary", {
                value: projectComparison.base_project.executive_summary
              })}
            </li>
            <li>
              {t("results.comparison.details.totalSampleSize", {
                value: String(projectComparison.base_project.total_sample_size)
              })}
            </li>
            <li>
              {t("results.comparison.details.durationDays", {
                value: String(projectComparison.base_project.estimated_duration_days)
              })}
            </li>
            <li>
              {t("results.comparison.details.warningsCount", {
                value: String(projectComparison.base_project.warnings_count)
              })}
            </li>
          </ul>
        </div>
        <div className="card">
          <strong>{projectComparison.candidate_project.project_name}</strong>
          <ul className="list">
            <li>
              {t("results.comparison.details.snapshot", {
                value: formatResultTimestamp(projectComparison.candidate_project.analysis_created_at)
              })}
            </li>
            <li>
              {t("results.comparison.details.primaryMetric", {
                value: projectComparison.candidate_project.primary_metric
              })}
            </li>
            <li>
              {t("results.comparison.details.executiveSummary", {
                value: projectComparison.candidate_project.executive_summary
              })}
            </li>
            <li>
              {t("results.comparison.details.totalSampleSize", {
                value: String(projectComparison.candidate_project.total_sample_size)
              })}
            </li>
            <li>
              {t("results.comparison.details.durationDays", {
                value: String(projectComparison.candidate_project.estimated_duration_days)
              })}
            </li>
            <li>
              {t("results.comparison.details.warningsCount", {
                value: String(projectComparison.candidate_project.warnings_count)
              })}
            </li>
          </ul>
        </div>
        <div className="card">
          <strong>{t("results.comparison.details.deltas")}</strong>
          <ul className="list">
            <li>
              {t("results.comparison.details.totalSampleSize", {
                value: formatDelta(projectComparison.deltas.total_sample_size)
              })}
            </li>
            <li>
              {t("results.comparison.details.perVariant", {
                value: formatDelta(projectComparison.deltas.sample_size_per_variant)
              })}
            </li>
            <li>
              {t("results.comparison.details.duration", {
                value: formatDelta(projectComparison.deltas.estimated_duration_days, " days")
              })}
            </li>
            <li>
              {t("results.comparison.details.warnings", {
                value: formatDelta(projectComparison.deltas.warnings_count)
              })}
            </li>
          </ul>
        </div>
        <div className="card">
          <strong>{t("results.comparison.details.warningOverlap")}</strong>
          <ul className="list">
            <li>
              {t("results.comparison.details.shared", {
                value: joinOrNone(projectComparison.shared_warning_codes, none)
              })}
            </li>
            <li>
              {t("results.comparison.details.baseOnly", {
                value: joinOrNone(projectComparison.base_only_warning_codes, none)
              })}
            </li>
            <li>
              {t("results.comparison.details.candidateOnly", {
                value: joinOrNone(projectComparison.candidate_only_warning_codes, none)
              })}
            </li>
          </ul>
        </div>
        <div className="card">
          <strong>{t("results.comparison.details.highlights")}</strong>
          <ul className="list">
            {projectComparison.highlights.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="card">
          <strong>{t("results.comparison.details.assumptionsOverlap")}</strong>
          <ul className="list">
            <li>
              {t("results.comparison.details.shared", {
                value: joinOrNone(projectComparison.shared_assumptions, none)
              })}
            </li>
            <li>
              {t("results.comparison.details.baseOnly", {
                value: joinOrNone(projectComparison.base_only_assumptions, none)
              })}
            </li>
            <li>
              {t("results.comparison.details.candidateOnly", {
                value: joinOrNone(projectComparison.candidate_only_assumptions, none)
              })}
            </li>
          </ul>
        </div>
        <div className="card">
          <strong>{t("results.comparison.details.riskOverlap")}</strong>
          <ul className="list">
            <li>
              {t("results.comparison.details.shared", {
                value: joinOrNone(projectComparison.shared_risk_highlights, none)
              })}
            </li>
            <li>
              {t("results.comparison.details.baseOnly", {
                value: joinOrNone(projectComparison.base_only_risk_highlights, none)
              })}
            </li>
            <li>
              {t("results.comparison.details.candidateOnly", {
                value: joinOrNone(projectComparison.candidate_only_risk_highlights, none)
              })}
            </li>
          </ul>
        </div>
        <div className="card">
          <strong>{t("results.comparison.details.recommendationHighlights")}</strong>
          <ul className="list">
            {projectComparison.base_project.recommendation_highlights.length === 0 &&
            projectComparison.candidate_project.recommendation_highlights.length === 0 ? (
              <li>{none}</li>
            ) : (
              <>
                {(projectComparison.base_project.recommendation_highlights ?? []).map((item) => (
                  <li key={`base-${item}`}>
                    {t("results.comparison.details.baseItem", { value: item })}
                  </li>
                ))}
                {(projectComparison.candidate_project.recommendation_highlights ?? []).map((item) => (
                  <li key={`candidate-${item}`}>
                    {t("results.comparison.details.candidateItem", { value: item })}
                  </li>
                ))}
              </>
            )}
          </ul>
        </div>
      </div>
    </>
  );
}
