import {
  getSectionFieldValue,
  getReviewSections,
  sections,
  stepLabels,
  type DraftFieldValue,
  type ExportFormat,
  type FullPayload,
  type FullPayloadSectionKey,
  type ResultsState
} from "../lib/experiment";

type WizardPanelProps = {
  step: number;
  form: FullPayload;
  activeProjectId: string | null;
  validationErrors: string[];
  importingDraft: boolean;
  loading: boolean;
  saving: boolean;
  results: ResultsState;
  statusMessage: string;
  error: string;
  onUpdateSection: (section: FullPayloadSectionKey, key: string, value: DraftFieldValue) => void;
  onBack: () => void;
  onNext: () => void;
  onSave: () => void;
  onStartNew: () => void;
  onImportDraft: () => void;
  onExportDraft: () => void;
  onRunAnalysis: () => void;
  onExportReport: (format: ExportFormat) => void;
};

export default function WizardPanel({
  step,
  form,
  activeProjectId,
  validationErrors,
  importingDraft,
  loading,
  saving,
  results,
  statusMessage,
  error,
  onUpdateSection,
  onBack,
  onNext,
  onSave,
  onStartNew,
  onImportDraft,
  onExportDraft,
  onRunAnalysis,
  onExportReport
}: WizardPanelProps) {
  const isReviewStep = step >= sections.length;
  const current = sections[Math.min(step, sections.length - 1)];
  const visibleFields = current.fields.filter((field) => (field.visibleWhen ? field.visibleWhen(form) : true));
  const reviewSections = getReviewSections(form);

  function readNextNumberValue(rawValue: string, emptyValue?: number | "" | null): number | "" | null {
    if (rawValue === "") {
      return emptyValue !== undefined ? emptyValue : 0;
    }

    return Number(rawValue);
  }

  return (
    <section className="panel">
      <div className="steps">
        {stepLabels.map((label, index) => (
          <div key={label} className={`step ${index === step ? "active" : index < step ? "done" : ""}`}>
            {index + 1}. {label}
          </div>
        ))}
      </div>

      {!isReviewStep ? (
        <div className="section">
          <h2>{current.title}</h2>
          <div className="note">
            <strong>{activeProjectId ? "Editing saved project" : "Working on a new draft"}</strong>
            <div className="muted">
              {activeProjectId ? `Project id: ${activeProjectId}` : "Saving will create a new local project record."}
            </div>
          </div>
          {validationErrors.length > 0 ? (
            <div className="status">
              <strong>Fix these fields before saving or running analysis:</strong>
              <ul className="list">
                {validationErrors.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="fields">
            {visibleFields.map((field) => {
              const targetSection = field.section ?? current.section;
              const value = getSectionFieldValue(form, targetSection, field.key);
              const fieldType = field.kind ?? "text";
              const fieldId = `${String(targetSection)}-${field.key}`;

              if (fieldType === "textarea") {
                return (
                  <div key={fieldId} className="field full">
                    <label htmlFor={fieldId}>{field.label}</label>
                    <textarea
                      id={fieldId}
                      value={String(value ?? "")}
                      onChange={(event) => onUpdateSection(targetSection, field.key, event.target.value)}
                    />
                  </div>
                );
              }

              if (fieldType === "boolean") {
                return (
                  <div key={fieldId} className="field">
                    <label htmlFor={fieldId}>{field.label}</label>
                    <select
                      id={fieldId}
                      value={String(value)}
                      onChange={(event) => onUpdateSection(targetSection, field.key, event.target.value === "true")}
                    >
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  </div>
                );
              }

              if (Array.isArray(field.options) && field.options.length > 0) {
                return (
                  <div key={fieldId} className={`field ${field.fullWidth ? "full" : ""}`}>
                    <label htmlFor={fieldId}>{field.label}</label>
                    <select
                      id={fieldId}
                      value={String(value ?? "")}
                      onChange={(event) => onUpdateSection(targetSection, field.key, event.target.value)}
                    >
                      {field.options.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                );
              }

              return (
                <div key={fieldId} className={`field ${field.fullWidth ? "full" : ""}`}>
                  <label htmlFor={fieldId}>{field.label}</label>
                  <input
                    id={fieldId}
                    type={fieldType === "number" ? "number" : "text"}
                    step={fieldType === "number" ? "any" : undefined}
                    value={String(value ?? "")}
                    onChange={(event) =>
                      onUpdateSection(
                        targetSection,
                        field.key,
                        fieldType === "number"
                          ? readNextNumberValue(event.target.value, field.emptyValue)
                          : event.target.value
                      )
                    }
                  />
                </div>
              );
            })}
          </div>

          <div className="actions">
            <button className="btn secondary" disabled={step === 0 || loading} onClick={onBack}>
              Back
            </button>
            <button className="btn ghost" disabled={loading || saving} onClick={onStartNew}>
              New draft
            </button>
            <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onImportDraft}>
              {importingDraft ? "Importing..." : "Import draft JSON"}
            </button>
            <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onExportDraft}>
              Export draft JSON
            </button>
            <button className="btn ghost" disabled={loading || saving} onClick={onSave}>
              {saving ? "Saving..." : activeProjectId ? "Update project" : "Save project"}
            </button>
            <button className="btn primary" disabled={loading} onClick={onNext}>
              Next
            </button>
          </div>
        </div>
      ) : (
        <div className="section">
          <h2>Review inputs</h2>
          <div className="note">
            <strong>{activeProjectId ? "Reviewing a saved project" : "Reviewing a new draft"}</strong>
            <div className="muted">
              Check the values below before saving or running the deterministic backend flow.
            </div>
          </div>
          {validationErrors.length > 0 ? (
            <div className="status">
              <strong>Fix these fields before saving or running analysis:</strong>
              <ul className="list">
                {validationErrors.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="two-col">
            {reviewSections.map((section) => (
              <div key={section.title} className="card">
                <h3>{section.title}</h3>
                <ul className="list">
                  {section.items.map((item) => (
                    <li key={`${section.title}-${item.label}`}>
                      <strong>{item.label}:</strong> {item.value}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="actions">
            <button className="btn secondary" disabled={loading} onClick={onBack}>
              Back
            </button>
            <button className="btn ghost" disabled={loading || saving} onClick={onStartNew}>
              New draft
            </button>
            <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onImportDraft}>
              {importingDraft ? "Importing..." : "Import draft JSON"}
            </button>
            <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onExportDraft}>
              Export draft JSON
            </button>
            <button className="btn ghost" disabled={loading || saving} onClick={onSave}>
              {saving ? "Saving..." : activeProjectId ? "Update project" : "Save project"}
            </button>
            <button className="btn primary" disabled={loading} onClick={onRunAnalysis}>
              {loading ? "Running analysis..." : "Run analysis"}
            </button>
          </div>
        </div>
      )}

      {results.report ? (
        <div className="results">
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
    </section>
  );
}
