import { useState } from "react";

import type { AnalysisResponsePayload, ProjectHistory, SavedProject, WarningItem } from "../../../lib/experiment";
import type { SensitivityResponse } from "../../../lib/generated/api-contract";
import { t } from "../../../i18n";
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

function getWarningSeverityLabel(warnings: WarningItem[], t: (key: string, options?: Record<string, unknown>) => string): string {
  const highCount = warnings.filter((warning) => warning.severity === "high").length;
  if (highCount > 0) return t("results.sensitivityOverview.warningSeverity.high", { count: highCount });
  const mediumCount = warnings.filter((warning) => warning.severity === "medium").length;
  if (mediumCount > 0) return t("results.sensitivityOverview.warningSeverity.medium", { count: mediumCount });
  return warnings.length > 0 ? t("results.sensitivityOverview.warningSeverity.low", { count: warnings.length }) : t("results.sensitivityOverview.warningSeverity.none");
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
          <span className="pill">{t("results.sensitivityOverview.reportPill")}</span>
          <h3>{t("results.sensitivityOverview.title")}</h3>
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
            {t("results.sensitivityOverview.export")}
          </button>
        </div>
      </div>
      <div
        id="report-export-menu"
        role="menu"
        aria-label={t("results.sensitivityOverview.exportMenuAriaLabel")}
        style={{
          display: exportMenuOpen ? "grid" : "none",
          gap: "8px",
          justifyItems: "start",
          marginBottom: "12px"
        }}
      >
        <button className="btn ghost" disabled={!canMutateBackend} title={t("results.sensitivityOverview.exportReportTitle")} onClick={() => { setExportMenuOpen(false); onExportReport("markdown"); }}>
          <Icon name="download" className="icon icon-inline" />
          {t("results.sensitivityOverview.exportMarkdown")}
        </button>
        <button className="btn ghost" disabled={!canMutateBackend} onClick={() => { setExportMenuOpen(false); onExportReport("html"); }}>
          <Icon name="code" className="icon icon-inline" />
          {t("results.sensitivityOverview.exportHtml")}
        </button>
        <button className="btn ghost" disabled={!canMutateBackend || !canExportPdf} onClick={() => { setExportMenuOpen(false); onExportPdf(); }}>
          <Icon name="download" className="icon icon-inline" />
          {t("results.sensitivityOverview.exportPdf")}
        </button>
        <button className="btn ghost" disabled={!canMutateBackend} onClick={() => { setExportMenuOpen(false); onExportProjectData("csv"); }}>
          <Icon name="download" className="icon icon-inline" />
          {t("results.sensitivityOverview.exportCsv")}
        </button>
        <button className="btn ghost" disabled={!canMutateBackend} onClick={() => { setExportMenuOpen(false); onExportProjectData("xlsx"); }}>
          <Icon name="download" className="icon icon-inline" />
          {t("results.sensitivityOverview.exportXlsx")}
        </button>
        <button className="btn primary" disabled={!canMutateBackend || standaloneExporting} onClick={() => { setExportMenuOpen(false); onExportStandalone(); }}>
          <Icon name="download" className="icon icon-inline" />
          {standaloneExporting ? t("results.sensitivityOverview.exporting") : t("results.sensitivityOverview.exportFullReport")}
        </button>
      </div>
      <p className={`muted ${styles["result-summary"]}`}>{String(displayedAnalysis.report.executive_summary ?? "")}</p>
      {!canMutateBackend ? <div className="callout"><Icon name="info" className="icon icon-inline" /><span>{backendMutationMessage}</span></div> : null}
      {standaloneExportError ? <div className="error">{standaloneExportError}</div> : null}
      <div className={styles["metric-grid"]}>
        <MetricCard
          icon="activity"
          title={t("results.sensitivityOverview.cards.perVariant")}
          value={String(displayedAnalysis.calculations.results.sample_size_per_variant ?? "-")}
          subtitle={t("results.sensitivityOverview.cards.sampleSizePerVariant")}
          meta={t("results.sensitivityOverview.cards.powerMeta", { power: String(displayedAnalysis.calculations.calculation_summary.power ?? "-") })}
          badge={displayedAnalysis.calculations.bonferroni_note ? <span className={styles["inline-note"]}>{t("results.sensitivityOverview.cards.bonferroni")}</span> : null}
        />
        <MetricCard icon="check" title={t("results.sensitivityOverview.cards.totalSample")} value={String(displayedAnalysis.calculations.results.total_sample_size ?? "-")} subtitle={t("results.sensitivityOverview.cards.totalSampleSubtitle")} meta={t("results.sensitivityOverview.cards.variantsMeta", { count: variantsCount })} />
        <MetricCard icon="clock" title={t("results.sensitivityOverview.cards.duration")} value={t("results.sensitivityOverview.cards.durationValue", { days: String(displayedAnalysis.calculations.results.estimated_duration_days ?? "-") })} subtitle={t("results.sensitivityOverview.cards.durationSubtitle")} meta={t("results.sensitivityOverview.cards.perDayMeta", { traffic: String(displayedAnalysis.calculations.results.effective_daily_traffic ?? "-") })} />
        <MetricCard icon="warning" title={t("results.sensitivityOverview.cards.warnings")} value={String(warnings.length)} subtitle={t("results.sensitivityOverview.cards.warningsSubtitle")} meta={getWarningSeverityLabel(warnings, t)} tone={warningSeverity === "high" ? "warning" : "default"} />
      </div>
      {displayedAnalysis.calculations.bonferroni_note ? <div className={`callout ${styles["callout-info"]}`}><Icon name="info" className="icon icon-inline" /><span>{displayedAnalysis.calculations.bonferroni_note}</span></div> : null}
      {displayedAnalysis.calculations.bayesian_sample_size_per_variant !== null ? (
        <div className={styles["cuped-panel"]}>
          <h3>{t("results.sensitivityOverview.bayesianEstimate.title")}</h3>
          <div className={styles["cuped-comparison"]}>
            <div className={styles["cuped-card"]}><span className={styles["cuped-label"]}>{t("results.sensitivityOverview.bayesianEstimate.frequentist")}</span><span className={styles["cuped-value"]}>{displayedAnalysis.calculations.results.sample_size_per_variant.toLocaleString()}</span><span className={styles["cuped-unit"]}>{t("results.sensitivityOverview.bayesianEstimate.usersPerVariant")}</span></div>
            <div className={styles["cuped-arrow"]}>{"->"}</div>
            <div className={[styles["cuped-card"], styles["cuped-card-adjusted"]].join(" ")}><span className={styles["cuped-label"]}>{t("results.sensitivityOverview.bayesianEstimate.bayesian")}{displayedAnalysis.calculations.bayesian_credibility != null ? ` (${t("results.panel.credibilityInterval", { percent: Math.round(displayedAnalysis.calculations.bayesian_credibility * 100) })})` : ""}</span><span className={styles["cuped-value"]}>{displayedAnalysis.calculations.bayesian_sample_size_per_variant?.toLocaleString()}</span><span className={styles["cuped-unit"]}>{t("results.sensitivityOverview.bayesianEstimate.usersPerVariant")}</span></div>
          </div>
          {displayedAnalysis.calculations.bayesian_note ? <p className="muted">{displayedAnalysis.calculations.bayesian_note}</p> : null}
        </div>
      ) : null}
      {displayedAnalysis.calculations.cuped_sample_size_per_variant !== null ? (
        <div className={styles["cuped-panel"]}>
          <h3>{t("results.sensitivityOverview.cuped.title")}</h3>
          <div className={styles["cuped-comparison"]}>
            <div className={styles["cuped-card"]}><span className={styles["cuped-label"]}>{t("results.sensitivityOverview.cuped.without")}</span><span className={styles["cuped-value"]}>{displayedAnalysis.calculations.results.sample_size_per_variant.toLocaleString()}</span><span className={styles["cuped-unit"]}>{t("results.sensitivityOverview.bayesianEstimate.usersPerVariant")}</span></div>
            <div className={styles["cuped-arrow"]}>{"->"}</div>
            <div className={[styles["cuped-card"], styles["cuped-card-adjusted"]].join(" ")}><span className={styles["cuped-label"]}>{t("results.sensitivityOverview.cuped.with")}{displayedAnalysis.calculations.cuped_variance_reduction_pct !== null ? ` (rho squared=${displayedAnalysis.calculations.cuped_variance_reduction_pct}%)` : ""}</span><span className={styles["cuped-value"]}>{displayedAnalysis.calculations.cuped_sample_size_per_variant?.toLocaleString()}</span><span className={styles["cuped-unit"]}>{t("results.sensitivityOverview.bayesianEstimate.usersPerVariant")}</span></div>
            {displayedAnalysis.calculations.cuped_variance_reduction_pct !== null ? <div className={styles["cuped-savings-badge"]}>{t("results.sensitivityOverview.cuped.sampleSizeSavings", { pct: displayedAnalysis.calculations.cuped_variance_reduction_pct })}</div> : null}
          </div>
          <p className="muted">
            {displayedAnalysis.calculations.cuped_duration_days !== null ? t("results.sensitivityOverview.cuped.durationChange", { from: displayedAnalysis.calculations.results.estimated_duration_days, to: displayedAnalysis.calculations.cuped_duration_days }) : ""}
            {displayedAnalysis.calculations.cuped_std !== null ? ` ${t("results.sensitivityOverview.cuped.adjustedStdDev", { value: displayedAnalysis.calculations.cuped_std })}` : ""}
          </p>
        </div>
      ) : null}
      <div className="two-col" style={{ marginTop: "var(--space-4)" }}>
        <div className="card">
          <h3>{t("results.sensitivityOverview.sensitivityTable.title")}</h3>
          <p className="muted">{t("results.sensitivityOverview.sensitivityTable.description")}</p>
          {sensitivityLoading ? <p className="muted">{t("results.sensitivityOverview.sensitivityTable.loading")}</p> : sensitivityData?.cells.length ? (
            <SensitivityTable cells={sensitivityData.cells} currentMde={currentMde} currentPower={currentPower} metricType={resolveMetricType(displayedAnalysis.calculations.calculation_summary.metric_type)} />
          ) : <div className="callout"><Icon name="info" className="icon icon-inline" /><span>{sensitivityUnavailableMessage}</span></div>}
        </div>
        <div className="card">
          <h3>{t("results.sensitivityOverview.sampleSizeBreakdown.title")}</h3>
          <p className="muted">{t("results.sensitivityOverview.sampleSizeBreakdown.description")}</p>
          <SampleSizeBar sampleSizePerVariant={displayedAnalysis.calculations.results.sample_size_per_variant} variants={variantsCount} variantNames={displayedAnalysis.report.experiment_design?.variants.map((variant) => variant.name)} trafficSplit={displayedAnalysis.report.experiment_design?.traffic_split} />
        </div>
      </div>
      <div className="two-col" style={{ marginTop: "var(--space-4)" }}>
        <div className="card"><h3>{t("results.sensitivityOverview.calculationSummary.title")}</h3><ul className="list"><li>{t("results.sensitivityOverview.calculationSummary.metricType")}: {String(displayedAnalysis.calculations.calculation_summary.metric_type)}</li><li>{t("results.sensitivityOverview.calculationSummary.baselineValue")}: {String(displayedAnalysis.calculations.calculation_summary.baseline_value)}</li><li>{t("results.sensitivityOverview.calculationSummary.mdePct")}: {String(displayedAnalysis.calculations.calculation_summary.mde_pct)}</li><li>{t("results.sensitivityOverview.calculationSummary.mdeAbsolute")}: {String(displayedAnalysis.calculations.calculation_summary.mde_absolute)}</li><li>{t("results.sensitivityOverview.calculationSummary.alpha")}: {String(displayedAnalysis.calculations.calculation_summary.alpha)}</li><li>{t("results.sensitivityOverview.calculationSummary.power")}: {String(displayedAnalysis.calculations.calculation_summary.power)}</li></ul></div>
        <div className="card"><h3>{t("results.sensitivityOverview.assumptions.title")}</h3><ul className="list">{(displayedAnalysis.report.calculations?.assumptions ?? []).map((item) => <li key={String(item)}>{String(item)}</li>)}</ul></div>
      </div>
      {activeProject ? (
        <>
          <h3 style={{ marginTop: "var(--space-4)" }}>{t("results.sensitivityOverview.projectHistoryContext.title")}</h3>
          <div className="two-col">
            <div className="card"><strong>{t("results.sensitivityOverview.projectHistoryContext.savedProject")}</strong><div>{activeProject.project_name}</div><p className="muted">{t("results.sensitivityOverview.projectHistoryContext.revisionsCount", { count: String(activeProject.revision_count ?? 0) })}{" | "}{t("results.sensitivityOverview.projectHistoryContext.lastSave")} {activeProject.last_revision_at ? formatResultTimestamp(activeProject.last_revision_at) : t("results.sensitivityOverview.projectHistoryContext.notRecorded")}</p><p className="muted">{t("results.sensitivityOverview.projectHistoryContext.analysisRuns", { current: projectHistory?.analysis_runs.length ?? 0, total: projectHistory?.analysis_total ?? 0 })}{" | "}{t("results.sensitivityOverview.projectHistoryContext.exportEvents", { current: projectHistory?.export_events.length ?? 0, total: projectHistory?.export_total ?? 0 })}</p></div>
            <div className="card"><strong>{t("results.sensitivityOverview.projectHistoryContext.latestAnalysisRun")}</strong><div>{latestRun ? formatResultTimestamp(latestRun.created_at) : t("results.sensitivityOverview.projectHistoryContext.noSavedAnalysisRunYet")}</div>{latestRun ? <p className="muted">{String(latestRun.summary.metric_type ?? t("results.sensitivityOverview.projectHistoryContext.unknownMetric"))}{" | "}{t("results.sensitivityOverview.projectHistoryContext.warnings")} {String(latestRun.summary.warnings_count ?? 0)}</p> : null}</div>
            <div className="card"><strong>{t("results.sensitivityOverview.projectHistoryContext.latestExport")}</strong><div>{latestExport ? formatResultTimestamp(latestExport.created_at) : t("results.sensitivityOverview.projectHistoryContext.noExportEventYet")}</div>{latestExport ? <p className="muted">{latestExport.format.toUpperCase()}{latestExport.analysis_run_id ? ` | ${t("results.sensitivityOverview.projectHistoryContext.linkedSnapshot")}` : ` | ${t("results.sensitivityOverview.projectHistoryContext.unlinkedExport")}`}</p> : null}</div>
          </div>
        </>
      ) : null}
    </>
  );
}
