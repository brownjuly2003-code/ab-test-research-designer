import type {
  AnalysisResponsePayload,
  ExportFormat,
  ProjectAnalysisRun,
  ProjectComparison,
  ProjectHistory,
  ResultsState,
  SavedProject
} from "../lib/experiment";

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

export default function ResultsPanel({
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

  return (
    <>
      {projectComparison ? (
        <div className="result-block">
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
        <div className="result-block">
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
        <div className="results">
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

          <div className="result-block">
            <span className="pill">Deterministic calculations</span>
            <h3>Calculation summary</h3>
            <div className="two-col">
              <div className="card">
                <strong>Sample size / variant</strong>
                <div>{String(displayedAnalysis.calculations.results.sample_size_per_variant ?? "-")}</div>
              </div>
              <div className="card">
                <strong>Total sample size</strong>
                <div>{String(displayedAnalysis.calculations.results.total_sample_size ?? "-")}</div>
              </div>
              <div className="card">
                <strong>Estimated duration</strong>
                <div>{String(displayedAnalysis.calculations.results.estimated_duration_days ?? "-")} days</div>
              </div>
              <div className="card">
                <strong>Effective traffic</strong>
                <div>{String(displayedAnalysis.calculations.results.effective_daily_traffic ?? "-")}</div>
              </div>
            </div>
          </div>

          <div className="result-block">
            <span className="pill">Warnings</span>
            <h3>Heuristic checks</h3>
            <ul className="list">
              {Array.isArray(displayedAnalysis.calculations.warnings) && displayedAnalysis.calculations.warnings.length > 0 ? (
                displayedAnalysis.calculations.warnings.map((warning) => (
                  <li key={String(warning.code)}>
                    <strong>{String(warning.code)}</strong>: {String(warning.message)}
                  </li>
                ))
              ) : (
                <li>No warning rules fired.</li>
              )}
            </ul>
          </div>

          <div className="result-block">
            <span className="pill">Report</span>
            <h3>Deterministic experiment design</h3>
            <p className="muted">{String(displayedAnalysis.report.executive_summary ?? "")}</p>
            <div className="actions">
              <button className="btn ghost" onClick={() => onExportReport("markdown")}>
                Export Markdown
              </button>
              <button className="btn ghost" onClick={() => onExportReport("html")}>
                Export HTML
              </button>
            </div>
            <div className="two-col">
              <div className="card">
                <h3>Before launch</h3>
                <ul className="list">
                  {(displayedAnalysis.report.recommendations?.before_launch ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>During test</h3>
                <ul className="list">
                  {(displayedAnalysis.report.recommendations?.during_test ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>After test</h3>
                <ul className="list">
                  {(displayedAnalysis.report.recommendations?.after_test ?? []).map((item) => (
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
          </div>

          <div className="result-block">
            <span className="pill">Experiment design</span>
            <h3>Variant and rollout structure</h3>
            <div className="two-col">
              <div className="card">
                <h3>Variants</h3>
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
                <h3>Assumptions</h3>
                <ul className="list">
                  {(displayedAnalysis.report.calculations?.assumptions ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="result-block">
            <span className="pill">Metrics plan</span>
            <h3>Primary, secondary, and guardrail coverage</h3>
            <div className="two-col">
              <div className="card">
                <h3>Primary</h3>
                <ul className="list">
                  {(displayedAnalysis.report.metrics_plan?.primary ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Secondary</h3>
                <ul className="list">
                  {(displayedAnalysis.report.metrics_plan?.secondary ?? []).length > 0 ? (
                    (displayedAnalysis.report.metrics_plan?.secondary ?? []).map((item) => (
                      <li key={String(item)}>{String(item)}</li>
                    ))
                  ) : (
                    <li>No secondary metrics provided.</li>
                  )}
                </ul>
              </div>
              <div className="card">
                <h3>Guardrail</h3>
                <ul className="list">
                  {(displayedAnalysis.report.metrics_plan?.guardrail ?? []).length > 0 ? (
                    (displayedAnalysis.report.metrics_plan?.guardrail ?? []).map((item) => (
                      <li key={String(item)}>{String(item)}</li>
                    ))
                  ) : (
                    <li>No guardrail metrics provided.</li>
                  )}
                </ul>
              </div>
              <div className="card">
                <h3>Diagnostic</h3>
                <ul className="list">
                  {(displayedAnalysis.report.metrics_plan?.diagnostic ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="result-block">
            <span className="pill">Risks</span>
            <h3>Statistical and operational considerations</h3>
            <div className="two-col">
              <div className="card">
                <h3>Statistical</h3>
                <ul className="list">
                  {(displayedAnalysis.report.risks?.statistical ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Product</h3>
                <ul className="list">
                  {(displayedAnalysis.report.risks?.product ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Technical</h3>
                <ul className="list">
                  {(displayedAnalysis.report.risks?.technical ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Operational</h3>
                <ul className="list">
                  {(displayedAnalysis.report.risks?.operational ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="result-block">
            <span className="pill">AI advice</span>
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
              <div className="status">
                AI advice unavailable. Core deterministic output still works. {String(displayedAnalysis.advice.error ?? "")}
              </div>
            )}
          </div>
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
}
