import { memo } from "react";

import type {
  AnalysisResponsePayload,
  ExportFormat,
  ProjectAnalysisRun,
  ProjectComparison,
  ProjectHistory,
  ResultsState,
  SavedProject,
  WarningItem
} from "../lib/experiment";
import Accordion from "./Accordion";
import Icon from "./Icon";
import MetricCard from "./MetricCard";

type ResultsPanelProps = {
  results: ResultsState;
  displayedAnalysis: AnalysisResponsePayload | null;
  loading: boolean;
  statusMessage: string;
  error: string;
  activeProject: SavedProject | null;
  projectHistory: ProjectHistory | null;
  selectedHistoryRun: ProjectAnalysisRun | null;
  projectComparison: ProjectComparison | null;
  loadingProjectHistory: boolean;
  onClearHistorySelection: () => void;
  onExportReport: (format: ExportFormat) => void;
};

function formatResultTimestamp(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

function formatDelta(value: number, suffix = ""): string {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value}${suffix}`;
}

function getHighestSeverity(warnings: WarningItem[]): WarningItem["severity"] {
  if (warnings.some((warning) => warning.severity === "high")) {
    return "high";
  }
  if (warnings.some((warning) => warning.severity === "medium")) {
    return "medium";
  }
  return "low";
}

function getWarningSeverityLabel(warnings: WarningItem[]): string {
  const highCount = warnings.filter((warning) => warning.severity === "high").length;
  if (highCount > 0) {
    return `${highCount} high`;
  }
  const mediumCount = warnings.filter((warning) => warning.severity === "medium").length;
  if (mediumCount > 0) {
    return `${mediumCount} medium`;
  }
  return warnings.length > 0 ? `${warnings.length} low` : "No warnings";
}

const ResultsPanel = memo(function ResultsPanel({
  results,
  displayedAnalysis,
  loading,
  statusMessage,
  error,
  activeProject,
  projectHistory,
  selectedHistoryRun,
  projectComparison,
  loadingProjectHistory,
  onClearHistorySelection,
  onExportReport
}: ResultsPanelProps) {
  const latestRun = projectHistory?.analysis_runs[0] ?? null;
  const latestExport = projectHistory?.export_events[0] ?? null;
  const liveResultsAvailable = Boolean(results.report);
  const warnings = displayedAnalysis?.calculations.warnings ?? [];
  const warningSeverity = getHighestSeverity(warnings);
  const variantsCount = displayedAnalysis?.report.experiment_design?.variants.length ?? 0;
  const riskItemCount =
    (displayedAnalysis?.report.risks?.statistical?.length ?? 0) +
    (displayedAnalysis?.report.risks?.product?.length ?? 0) +
    (displayedAnalysis?.report.risks?.technical?.length ?? 0) +
    (displayedAnalysis?.report.risks?.operational?.length ?? 0);
  const metricItemCount =
    (displayedAnalysis?.report.metrics_plan?.primary?.length ?? 0) +
    (displayedAnalysis?.report.metrics_plan?.secondary?.length ?? 0) +
    (displayedAnalysis?.report.metrics_plan?.guardrail?.length ?? 0) +
    (displayedAnalysis?.report.metrics_plan?.diagnostic?.length ?? 0);

  return (
    <>
      {projectComparison ? (
        <div className="result-block results-enter">
          <span className="pill">Saved comparison</span>
          <h3>Saved snapshot comparison</h3>
          <p className="muted">{projectComparison.summary}</p>
          <div className="two-col">
            <div className="card">
              <strong>{projectComparison.base_project.project_name}</strong>
              <ul className="list">
                <li>Snapshot: {formatResultTimestamp(projectComparison.base_project.analysis_created_at)}</li>
                <li>Primary metric: {projectComparison.base_project.primary_metric}</li>
                <li>Total sample size: {String(projectComparison.base_project.total_sample_size)}</li>
                <li>Duration: {String(projectComparison.base_project.estimated_duration_days)} days</li>
                <li>Warnings: {String(projectComparison.base_project.warnings_count)}</li>
              </ul>
            </div>
            <div className="card">
              <strong>{projectComparison.candidate_project.project_name}</strong>
              <ul className="list">
                <li>Snapshot: {formatResultTimestamp(projectComparison.candidate_project.analysis_created_at)}</li>
                <li>Primary metric: {projectComparison.candidate_project.primary_metric}</li>
                <li>Total sample size: {String(projectComparison.candidate_project.total_sample_size)}</li>
                <li>Duration: {String(projectComparison.candidate_project.estimated_duration_days)} days</li>
                <li>Warnings: {String(projectComparison.candidate_project.warnings_count)}</li>
              </ul>
            </div>
            <div className="card">
              <strong>Deltas</strong>
              <ul className="list">
                <li>Total sample size: {formatDelta(projectComparison.deltas.total_sample_size)}</li>
                <li>Per variant: {formatDelta(projectComparison.deltas.sample_size_per_variant)}</li>
                <li>Duration: {formatDelta(projectComparison.deltas.estimated_duration_days, " days")}</li>
                <li>Warnings: {formatDelta(projectComparison.deltas.warnings_count)}</li>
              </ul>
            </div>
            <div className="card">
              <strong>Warning overlap</strong>
              <ul className="list">
                <li>Shared: {projectComparison.shared_warning_codes.join(", ") || "None"}</li>
                <li>Base only: {projectComparison.base_only_warning_codes.join(", ") || "None"}</li>
                <li>Candidate only: {projectComparison.candidate_only_warning_codes.join(", ") || "None"}</li>
              </ul>
            </div>
          </div>
        </div>
      ) : null}

      {selectedHistoryRun ? (
        <div className="result-block results-enter">
          <span className="pill">Saved snapshot</span>
          <h3>Viewing historical analysis</h3>
          <p className="muted">
            Opened snapshot from {formatResultTimestamp(selectedHistoryRun.created_at)}.
            {liveResultsAvailable ? " Current in-memory results are still available." : ""}
          </p>
          <div className="actions">
            <button className="btn ghost" onClick={onClearHistorySelection}>
              {liveResultsAvailable ? "Show current analysis" : "Close snapshot view"}
            </button>
          </div>
        </div>
      ) : null}

      {displayedAnalysis?.report ? (
        <div className="results results-enter">
          <div className="result-block">
            <div className="section-heading">
              <div>
                <span className="pill">Report</span>
                <h3>Deterministic experiment design</h3>
              </div>
              <div className="actions">
                <button className="btn ghost" onClick={() => onExportReport("markdown")}>
                  <Icon name="download" className="icon icon-inline" />
                  Export Markdown
                </button>
                <button className="btn ghost" onClick={() => onExportReport("html")}>
                  <Icon name="code" className="icon icon-inline" />
                  Export HTML
                </button>
              </div>
            </div>
            <p className="muted result-summary">{String(displayedAnalysis.report.executive_summary ?? "")}</p>
            <div className="metric-grid">
              <MetricCard
                icon="activity"
                title="Per variant"
                value={String(displayedAnalysis.calculations.results.sample_size_per_variant ?? "-")}
                subtitle="sample size / variant"
                meta={`${String(displayedAnalysis.calculations.calculation_summary.power ?? "-")} power`}
                badge={
                  displayedAnalysis.calculations.bonferroni_note ? (
                    <span className="inline-note">Bonferroni</span>
                  ) : null
                }
              />
              <MetricCard
                icon="check"
                title="Total sample"
                value={String(displayedAnalysis.calculations.results.total_sample_size ?? "-")}
                subtitle="total sample size"
                meta={`${String(variantsCount)} variants`}
              />
              <MetricCard
                icon="clock"
                title="Duration"
                value={`${String(displayedAnalysis.calculations.results.estimated_duration_days ?? "-")} days`}
                subtitle="estimated duration"
                meta={`${String(displayedAnalysis.calculations.results.effective_daily_traffic ?? "-")}/day`}
              />
              <MetricCard
                icon="warning"
                title="Warnings"
                value={String(warnings.length)}
                subtitle="heuristic checks"
                meta={getWarningSeverityLabel(warnings)}
                tone={warningSeverity === "high" ? "warning" : "default"}
              />
            </div>
            {displayedAnalysis.calculations.bonferroni_note ? (
              <div className="callout callout-info">
                <Icon name="info" className="icon icon-inline" />
                <span>{displayedAnalysis.calculations.bonferroni_note}</span>
              </div>
            ) : null}
          </div>

          {activeProject ? (
            <div className="result-block">
              <span className="pill">Saved activity</span>
              <h3>Project history context</h3>
              {loadingProjectHistory && !projectHistory ? (
                <p className="muted">Loading history for the current saved project...</p>
              ) : (
                <div className="two-col">
                  <div className="card">
                    <strong>Saved project</strong>
                    <div>{activeProject.project_name}</div>
                    <p className="muted">
                      {projectHistory?.analysis_runs.length ?? 0} of {projectHistory?.analysis_total ?? 0} analysis run(s)
                      {" | "}
                      {projectHistory?.export_events.length ?? 0} of {projectHistory?.export_total ?? 0} export event(s)
                    </p>
                  </div>
                  <div className="card">
                    <strong>{selectedHistoryRun ? "Opened analysis run" : "Latest analysis run"}</strong>
                    <div>
                      {selectedHistoryRun
                        ? formatResultTimestamp(selectedHistoryRun.created_at)
                        : latestRun
                          ? formatResultTimestamp(latestRun.created_at)
                          : "No saved analysis run yet"}
                    </div>
                    {(selectedHistoryRun ?? latestRun) ? (
                      <p className="muted">
                        {String((selectedHistoryRun ?? latestRun)?.summary.metric_type ?? "unknown metric")}
                        {" | "}
                        warnings {String((selectedHistoryRun ?? latestRun)?.summary.warnings_count ?? 0)}
                      </p>
                    ) : null}
                  </div>
                  <div className="card">
                    <strong>Latest export</strong>
                    <div>{latestExport ? formatResultTimestamp(latestExport.created_at) : "No export event yet"}</div>
                    {latestExport ? (
                      <p className="muted">
                        {latestExport.format.toUpperCase()}
                        {latestExport.analysis_run_id ? " | linked snapshot" : " | unlinked export"}
                      </p>
                    ) : null}
                  </div>
                </div>
              )}
            </div>
          ) : null}

          <Accordion title="Calculation summary" badge={`${variantsCount} variants`} defaultOpen>
            <div className="two-col">
              <div className="card">
                <strong>Primary statistic</strong>
                <ul className="list">
                  <li>Metric type: {String(displayedAnalysis.calculations.calculation_summary.metric_type)}</li>
                  <li>Baseline value: {String(displayedAnalysis.calculations.calculation_summary.baseline_value)}</li>
                  <li>MDE %: {String(displayedAnalysis.calculations.calculation_summary.mde_pct)}</li>
                  <li>MDE absolute: {String(displayedAnalysis.calculations.calculation_summary.mde_absolute)}</li>
                  <li>Alpha: {String(displayedAnalysis.calculations.calculation_summary.alpha)}</li>
                  <li>Power: {String(displayedAnalysis.calculations.calculation_summary.power)}</li>
                </ul>
              </div>
              <div className="card">
                <strong>Assumptions</strong>
                <ul className="list">
                  {(displayedAnalysis.report.calculations?.assumptions ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
            </div>
          </Accordion>

          <Accordion
            title="Warnings & Risks"
            badge={`${warnings.length} warnings`}
            badgeColor={warningSeverity === "high" ? "danger" : warningSeverity === "medium" ? "warn" : "accent"}
            defaultOpen={warnings.length > 0}
          >
            <div className="warning-stack">
              {warnings.length > 0 ? (
                warnings.map((warning) => (
                  <div key={String(warning.code)} className={`warning-row severity-${String(warning.severity)}`}>
                    <div className="warning-title">
                      <Icon
                        name={warning.severity === "high" ? "warning" : warning.severity === "medium" ? "info" : "check"}
                        className="icon icon-inline"
                      />
                      <strong>{String(warning.code)}</strong>
                    </div>
                    <div className="muted">{String(warning.message)}</div>
                  </div>
                ))
              ) : (
                <div className="warning-row severity-low">
                  <div className="warning-title">
                    <Icon name="check" className="icon icon-inline" />
                    <strong>No warning rules fired.</strong>
                  </div>
                  <div className="muted">The heuristic layer did not detect duration, traffic, or contamination issues.</div>
                </div>
              )}
            </div>
          </Accordion>

          <Accordion title="Experiment design" badge={`${variantsCount} variants`}>
            <div className="two-col">
              <div className="card">
                <h3>Variant and rollout structure</h3>
                <ul className="list">
                  {(displayedAnalysis.report.experiment_design?.variants ?? []).map((variant) => (
                    <li key={variant.name}>
                      <strong>{variant.name}</strong>: {variant.description}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Setup</h3>
                <ul className="list">
                  <li>
                    <strong>Randomization unit:</strong> {String(displayedAnalysis.report.experiment_design?.randomization_unit ?? "-")}
                  </li>
                  <li>
                    <strong>Traffic split:</strong> {String(displayedAnalysis.report.experiment_design?.traffic_split?.join(", ") ?? "-")}
                  </li>
                  <li>
                    <strong>Target audience:</strong> {String(displayedAnalysis.report.experiment_design?.target_audience ?? "-")}
                  </li>
                  <li>
                    <strong>Inclusion:</strong> {String(displayedAnalysis.report.experiment_design?.inclusion_criteria ?? "-")}
                  </li>
                  <li>
                    <strong>Exclusion:</strong> {String(displayedAnalysis.report.experiment_design?.exclusion_criteria ?? "-")}
                  </li>
                  <li>
                    <strong>Recommended duration:</strong> {String(displayedAnalysis.report.experiment_design?.recommended_duration_days ?? "-")} days
                  </li>
                </ul>
              </div>
              <div className="card">
                <h3>Stopping conditions</h3>
                <ul className="list">
                  {(displayedAnalysis.report.experiment_design?.stopping_conditions ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Open questions</h3>
                <ul className="list">
                  {(displayedAnalysis.report.open_questions ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
            </div>
          </Accordion>

          <Accordion title="Metrics plan" badge={`${metricItemCount} metrics`}>
            <div className="two-col">
              <div className="card">
                <h3>Primary, secondary, and guardrail coverage</h3>
                <ul className="list">
                  {(displayedAnalysis.report.metrics_plan?.primary ?? []).map((item) => (
                    <li key={`primary-${String(item)}`}>Primary: {String(item)}</li>
                  ))}
                  {(displayedAnalysis.report.metrics_plan?.secondary ?? []).map((item) => (
                    <li key={`secondary-${String(item)}`}>Secondary: {String(item)}</li>
                  ))}
                  {(displayedAnalysis.report.metrics_plan?.guardrail ?? []).map((item) => (
                    <li key={`guardrail-${String(item)}`}>Guardrail: {String(item)}</li>
                  ))}
                  {(displayedAnalysis.report.metrics_plan?.diagnostic ?? []).map((item) => (
                    <li key={`diagnostic-${String(item)}`}>Diagnostic: {String(item)}</li>
                  ))}
                </ul>
              </div>
            </div>
          </Accordion>

          <Accordion title="Risk assessment" badge={`${riskItemCount} items`}>
            <div className="two-col">
              <div className="card">
                <h3>Statistical and operational considerations</h3>
                <ul className="list">
                  {(displayedAnalysis.report.risks?.statistical ?? []).map((item) => (
                    <li key={`statistical-${String(item)}`}>{String(item)}</li>
                  ))}
                  {(displayedAnalysis.report.risks?.operational ?? []).map((item) => (
                    <li key={`operational-${String(item)}`}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Product</h3>
                <ul className="list">
                  {(displayedAnalysis.report.risks?.product ?? []).map((item) => (
                    <li key={`product-${String(item)}`}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Technical</h3>
                <ul className="list">
                  {(displayedAnalysis.report.risks?.technical ?? []).map((item) => (
                    <li key={`technical-${String(item)}`}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Recommendations</h3>
                <ul className="list">
                  {(displayedAnalysis.report.recommendations?.before_launch ?? []).map((item) => (
                    <li key={`before-${String(item)}`}>Before launch: {String(item)}</li>
                  ))}
                  {(displayedAnalysis.report.recommendations?.during_test ?? []).map((item) => (
                    <li key={`during-${String(item)}`}>During test: {String(item)}</li>
                  ))}
                  {(displayedAnalysis.report.recommendations?.after_test ?? []).map((item) => (
                    <li key={`after-${String(item)}`}>After test: {String(item)}</li>
                  ))}
                </ul>
              </div>
            </div>
          </Accordion>

          <Accordion title="AI recommendations" badge={displayedAnalysis.advice.available ? "Available" : "Offline"}>
            <div className="card">
              <h3>Local orchestrator output</h3>
              {displayedAnalysis.advice.available ? (
                <>
                  <p className="muted">
                    Provider: {String(displayedAnalysis.advice.provider)} | Model: {String(displayedAnalysis.advice.model)}
                  </p>
                  <div className="two-col">
                    <div className="card">
                      <strong>Assessment</strong>
                      <p className="muted">{String(displayedAnalysis.advice.advice?.brief_assessment ?? "")}</p>
                    </div>
                    <div className="card">
                      <strong>Design improvements</strong>
                      <ul className="list">
                        {(displayedAnalysis.advice.advice?.design_improvements ?? []).map((item) => (
                          <li key={String(item)}>{String(item)}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="card">
                      <strong>Key risks</strong>
                      <ul className="list">
                        {(displayedAnalysis.advice.advice?.key_risks ?? []).map((item) => (
                          <li key={String(item)}>{String(item)}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="card">
                      <strong>Metric recommendations</strong>
                      <ul className="list">
                        {(displayedAnalysis.advice.advice?.metric_recommendations ?? []).map((item) => (
                          <li key={String(item)}>{String(item)}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="card">
                      <strong>Interpretation pitfalls</strong>
                      <ul className="list">
                        {(displayedAnalysis.advice.advice?.interpretation_pitfalls ?? []).map((item) => (
                          <li key={String(item)}>{String(item)}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="card">
                      <strong>Additional checks</strong>
                      <ul className="list">
                        {(displayedAnalysis.advice.advice?.additional_checks ?? []).map((item) => (
                          <li key={String(item)}>{String(item)}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </>
              ) : (
                <div className="callout">
                  <Icon name="info" className="icon icon-inline" />
                  <span>
                    AI advice unavailable. Core deterministic output still works. {String(displayedAnalysis.advice.error ?? "")}
                  </span>
                </div>
              )}
            </div>
          </Accordion>
        </div>
      ) : null}

      {!displayedAnalysis?.report && !loading && !projectComparison ? (
        <div className="status">
          No analysis yet. Complete the wizard and run the deterministic backend flow first.
        </div>
      ) : null}

      {statusMessage ? <div className="status">{statusMessage}</div> : null}
      {error ? <div className="error">{error}</div> : null}
    </>
  );
});

export default ResultsPanel;
