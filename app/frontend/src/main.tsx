import React, { useState } from "react";
import { createRoot } from "react-dom/client";

type FullPayload = {
  project: Record<string, unknown>;
  hypothesis: Record<string, unknown>;
  setup: Record<string, unknown>;
  metrics: Record<string, unknown>;
  constraints: Record<string, unknown>;
  additional_context: Record<string, unknown>;
};

type ApiErrorResponse = {
  detail?: string;
};

type WarningItem = {
  code: string;
  message: string;
  severity: string;
  source?: string;
};

type CalculationResponse = {
  calculation_summary: Record<string, unknown>;
  results: {
    sample_size_per_variant: number;
    total_sample_size: number;
    effective_daily_traffic: number;
    estimated_duration_days: number;
  };
  assumptions: string[];
  warnings: WarningItem[];
};

type ReportResponse = {
  executive_summary: string;
  recommendations: {
    before_launch: string[];
    during_test: string[];
    after_test: string[];
  };
  open_questions: string[];
};

type AdvicePayload = {
  brief_assessment: string;
  key_risks: string[];
  design_improvements: string[];
  metric_recommendations: string[];
  interpretation_pitfalls: string[];
  additional_checks: string[];
};

type AdviceResponse = {
  available: boolean;
  provider: string;
  model: string;
  advice: AdvicePayload | null;
  raw_text: string | null;
  error: string | null;
};

type ResultsState = {
  calculations?: CalculationResponse;
  report?: ReportResponse;
  advice?: AdviceResponse;
};

type SavedProject = {
  id: string;
  project_name: string;
  created_at: string;
  updated_at: string;
};

const configuredApiBase = import.meta.env.VITE_API_BASE_URL?.trim();
const apiBase =
  configuredApiBase && configuredApiBase.length > 0
    ? configuredApiBase.replace(/\/$/, "")
    : import.meta.env.DEV
      ? "http://127.0.0.1:8008"
      : "";

function apiUrl(path: string): string {
  return `${apiBase}${path}`;
}

const styles = `
  :root {
    color-scheme: light;
    --bg: linear-gradient(160deg, #f4efe2 0%, #f8f8f4 45%, #e2ece5 100%);
    --panel: rgba(255,255,255,0.82);
    --ink: #183028;
    --muted: #5c6f67;
    --line: rgba(24,48,40,0.12);
    --accent: #0f766e;
    --accent-soft: #d7f3ee;
    --warn: #fff1d6;
    --shadow: 0 20px 50px rgba(33, 52, 45, 0.12);
    font-family: "Segoe UI", "Trebuchet MS", sans-serif;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink); }
  button, input, textarea, select { font: inherit; }
  .page { min-height: 100vh; padding: 32px 16px 48px; }
  .shell { max-width: 1200px; margin: 0 auto; display: grid; gap: 20px; }
  .hero, .panel { background: var(--panel); backdrop-filter: blur(12px); border: 1px solid var(--line); border-radius: 24px; box-shadow: var(--shadow); }
  .hero { padding: 28px; display: grid; gap: 12px; }
  .eyebrow { letter-spacing: 0.18em; text-transform: uppercase; font-size: 12px; color: var(--accent); }
  .hero h1 { margin: 0; font-size: clamp(32px, 4vw, 56px); line-height: 0.95; }
  .hero p { margin: 0; max-width: 780px; color: var(--muted); }
  .grid { display: grid; gap: 20px; grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.75fr); }
  .panel { padding: 24px; }
  .steps { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
  .step { padding: 10px 14px; border-radius: 999px; border: 1px solid var(--line); color: var(--muted); background: rgba(255,255,255,0.6); }
  .step.active { background: var(--accent); color: white; border-color: var(--accent); }
  .step.done { background: var(--accent-soft); color: var(--ink); }
  .section { display: grid; gap: 14px; }
  .section h2 { margin: 0; font-size: 22px; }
  .fields { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
  .field { display: grid; gap: 6px; }
  .field.full { grid-column: 1 / -1; }
  .field label { font-size: 14px; font-weight: 600; }
  .field input, .field textarea, .field select { width: 100%; border-radius: 14px; border: 1px solid var(--line); padding: 12px 14px; background: rgba(255,255,255,0.9); }
  .field textarea { min-height: 96px; resize: vertical; }
  .actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }
  .btn { border: none; border-radius: 999px; padding: 12px 18px; cursor: pointer; transition: transform .15s ease, opacity .15s ease; }
  .btn:hover { transform: translateY(-1px); }
  .btn.primary { background: var(--accent); color: white; }
  .btn.secondary { background: transparent; border: 1px solid var(--line); color: var(--ink); }
  .btn.ghost { background: rgba(255,255,255,0.7); color: var(--ink); }
  .meta { display: grid; gap: 12px; }
  .note, .status, .card, .result-block { border-radius: 18px; border: 1px solid var(--line); padding: 16px; background: rgba(255,255,255,0.65); }
  .status { background: var(--warn); }
  .card h3, .result-block h3 { margin: 0 0 10px; font-size: 18px; }
  .list { margin: 0; padding-left: 18px; display: grid; gap: 8px; }
  .results { display: grid; gap: 16px; }
  .two-col { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
  .muted { color: var(--muted); }
  .pill { display: inline-flex; padding: 6px 10px; border-radius: 999px; background: var(--accent-soft); font-size: 12px; font-weight: 700; color: var(--ink); }
  .error { color: #a12c2c; font-weight: 600; }
  @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } .page { padding: 18px 12px 28px; } }
`;

