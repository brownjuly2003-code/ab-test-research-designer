import { useState } from "react";

import SidebarPanel from "./components/SidebarPanel";
import WizardPanel from "./components/WizardPanel";
import {
  apiUrl,
  buildApiPayload,
  buildCalculationPayload,
  cloneInitialState,
  type AdviceResponse,
  type ApiErrorResponse,
  type CalculationResponse,
  type ExportFormat,
  type FullPayload,
  hydrateLoadedPayload,
  stepLabels,
  type ReportResponse,
  type ResultsState,
  type SavedProject,
  validateForm
} from "./lib/experiment";

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

export default function App() {
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
  const [validationErrors, setValidationErrors] = useState<string[]>([]);

  function invalidateResults() {
    setResults((current) => (Object.keys(current).length > 0 ? {} : current));
    setStatusMessage((current) => (current ? "" : current));
    setError((current) => (current ? "" : current));
    setValidationErrors((current) => (current.length > 0 ? [] : current));
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
    setValidationErrors([]);
    setStep(0);
  }

  function ensureValidForm(): boolean {
    const issues = validateForm(form);

    if (issues.length > 0) {
      setValidationErrors(issues);
      setError("");
      setStatusMessage("");
      return false;
    }

    setValidationErrors([]);
    return true;
  }

  async function runAnalysis() {
    if (!ensureValidForm()) {
      return;
    }

    setLoading(true);
    setError("");
    setStatusMessage("");

    const payload = buildApiPayload(form);
    const calculationPayload = buildCalculationPayload(form);

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
    if (!ensureValidForm()) {
      return;
    }

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

      setForm(hydrateLoadedPayload(data.payload as FullPayload));
      setResults({});
      setActiveProjectId(typeof data.id === "string" ? data.id : projectId);
      setValidationErrors([]);
      setStatusMessage(`Loaded project ${String(data.project_name)} into the wizard.`);
      setStep(0);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected project load error");
    }
  }

  async function exportReport(format: ExportFormat) {
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
            <WizardPanel
              step={step}
              form={form}
              activeProjectId={activeProjectId}
              validationErrors={validationErrors}
              loading={loading}
              saving={saving}
              results={results}
              statusMessage={statusMessage}
              error={error}
              onUpdateSection={updateSection}
              onBack={() => setStep((currentStep) => currentStep - 1)}
              onNext={() => setStep((currentStep) => currentStep + 1)}
              onSave={saveProject}
              onStartNew={startNewProject}
              onRunAnalysis={runAnalysis}
              onExportReport={exportReport}
            />
            <SidebarPanel
              loadingProjects={loadingProjects}
              savedProjects={savedProjects}
              onLoadProjects={loadProjects}
              onLoadProject={loadProject}
            />
          </div>
        </div>
      </div>
    </>
  );
}
