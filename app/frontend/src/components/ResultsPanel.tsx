import type { ExportFormat, ProjectHistory, SavedProject, ResultsState } from "../lib/experiment";

type ResultsPanelProps = {
  results: ResultsState;
  loading: boolean;
  statusMessage: string;
  error: string;
  activeProject: SavedProject | null;
  projectHistory: ProjectHistory | null;
  loadingProjectHistory: boolean;
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

export default function ResultsPanel({
  results,
  loading,
  statusMessage,
  error,
  activeProject,
  projectHistory,
  loadingProjectHistory,
  onExportReport
}: ResultsPanelProps) {
  const latestRun = projectHistory?.analysis_runs[0] ?? null;
  const latestExport = projectHistory?.export_events[0] ?? null;

  return (
    <>
      {results.report ? (
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
                      {projectHistory?.analysis_runs.length ?? 0} analysis run(s) | {projectHistory?.export_events.length ?? 0} export event(s)
                    </p>
                  </div>
                  <div className="card">
                    <strong>Latest analysis run</strong>
                    <div>{latestRun ? formatResultTimestamp(latestRun.created_at) : "No saved analysis run yet"}</div>
                    {latestRun ? (
                      <p className="muted">
                        {String(latestRun.summary.metric_type ?? "unknown metric")} | warnings {String(latestRun.summary.warnings_count)}
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
                <div>{String(results.calculations?.results?.sample_size_per_variant ?? "-")}</div>
              </div>
              <div className="card">
                <strong>Total sample size</strong>
                <div>{String(results.calculations?.results?.total_sample_size ?? "-")}</div>
              </div>
              <div className="card">
                <strong>Estimated duration</strong>
                <div>{String(results.calculations?.results?.estimated_duration_days ?? "-")} days</div>
              </div>
              <div className="card">
                <strong>Effective traffic</strong>
                <div>{String(results.calculations?.results?.effective_daily_traffic ?? "-")}</div>
              </div>
            </div>
          </div>

          <div className="result-block">
            <span className="pill">Warnings</span>
            <h3>Heuristic checks</h3>
            <ul className="list">
              {Array.isArray(results.calculations?.warnings) && results.calculations?.warnings.length > 0 ? (
                results.calculations.warnings.map((warning) => (
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
            <p className="muted">{String(results.report.executive_summary ?? "")}</p>
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
                  {(results.report.recommendations?.before_launch ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>During test</h3>
                <ul className="list">
                  {(results.report.recommendations?.during_test ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>After test</h3>
                <ul className="list">
                  {(results.report.recommendations?.after_test ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Open questions</h3>
                <ul className="list">
                  {(results.report.open_questions ?? []).map((item) => (
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
                  {(results.report.experiment_design?.variants ?? []).map((variant) => (
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
                    <strong>Randomization unit:</strong> {String(results.report.experiment_design?.randomization_unit ?? "-")}
                  </li>
                  <li>
                    <strong>Traffic split:</strong> {String(results.report.experiment_design?.traffic_split?.join(", ") ?? "-")}
                  </li>
                  <li>
                    <strong>Target audience:</strong> {String(results.report.experiment_design?.target_audience ?? "-")}
                  </li>
                  <li>
                    <strong>Inclusion:</strong> {String(results.report.experiment_design?.inclusion_criteria ?? "-")}
                  </li>
                  <li>
                    <strong>Exclusion:</strong> {String(results.report.experiment_design?.exclusion_criteria ?? "-")}
                  </li>
                  <li>
                    <strong>Recommended duration:</strong> {String(results.report.experiment_design?.recommended_duration_days ?? "-")} days
                  </li>
                </ul>
              </div>
              <div className="card">
                <h3>Stopping conditions</h3>
                <ul className="list">
                  {(results.report.experiment_design?.stopping_conditions ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Assumptions</h3>
                <ul className="list">
                  {(results.report.calculations?.assumptions ?? []).map((item) => (
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
                  {(results.report.metrics_plan?.primary ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Secondary</h3>
                <ul className="list">
                  {(results.report.metrics_plan?.secondary ?? []).length > 0 ? (
                    (results.report.metrics_plan?.secondary ?? []).map((item) => (
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
                  {(results.report.metrics_plan?.guardrail ?? []).length > 0 ? (
                    (results.report.metrics_plan?.guardrail ?? []).map((item) => (
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
                  {(results.report.metrics_plan?.diagnostic ?? []).map((item) => (
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
                  {(results.report.risks?.statistical ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Product</h3>
                <ul className="list">
                  {(results.report.risks?.product ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Technical</h3>
                <ul className="list">
                  {(results.report.risks?.technical ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
              <div className="card">
                <h3>Operational</h3>
                <ul className="list">
                  {(results.report.risks?.operational ?? []).map((item) => (
                    <li key={String(item)}>{String(item)}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          <div className="result-block">
            <span className="pill">AI advice</span>
            <h3>Local orchestrator output</h3>
            {results.advice?.available ? (
              <>
                <p className="muted">
                  Provider: {String(results.advice.provider)} | Model: {String(results.advice.model)}
                </p>
                <div className="two-col">
                  <div className="card">
                    <strong>Assessment</strong>
                    <p className="muted">{String(results.advice.advice?.brief_assessment ?? "")}</p>
                  </div>
                  <div className="card">
                    <strong>Design improvements</strong>
                    <ul className="list">
                      {(results.advice.advice?.design_improvements ?? []).map((item) => (
                        <li key={String(item)}>{String(item)}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="card">
                    <strong>Key risks</strong>
                    <ul className="list">
                      {(results.advice.advice?.key_risks ?? []).map((item) => (
                        <li key={String(item)}>{String(item)}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="card">
                    <strong>Metric recommendations</strong>
                    <ul className="list">
                      {(results.advice.advice?.metric_recommendations ?? []).map((item) => (
                        <li key={String(item)}>{String(item)}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="card">
                    <strong>Interpretation pitfalls</strong>
                    <ul className="list">
                      {(results.advice.advice?.interpretation_pitfalls ?? []).map((item) => (
                        <li key={String(item)}>{String(item)}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="card">
                    <strong>Additional checks</strong>
                    <ul className="list">
                      {(results.advice.advice?.additional_checks ?? []).map((item) => (
                        <li key={String(item)}>{String(item)}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </>
            ) : (
              <div className="status">
                AI advice unavailable. Core deterministic output still works. {String(results.advice?.error ?? "")}
              </div>
            )}
          </div>
        </div>
      ) : null}

      {!results.report && !loading ? (
        <div className="status">
          No analysis yet. Complete the wizard and run the deterministic backend flow first.
        </div>
      ) : null}

      {statusMessage ? <div className="status">{statusMessage}</div> : null}
      {error ? <div className="error">{error}</div> : null}
    </>
  );
}