const stepLabels = ["Project", "Hypothesis", "Setup", "Metrics", "Constraints", "Review"];

const initialState: FullPayload = {
  project: {
    project_name: "Checkout redesign",
    domain: "e-commerce",
    product_type: "web app",
    platform: "web",
    market: "US",
    project_description: "We want to test a simplified checkout flow."
  },
  hypothesis: {
    change_description: "Reduce checkout from 4 steps to 2",
    target_audience: "new users on web",
    business_problem: "checkout abandonment is high",
    hypothesis_statement: "If we simplify checkout, purchase conversion will increase because the flow becomes easier.",
    what_to_validate: "impact on conversion",
    desired_result: "statistically meaningful uplift"
  },
  setup: {
    experiment_type: "ab",
    randomization_unit: "user",
    traffic_split: "50,50",
    expected_daily_traffic: 12000,
    audience_share_in_test: 0.6,
    variants_count: 2,
    inclusion_criteria: "new users only",
    exclusion_criteria: "internal staff"
  },
  metrics: {
    primary_metric_name: "purchase_conversion",
    metric_type: "binary",
    baseline_value: 0.042,
    expected_uplift_pct: 8,
    mde_pct: 5,
    alpha: 0.05,
    power: 0.8,
    std_dev: ""
  },
  constraints: {
    seasonality_present: true,
    active_campaigns_present: false,
    returning_users_present: true,
    interference_risk: "medium",
    technical_constraints: "legacy event logging",
    legal_or_ethics_constraints: "none",
    known_risks: "tracking quality",
    deadline_pressure: "medium",
    long_test_possible: true
  },
  additional_context: {
    llm_context: "Previous tests showed mixed results. Team worries about event quality and segmentation."
  }
};

function cloneInitialState(): FullPayload {
  return structuredClone(initialState) as FullPayload;
}

function parseTrafficSplit(raw: unknown): number[] {
  if (Array.isArray(raw)) return raw.map(Number);
  return String(raw)
    .split(",")
    .map((value) => Number(value.trim()))
    .filter((value) => !Number.isNaN(value) && value > 0);
}

function buildApiPayload(state: FullPayload): FullPayload {
  return {
    ...state,
    setup: {
      ...state.setup,
      traffic_split: parseTrafficSplit(state.setup.traffic_split)
    },
    metrics: {
      ...state.metrics,
      std_dev: state.metrics.std_dev === "" ? null : Number(state.metrics.std_dev)
    }
  };
}

