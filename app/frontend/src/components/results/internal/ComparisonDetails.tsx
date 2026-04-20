import type { ProjectComparison } from "../../../lib/experiment";
import Icon from "../../Icon";
import MetricCard from "../../MetricCard";
import styles from "../../ResultsPanel.module.css";
import { formatDelta, formatResultTimestamp } from "../resultsShared";

function comparisonWarningTone(severity: string): "default" | "warning" {
  return severity === "high" || severity === "medium" ? "warning" : "default";
}

export default function ComparisonDetails({ projectComparison }: { projectComparison: ProjectComparison }) {
  return (
    <>
      <span className="pill">Saved comparison</span>
      <h3>Saved snapshot comparison</h3>
      <p className="muted">{projectComparison.summary}</p>
      <div className={styles["metric-grid"]}>
        <MetricCard icon="check" title={projectComparison.base_project.project_name} value={String(projectComparison.base_project.total_sample_size)} subtitle={`${String(projectComparison.base_project.estimated_duration_days)} days`} meta={`${projectComparison.base_project.warning_severity} warning level`} tone={comparisonWarningTone(projectComparison.base_project.warning_severity)} />
        <MetricCard icon="activity" title={projectComparison.candidate_project.project_name} value={String(projectComparison.candidate_project.total_sample_size)} subtitle={`${String(projectComparison.candidate_project.estimated_duration_days)} days`} meta={`${projectComparison.candidate_project.warning_severity} warning level`} tone={comparisonWarningTone(projectComparison.candidate_project.warning_severity)} />
        <MetricCard icon="clock" title="Duration delta" value={formatDelta(projectComparison.deltas.estimated_duration_days, "d")} subtitle="candidate vs base" meta={projectComparison.metric_alignment_note} />
        <MetricCard icon="warning" title="Warnings delta" value={formatDelta(projectComparison.deltas.warnings_count)} subtitle="candidate vs base" meta={`shared ${String(projectComparison.shared_warning_codes.length)}`} tone={projectComparison.deltas.warnings_count > 0 ? "warning" : "default"} />
      </div>
      <div className={`callout ${styles["callout-info"]}`}><Icon name="info" className="icon icon-inline" /><span>{projectComparison.metric_alignment_note}</span></div>
      <div className="two-col">
        <div className="card"><strong>{projectComparison.base_project.project_name}</strong><ul className="list"><li>Snapshot: {formatResultTimestamp(projectComparison.base_project.analysis_created_at)}</li><li>Primary metric: {projectComparison.base_project.primary_metric}</li><li>Executive summary: {projectComparison.base_project.executive_summary}</li><li>Total sample size: {String(projectComparison.base_project.total_sample_size)}</li><li>Duration: {String(projectComparison.base_project.estimated_duration_days)} days</li><li>Warnings: {String(projectComparison.base_project.warnings_count)}</li></ul></div>
        <div className="card"><strong>{projectComparison.candidate_project.project_name}</strong><ul className="list"><li>Snapshot: {formatResultTimestamp(projectComparison.candidate_project.analysis_created_at)}</li><li>Primary metric: {projectComparison.candidate_project.primary_metric}</li><li>Executive summary: {projectComparison.candidate_project.executive_summary}</li><li>Total sample size: {String(projectComparison.candidate_project.total_sample_size)}</li><li>Duration: {String(projectComparison.candidate_project.estimated_duration_days)} days</li><li>Warnings: {String(projectComparison.candidate_project.warnings_count)}</li></ul></div>
        <div className="card"><strong>Deltas</strong><ul className="list"><li>Total sample size: {formatDelta(projectComparison.deltas.total_sample_size)}</li><li>Per variant: {formatDelta(projectComparison.deltas.sample_size_per_variant)}</li><li>Duration: {formatDelta(projectComparison.deltas.estimated_duration_days, " days")}</li><li>Warnings: {formatDelta(projectComparison.deltas.warnings_count)}</li></ul></div>
        <div className="card"><strong>Warning overlap</strong><ul className="list"><li>Shared: {projectComparison.shared_warning_codes.join(", ") || "None"}</li><li>Base only: {projectComparison.base_only_warning_codes.join(", ") || "None"}</li><li>Candidate only: {projectComparison.candidate_only_warning_codes.join(", ") || "None"}</li></ul></div>
        <div className="card"><strong>Comparison highlights</strong><ul className="list">{projectComparison.highlights.map((item) => <li key={item}>{item}</li>)}</ul></div>
        <div className="card"><strong>Assumptions overlap</strong><ul className="list"><li>Shared: {projectComparison.shared_assumptions.join(", ") || "None"}</li><li>Base only: {projectComparison.base_only_assumptions.join(", ") || "None"}</li><li>Candidate only: {projectComparison.candidate_only_assumptions.join(", ") || "None"}</li></ul></div>
        <div className="card"><strong>Risk overlap</strong><ul className="list"><li>Shared: {projectComparison.shared_risk_highlights.join(", ") || "None"}</li><li>Base only: {projectComparison.base_only_risk_highlights.join(", ") || "None"}</li><li>Candidate only: {projectComparison.candidate_only_risk_highlights.join(", ") || "None"}</li></ul></div>
        <div className="card"><strong>Recommendation highlights</strong><ul className="list">{projectComparison.base_project.recommendation_highlights.length === 0 && projectComparison.candidate_project.recommendation_highlights.length === 0 ? <li>None</li> : <>{(projectComparison.base_project.recommendation_highlights ?? []).map((item) => <li key={`base-${item}`}>Base: {item}</li>)}{(projectComparison.candidate_project.recommendation_highlights ?? []).map((item) => <li key={`candidate-${item}`}>Candidate: {item}</li>)}</>}</ul></div>
      </div>
    </>
  );
}
