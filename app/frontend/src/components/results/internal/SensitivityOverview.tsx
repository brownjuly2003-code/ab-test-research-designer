import { useState } from "react";

import type { AnalysisResponsePayload, ProjectHistory, SavedProject, WarningItem } from "../../../lib/experiment";
import type { SensitivityResponse } from "../../../lib/generated/api-contract";
import Icon from "../../Icon";
import MetricCard from "../../MetricCard";
import styles from "../../ResultsPanel.module.css";
import SampleSizeBar from "../../SampleSizeBar";
import SensitivityTable from "../../SensitivityTable";
import { formatResultTimestamp } from "../resultsShared";
import { resolveCurrentMde, resolveMetricType } from "../sensitivityShared";

type SensitivityOverviewProps = {
  displayedAnalysis: AnalysisResponsePayload;
  activeProject: SavedProject | null;
  projectHistory: ProjectHistory | null;
  canMutateBackend: boolean;
  backendMutationMessage: string;
  sensitivityData: SensitivityResponse | null;
  sensitivityLoading: boolean;
  sensitivityUnavailableMessage: string;
  standaloneExporting: boolean;
  standaloneExportError: string;
  canExportPdf: boolean;
  onExportReport: (format: "markdown" | "html") => void;
  onExportPdf: () => void;
  onExportProjectData: (format: "csv" | "xlsx") => void;
  onExportStandalone: () => void;
};

function getHighestSeverity(warnings: WarningItem[]): WarningItem["severity"] {
  if (warnings.some((warning) => warning.severity === "high")) return "high";
  if (warnings.some((warning) => warning.severity === "medium")) return "medium";
  return "low";
}

function getWarningSeverityLabel(warnings: WarningItem[]): string {
  const highCount = warnings.filter((warning) => warning.severity === "high").length;
  if (highCount > 0) return `${highCount} high`;
  const mediumCount = warnings.filter((warning) => warning.severity === "medium").length;
  if (mediumCount > 0) return `${mediumCount} medium`;
  return warnings.length > 0 ? `${warnings.length} low` : "No warnings";
}

