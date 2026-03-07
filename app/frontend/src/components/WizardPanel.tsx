import { sections, stepLabels, type ExportFormat, type FullPayload, type ResultsState } from "../lib/experiment";

type WizardPanelProps = {
  step: number;
  form: FullPayload;
  activeProjectId: string | null;
  validationErrors: string[];
  loading: boolean;
  saving: boolean;
  results: ResultsState;
  statusMessage: string;
  error: string;
  onUpdateSection: (section: keyof FullPayload, key: string, value: unknown) => void;
  onBack: () => void;
  onNext: () => void;
  onSave: () => void;
  onStartNew: () => void;
  onRunAnalysis: () => void;
  onExportReport: (format: ExportFormat) => void;
};

export default function WizardPanel({
  step,
  form,
  activeProjectId,
  validationErrors,
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
  onRunAnalysis,
  onExportReport
}: WizardPanelProps) {
  const current = sections[Math.min(step, sections.length - 1)];

  return (
    <section className="panel">
      <div className="steps">
        {stepLabels.map((label, index) => (
          <div key={label} className={`step ${index === step ? "active" : index < step ? "done" : ""}`}>
            {index + 1}. {label}
          </div>
        ))}
      </div>

      {step < sections.length ? (
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
            {current.fields.map(([label, key, kind, explicitSection]) => {
              const targetSection = explicitSection ?? current.section;
              const value = form[targetSection][key as keyof typeof form[typeof targetSection]];
              const fieldType = kind ?? "text";

              if (fieldType === "textarea") {
                return (
                  <div key={key} className="field full">
                    <label>{label}</label>
                    <textarea value={String(value ?? "")} onChange={(event) => onUpdateSection(targetSection, key, event.target.value)} />
                  </div>
                );
              }

              if (fieldType === "boolean") {
                return (
                  <div key={key} className="field">
                    <label>{label}</label>
                    <select value={String(value)} onChange={(event) => onUpdateSection(targetSection, key, event.target.value === "true")}>
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  </div>
                );
              }

              return (
                <div key={key} className={`field ${label.includes("description") || label.includes("constraints") ? "full" : ""}`}>
                  <label>{label}</label>
                  <input
                    type={fieldType === "number" ? "number" : "text"}
                    step={fieldType === "number" ? "any" : undefined}
                    value={String(value ?? "")}
                    onChange={(event) =>
                      onUpdateSection(
                        targetSection,
                        key,
                        fieldType === "number" ? Number(event.target.value) : event.target.value
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
            <button className="btn ghost" disabled={loading || saving} onClick={onSave}>
              {saving ? "Saving..." : activeProjectId ? "Update project" : "Save project"}
            </button>
            {step < sections.length - 1 ? (
              <button className="btn primary" disabled={loading} onClick={onNext}>
                Next
              </button>
            ) : (
              <button className="btn primary" disabled={loading} onClick={onRunAnalysis}>
                {loading ? "Running analysis..." : "Run analysis"}
              </button>
            )}
          </div>
        </div>
      ) : null}

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
            <span className="pill">AI advice</span>
            <h3>Local orchestrator output</h3>
            {results.advice?.available ? (
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
              </div>
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