function App() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FullPayload>(cloneInitialState);
  const [results, setResults] = useState<ResultsState>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [savedProjects, setSavedProjects] = useState<SavedProject[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);

  function invalidateResults() {
    setResults((current) => (Object.keys(current).length > 0 ? {} : current));
    setStatusMessage((current) => (current ? "" : current));
  }

  function updateSection(section: keyof FullPayload, key: string, value: unknown) {
    setForm((current) => ({
      ...current,
      [section]: {
        ...current[section],
        [key]: value
      }
    }));
    invalidateResults();
  }

  function startNewProject() {
    setForm(cloneInitialState());
    setResults({});
    setError("");
    setStatusMessage("Started a new local draft.");
    setActiveProjectId(null);
    setStep(0);
  }

  async function runAnalysis() {
    setLoading(true);
    setError("");
    setStatusMessage("");

    const payload = buildApiPayload(form);
    const calculationPayload = {
      metric_type: payload.metrics.metric_type,
      baseline_value: payload.metrics.baseline_value,
      std_dev: payload.metrics.std_dev,
      mde_pct: payload.metrics.mde_pct,
      alpha: payload.metrics.alpha,
      power: payload.metrics.power,
      expected_daily_traffic: payload.setup.expected_daily_traffic,
      audience_share_in_test: payload.setup.audience_share_in_test,
      traffic_split: payload.setup.traffic_split,
      variants_count: payload.setup.variants_count,
      seasonality_present: payload.constraints.seasonality_present,
      active_campaigns_present: payload.constraints.active_campaigns_present,
      long_test_possible: payload.constraints.long_test_possible
    };

    try {
      const [calculationsRes, reportRes, adviceRes] = await Promise.all([
        fetch(apiUrl("/api/v1/calculate"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(calculationPayload)
        }),
        fetch(apiUrl("/api/v1/design"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        }),
        fetch(apiUrl("/api/v1/llm/advice"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_context: payload.project,
            hypothesis: payload.hypothesis,
            setup: payload.setup,
            metrics: payload.metrics,
            constraints: payload.constraints,
            additional_context: payload.additional_context
          })
        })
      ]);

      const calculations = await calculationsRes.json() as CalculationResponse | ApiErrorResponse;
      const report = await reportRes.json() as ReportResponse | ApiErrorResponse;
      const advice = await adviceRes.json() as AdviceResponse;

      if (!calculationsRes.ok) {
        const calculationError = calculations as ApiErrorResponse;
        throw new Error(typeof calculationError.detail === "string" ? calculationError.detail : "Calculation request failed");
      }
      if (!reportRes.ok) {
        const reportError = report as ApiErrorResponse;
        throw new Error(typeof reportError.detail === "string" ? reportError.detail : "Design request failed");
      }

      setResults({
        calculations: calculations as CalculationResponse,
        report: report as ReportResponse,
        advice
      });
      setStep(stepLabels.length - 1);
      setStatusMessage("Analysis completed. Deterministic output and optional AI advice are shown below.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected request error");
    } finally {
      setLoading(false);
    }
  }

  async function saveProject() {
    setSaving(true);
    setError("");
    setStatusMessage("");

    try {
      const isUpdate = activeProjectId !== null;
      const response = await fetch(
        isUpdate ? apiUrl(`/api/v1/projects/${activeProjectId}`) : apiUrl("/api/v1/projects"),
        {
          method: isUpdate ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildApiPayload(form))
        }
      );
      const data = await response.json();

      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Project save failed");
      }

      setActiveProjectId(typeof data.id === "string" ? data.id : activeProjectId);
      setStatusMessage(
        isUpdate
          ? `Project ${String(data.project_name)} updated locally.`
          : `Project saved locally with id ${String(data.id)}.`
      );
      await loadProjects();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected save error");
    } finally {
      setSaving(false);
    }
  }

  async function loadProjects() {
    setLoadingProjects(true);
    setError("");

    try {
      const response = await fetch(apiUrl("/api/v1/projects"));
      const data = await response.json();

      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Project list request failed");
      }

      setSavedProjects(Array.isArray(data.projects) ? data.projects : []);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected project list error");
    } finally {
      setLoadingProjects(false);
    }
  }

  async function loadProject(projectId: string) {
    setError("");
    setStatusMessage("");

    try {
      const response = await fetch(apiUrl(`/api/v1/projects/${projectId}`));
      const data = await response.json();

      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Project load failed");
      }

      const payload = data.payload as FullPayload;
      setForm({
        ...payload,
        setup: {
          ...payload.setup,
          traffic_split: Array.isArray(payload.setup.traffic_split)
            ? payload.setup.traffic_split.join(",")
            : String(payload.setup.traffic_split ?? "")
        },
        metrics: {
          ...payload.metrics,
          std_dev:
            payload.metrics.std_dev === null || payload.metrics.std_dev === undefined
              ? ""
              : String(payload.metrics.std_dev)
        }
      });
      setResults({});
      setActiveProjectId(typeof data.id === "string" ? data.id : projectId);
      setStatusMessage(`Loaded project ${String(data.project_name)} into the wizard.`);
      setStep(0);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected project load error");
    }
  }

  async function exportReport(format: "markdown" | "html") {
    if (!results.report) {
      setError("Run analysis before exporting a report.");
      return;
    }

    setError("");
    setStatusMessage("");

    try {
      const response = await fetch(apiUrl(`/api/v1/export/${format}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(results.report)
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "Export failed");
      }

      const extension = format === "markdown" ? "md" : "html";
      const blob = new Blob([String(data.content)], { type: format === "markdown" ? "text/markdown" : "text/html" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `experiment-report.${extension}`;
      anchor.click();
      URL.revokeObjectURL(url);
      setStatusMessage(`Exported report as ${extension.toUpperCase()}.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected export error");
    }
  }

  const sections = [
    {
      title: "Project context",
      section: "project" as const,
      fields: [
        ["Project name", "project_name"],
        ["Domain", "domain"],
        ["Product type", "product_type"],
        ["Platform", "platform"],
        ["Market", "market"],
        ["Project description", "project_description", "textarea"]
      ]
    },
    {
      title: "Hypothesis",
      section: "hypothesis" as const,
      fields: [
        ["Change description", "change_description"],
        ["Target audience", "target_audience"],
        ["Business problem", "business_problem"],
        ["Hypothesis statement", "hypothesis_statement", "textarea"],
        ["What to validate", "what_to_validate"],
        ["Desired result", "desired_result"]
      ]
    },
    {
      title: "Experiment setup",
      section: "setup" as const,
      fields: [
        ["Experiment type", "experiment_type"],
        ["Randomization unit", "randomization_unit"],
        ["Traffic split", "traffic_split"],
        ["Expected daily traffic", "expected_daily_traffic", "number"],
        ["Audience share in test", "audience_share_in_test", "number"],
        ["Variants count", "variants_count", "number"],
        ["Inclusion criteria", "inclusion_criteria"],
        ["Exclusion criteria", "exclusion_criteria"]
      ]
    },
    {
      title: "Metrics",
      section: "metrics" as const,
      fields: [
        ["Primary metric", "primary_metric_name"],
        ["Metric type", "metric_type"],
        ["Baseline value", "baseline_value", "number"],
        ["Expected uplift %", "expected_uplift_pct", "number"],
        ["MDE %", "mde_pct", "number"],
        ["Alpha", "alpha", "number"],
        ["Power", "power", "number"],
        ["Std dev", "std_dev", "number"]
      ]
    },
    {
      title: "Constraints",
      section: "constraints" as const,
      fields: [
        ["Seasonality present", "seasonality_present", "boolean"],
        ["Active campaigns present", "active_campaigns_present", "boolean"],
        ["Returning users present", "returning_users_present", "boolean"],
        ["Interference risk", "interference_risk"],
        ["Technical constraints", "technical_constraints"],
        ["Known risks", "known_risks"],
        ["Long test possible", "long_test_possible", "boolean"],
        ["AI context", "llm_context", "textarea", "additional_context"]
      ]
    }
  ];

  const current = sections[Math.min(step, sections.length - 1)];

  return (
    <>
      <style>{styles}</style>
      <div className="page">
        <div className="shell">
          <section className="hero">
            <span className="eyebrow">Local Experiment Planner</span>
            <h1>AB Test Research Designer</h1>
            <p>
              Fill in experiment context, run deterministic calculations, inspect warnings, and keep AI advice separate
              from hard math.
            </p>
          </section>

          <div className="grid">
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
                  <div className="fields">
                    {current.fields.map(([label, key, kind, explicitSection]) => {
                      const targetSection = (explicitSection as keyof FullPayload | undefined) ?? current.section;
                      const value = form[targetSection][key as keyof typeof form[typeof targetSection]];
                      const fieldType = kind ?? "text";

                      if (fieldType === "textarea") {
                        return (
                          <div key={key as string} className="field full">
                            <label>{label}</label>
                            <textarea value={String(value ?? "")} onChange={(event) => updateSection(targetSection, key as string, event.target.value)} />
                          </div>
                        );
                      }

                      if (fieldType === "boolean") {
                        return (
                          <div key={key as string} className="field">
                            <label>{label}</label>
                            <select value={String(value)} onChange={(event) => updateSection(targetSection, key as string, event.target.value === "true")}>
                              <option value="true">Yes</option>
                              <option value="false">No</option>
                            </select>
                          </div>
                        );
                      }

                      return (
                        <div key={key as string} className={`field ${label.includes("description") || label.includes("constraints") ? "full" : ""}`}>
                          <label>{label}</label>
                          <input
                            type={fieldType === "number" ? "number" : "text"}
                            step={fieldType === "number" ? "any" : undefined}
                            value={String(value ?? "")}
                            onChange={(event) =>
                              updateSection(
                                targetSection,
                                key as string,
                                fieldType === "number" ? Number(event.target.value) : event.target.value
                              )
                            }
                          />
                        </div>
                      );
                    })}
                  </div>

                  <div className="actions">
                    <button className="btn secondary" disabled={step === 0 || loading} onClick={() => setStep((currentStep) => currentStep - 1)}>
                      Back
                    </button>
                    <button className="btn ghost" disabled={loading || saving} onClick={startNewProject}>
                      New draft
                    </button>
                    <button className="btn ghost" disabled={loading || saving} onClick={saveProject}>
                      {saving ? "Saving..." : activeProjectId ? "Update project" : "Save project"}
                    </button>
                    {step < sections.length - 1 ? (
                      <button className="btn primary" disabled={loading} onClick={() => setStep((currentStep) => currentStep + 1)}>
                        Next
                      </button>
                    ) : (
                      <button className="btn primary" disabled={loading} onClick={runAnalysis}>
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
                        results.calculations?.warnings.map((warning) => (
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
                      <button className="btn ghost" onClick={() => exportReport("markdown")}>
                        Export Markdown
                      </button>
                      <button className="btn ghost" onClick={() => exportReport("html")}>
                        Export HTML
                      </button>
                    </div>
                    <div className="two-col">
                      <div className="card">
                        <h3>Before launch</h3>
                        <ul className="list">
                          {(results.report.recommendations?.before_launch ?? []).map((item: unknown) => (
                            <li key={String(item)}>{String(item)}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="card">
                        <h3>Open questions</h3>
                        <ul className="list">
                          {(results.report.open_questions ?? []).map((item: unknown) => (
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
                            {(results.advice.advice?.design_improvements ?? []).map((item: unknown) => (
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

            <aside className="panel meta">
              <div className="note">
                <h3>How this UI is split</h3>
                <ul className="list">
                  <li>Deterministic calculations come from `/api/v1/calculate`.</li>
                  <li>Warnings come from the rules engine layered on top of deterministic inputs.</li>
                  <li>AI advice is optional and pulled separately from the local orchestrator.</li>
                </ul>
              </div>
              <div className="card">
                <div className="actions">
                  <button className="btn ghost" disabled={loadingProjects} onClick={loadProjects}>
                    {loadingProjects ? "Loading..." : "Load saved projects"}
                  </button>
                </div>
                <h3>Saved projects</h3>
                {savedProjects.length > 0 ? (
                  <ul className="list">
                    {savedProjects.map((project) => (
                      <li key={project.id}>
                        <button className="btn ghost" onClick={() => loadProject(project.id)}>
                          {project.project_name}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No saved projects loaded yet.</p>
                )}
              </div>
              <div className="card">
                <h3>Current phase</h3>
                <p className="muted">
                  Use the wizard to define experiment context first. Results stay visible below the form after the run.
                </p>
              </div>
              <div className="card">
                <h3>Backend endpoints</h3>
                <ul className="list">
                  <li>`POST /api/v1/calculate`</li>
                  <li>`POST /api/v1/design`</li>
                  <li>`POST /api/v1/llm/advice`</li>
                  <li>`GET/POST/PUT /api/v1/projects`</li>
                </ul>
              </div>
            </aside>
          </div>
        </div>
      </div>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