export default function SensitivityOverview({
  displayedAnalysis,
  activeProject,
  projectHistory,
  canMutateBackend,
  backendMutationMessage,
  sensitivityData,
  sensitivityLoading,
  sensitivityUnavailableMessage,
  standaloneExporting,
  standaloneExportError,
  canExportPdf,
  onExportReport,
  onExportPdf,
  onExportProjectData,
  onExportStandalone
}: SensitivityOverviewProps) {
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const warnings = displayedAnalysis.calculations.warnings ?? [];
  const warningSeverity = getHighestSeverity(warnings);
  const variantsCount = displayedAnalysis.report.experiment_design?.variants.length ?? 0;
  const latestRun = projectHistory?.analysis_runs[0] ?? null;
  const latestExport = projectHistory?.export_events[0] ?? null;
  const currentMde = resolveCurrentMde(displayedAnalysis);
  const currentPower = displayedAnalysis.calculations.calculation_summary.power;

  return (
    <>
      <div className="section-heading">
        <div>
          <span className="pill">Report</span>
          <h3>Deterministic experiment design</h3>
        </div>
        <div className="actions">
          <button
            className="btn ghost"
            aria-expanded={exportMenuOpen}
            aria-controls="report-export-menu"
            disabled={!canMutateBackend}
            onClick={() => setExportMenuOpen((current) => !current)}
          >
            <Icon name="download" className="icon icon-inline" />
            Export
          </button>
        </div>
      </div>
      <div
        id="report-export-menu"
        role="menu"
        aria-label="Report export options"
        style={{
          display: exportMenuOpen ? "grid" : "none",
          gap: "8px",
          justifyItems: "start",
          marginBottom: "12px"
        }}
      >
        <button className="btn ghost" disabled={!canMutateBackend} title="Export report (Ctrl+E)" onClick={() => { setExportMenuOpen(false); onExportReport("markdown"); }}>
          <Icon name="download" className="icon icon-inline" />
          Export Markdown
        </button>
        <button className="btn ghost" disabled={!canMutateBackend} onClick={() => { setExportMenuOpen(false); onExportReport("html"); }}>
          <Icon name="code" className="icon icon-inline" />
          Export HTML
        </button>
        <button className="btn ghost" disabled={!canMutateBackend || !canExportPdf} onClick={() => { setExportMenuOpen(false); onExportPdf(); }}>
          <Icon name="download" className="icon icon-inline" />
          Export PDF
        </button>
        <button className="btn ghost" disabled={!canMutateBackend} onClick={() => { setExportMenuOpen(false); onExportProjectData("csv"); }}>
          <Icon name="download" className="icon icon-inline" />
          CSV Data
        </button>
        <button className="btn ghost" disabled={!canMutateBackend} onClick={() => { setExportMenuOpen(false); onExportProjectData("xlsx"); }}>
          <Icon name="download" className="icon icon-inline" />
          Excel Workbook
        </button>
        <button className="btn primary" disabled={!canMutateBackend || standaloneExporting} onClick={() => { setExportMenuOpen(false); onExportStandalone(); }}>
          <Icon name="download" className="icon icon-inline" />
          {standaloneExporting ? "Exporting..." : "Export Full Report"}
        </button>
      </div>
      <p className={`muted ${styles["result-summary"]}`}>{String(displayedAnalysis.report.executive_summary ?? "")}</p>
      {!canMutateBackend ? <div className="callout"><Icon name="info" className="icon icon-inline" /><span>{backendMutationMessage}</span></div> : null}
      {standaloneExportError ? <div className="error">{standaloneExportError}</div> : null}
      <div className={styles["metric-grid"]}>
        <MetricCard
          icon="activity"
          title="Per variant"
          value={String(displayedAnalysis.calculations.results.sample_size_per_variant ?? "-")}
          subtitle="sample size / variant"
          meta={`${String(displayedAnalysis.calculations.calculation_summary.power ?? "-")} power`}
          badge={displayedAnalysis.calculations.bonferroni_note ? <span className={styles["inline-note"]}>Bonferroni</span> : null}
        />
        <MetricCard icon="check" title="Total sample" value={String(displayedAnalysis.calculations.results.total_sample_size ?? "-")} subtitle="total sample size" meta={`${String(variantsCount)} variants`} />
        <MetricCard icon="clock" title="Duration" value={`${String(displayedAnalysis.calculations.results.estimated_duration_days ?? "-")} days`} subtitle="estimated duration" meta={`${String(displayedAnalysis.calculations.results.effective_daily_traffic ?? "-")}/day`} />
        <MetricCard icon="warning" title="Warnings" value={String(warnings.length)} subtitle="heuristic checks" meta={getWarningSeverityLabel(warnings)} tone={warningSeverity === "high" ? "warning" : "default"} />
      </div>
      {displayedAnalysis.calculations.bonferroni_note ? <div className={`callout ${styles["callout-info"]}`}><Icon name="info" className="icon icon-inline" /><span>{displayedAnalysis.calculations.bonferroni_note}</span></div> : null}
      {displayedAnalysis.calculations.bayesian_sample_size_per_variant !== null ? (
        <div className={styles["cuped-panel"]}>
          <h3>Bayesian estimate</h3>
          <div className={styles["cuped-comparison"]}>
            <div className={styles["cuped-card"]}><span className={styles["cuped-label"]}>Frequentist</span><span className={styles["cuped-value"]}>{displayedAnalysis.calculations.results.sample_size_per_variant.toLocaleString()}</span><span className={styles["cuped-unit"]}>users / variant</span></div>
            <div className={styles["cuped-arrow"]}>{"->"}</div>
            <div className={[styles["cuped-card"], styles["cuped-card-adjusted"]].join(" ")}><span className={styles["cuped-label"]}>Bayesian{displayedAnalysis.calculations.bayesian_credibility != null ? ` (${Math.round(displayedAnalysis.calculations.bayesian_credibility * 100)}% CI)` : ""}</span><span className={styles["cuped-value"]}>{displayedAnalysis.calculations.bayesian_sample_size_per_variant?.toLocaleString()}</span><span className={styles["cuped-unit"]}>users / variant</span></div>
          </div>
          {displayedAnalysis.calculations.bayesian_note ? <p className="muted">{displayedAnalysis.calculations.bayesian_note}</p> : null}
        </div>
      ) : null}
      {displayedAnalysis.calculations.cuped_sample_size_per_variant !== null ? (
        <div className={styles["cuped-panel"]}>
          <h3>CUPED-adjusted estimate</h3>
          <div className={styles["cuped-comparison"]}>
            <div className={styles["cuped-card"]}><span className={styles["cuped-label"]}>Without CUPED</span><span className={styles["cuped-value"]}>{displayedAnalysis.calculations.results.sample_size_per_variant.toLocaleString()}</span><span className={styles["cuped-unit"]}>users / variant</span></div>
            <div className={styles["cuped-arrow"]}>{"->"}</div>
            <div className={[styles["cuped-card"], styles["cuped-card-adjusted"]].join(" ")}><span className={styles["cuped-label"]}>With CUPED{displayedAnalysis.calculations.cuped_variance_reduction_pct !== null ? ` (rho squared=${displayedAnalysis.calculations.cuped_variance_reduction_pct}%)` : ""}</span><span className={styles["cuped-value"]}>{displayedAnalysis.calculations.cuped_sample_size_per_variant?.toLocaleString()}</span><span className={styles["cuped-unit"]}>users / variant</span></div>
            {displayedAnalysis.calculations.cuped_variance_reduction_pct !== null ? <div className={styles["cuped-savings-badge"]}>-{displayedAnalysis.calculations.cuped_variance_reduction_pct}% sample size</div> : null}
          </div>
          <p className="muted">
            {displayedAnalysis.calculations.cuped_duration_days !== null ? `Estimated duration changes from ${displayedAnalysis.calculations.results.estimated_duration_days} to ${displayedAnalysis.calculations.cuped_duration_days} days. ` : ""}
            {displayedAnalysis.calculations.cuped_std !== null ? `Adjusted std dev: ${displayedAnalysis.calculations.cuped_std}.` : ""}
          </p>
        </div>
      ) : null}
      <div className="two-col" style={{ marginTop: "var(--space-4)" }}>
        <div className="card">
          <h3>Sensitivity table</h3>
          <p className="muted">Duration matrix across the MDE and power scenarios returned by the backend.</p>
          {sensitivityLoading ? <p className="muted">Loading sensitivity table...</p> : sensitivityData?.cells.length ? (
            <SensitivityTable cells={sensitivityData.cells} currentMde={currentMde} currentPower={currentPower} metricType={resolveMetricType(displayedAnalysis.calculations.calculation_summary.metric_type)} />
          ) : <div className="callout"><Icon name="info" className="icon icon-inline" /><span>{sensitivityUnavailableMessage}</span></div>}
        </div>
        <div className="card">
          <h3>Sample size breakdown</h3>
          <p className="muted">Per-variant sample requirement shown alongside the configured traffic allocation.</p>
          <SampleSizeBar sampleSizePerVariant={displayedAnalysis.calculations.results.sample_size_per_variant} variants={variantsCount} variantNames={displayedAnalysis.report.experiment_design?.variants.map((variant) => variant.name)} trafficSplit={displayedAnalysis.report.experiment_design?.traffic_split} />
        </div>
      </div>
      <div className="two-col" style={{ marginTop: "var(--space-4)" }}>
        <div className="card"><h3>Calculation summary</h3><ul className="list"><li>Metric type: {String(displayedAnalysis.calculations.calculation_summary.metric_type)}</li><li>Baseline value: {String(displayedAnalysis.calculations.calculation_summary.baseline_value)}</li><li>MDE %: {String(displayedAnalysis.calculations.calculation_summary.mde_pct)}</li><li>MDE absolute: {String(displayedAnalysis.calculations.calculation_summary.mde_absolute)}</li><li>Alpha: {String(displayedAnalysis.calculations.calculation_summary.alpha)}</li><li>Power: {String(displayedAnalysis.calculations.calculation_summary.power)}</li></ul></div>
        <div className="card"><h3>Assumptions</h3><ul className="list">{(displayedAnalysis.report.calculations?.assumptions ?? []).map((item) => <li key={String(item)}>{String(item)}</li>)}</ul></div>
      </div>
      {activeProject ? (
        <>
          <h3 style={{ marginTop: "var(--space-4)" }}>Project history context</h3>
          <div className="two-col">
            <div className="card"><strong>Saved project</strong><div>{activeProject.project_name}</div><p className="muted">{String(activeProject.revision_count ?? 0)} revision(s){" | "}last save {activeProject.last_revision_at ? formatResultTimestamp(activeProject.last_revision_at) : "not recorded"}</p><p className="muted">{projectHistory?.analysis_runs.length ?? 0} of {projectHistory?.analysis_total ?? 0} analysis run(s){" | "}{projectHistory?.export_events.length ?? 0} of {projectHistory?.export_total ?? 0} export event(s)</p></div>
            <div className="card"><strong>Latest analysis run</strong><div>{latestRun ? formatResultTimestamp(latestRun.created_at) : "No saved analysis run yet"}</div>{latestRun ? <p className="muted">{String(latestRun.summary.metric_type ?? "unknown metric")}{" | "}warnings {String(latestRun.summary.warnings_count ?? 0)}</p> : null}</div>
            <div className="card"><strong>Latest export</strong><div>{latestExport ? formatResultTimestamp(latestExport.created_at) : "No export event yet"}</div>{latestExport ? <p className="muted">{latestExport.format.toUpperCase()}{latestExport.analysis_run_id ? " | linked snapshot" : " | unlinked export"}</p> : null}</div>
          </div>
        </>
      ) : null}
    </>
  );
}
