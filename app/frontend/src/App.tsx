import { useEffect, useRef, useState, type ChangeEvent } from "react";

import SidebarPanel from "./components/SidebarPanel";
import WizardPanel from "./components/WizardPanel";
import {
  type AnalysisResponse,
  compareProjectsRequest,
  deleteProjectRequest,
  exportReportRequest,
  listProjectsRequest,
  loadProjectHistoryRequest,
  loadProjectRequest,
  recordProjectAnalysisRequest,
  recordProjectExportRequest,
  requestHealth,
  requestAnalysis,
  saveProjectRequest
} from "./lib/api";
import {
  buildApiPayload,
  buildDraftTransferFile,
  browserDraftStorageKey,
  type ApiHealthResponse,
  cloneInitialState,
  type DraftFieldValue,
  type ExportFormat,
  type FullPayload,
  type FullPayloadSectionKey,
  hydrateLoadedPayload,
  parseImportedDraft,
  type ProjectAnalysisRun,
  type ProjectComparison,
  type ProjectHistory,
  type SavedProject,
  setSectionFieldValue,
  stepLabels,
  type ResultsState,
  validateForm
} from "./lib/experiment";

const initialProjectHistoryWindow = {
  analysisLimit: 3,
  exportLimit: 3
};

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
  const [draftBootstrap] = useState(() => {
    const fallback = { form: cloneInitialState(), restored: false };

    if (typeof window === "undefined") {
      return fallback;
    }

    try {
      const storedDraft = window.localStorage.getItem(browserDraftStorageKey);
      if (!storedDraft) {
        return fallback;
      }

      return {
        form: parseImportedDraft(storedDraft),
        restored: true
      };
    } catch {
      try {
        window.localStorage.removeItem(browserDraftStorageKey);
      } catch {
        // Ignore storage cleanup failures and fall back to the built-in initial draft.
      }
      return fallback;
    }
  });
  const draftImportRef = useRef<HTMLInputElement | null>(null);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FullPayload>(draftBootstrap.form);
  const [results, setResults] = useState<ResultsState>({});
  const [importingDraft, setImportingDraft] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [backendHealth, setBackendHealth] = useState<ApiHealthResponse | null>(null);
  const [healthError, setHealthError] = useState("");
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [savedProjects, setSavedProjects] = useState<SavedProject[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [savedProjectSnapshot, setSavedProjectSnapshot] = useState<string | null>(null);
  const [projectHistory, setProjectHistory] = useState<ProjectHistory | null>(null);
  const [projectHistoryError, setProjectHistoryError] = useState("");
  const [loadingProjectHistory, setLoadingProjectHistory] = useState(false);
  const [projectHistoryWindow, setProjectHistoryWindow] = useState(initialProjectHistoryWindow);
  const [selectedHistoryRunId, setSelectedHistoryRunId] = useState<string | null>(null);
  const [projectComparison, setProjectComparison] = useState<ProjectComparison | null>(null);
  const [projectComparisonError, setProjectComparisonError] = useState("");
  const [loadingProjectComparison, setLoadingProjectComparison] = useState(false);
  const [comparingProjectId, setComparingProjectId] = useState<string | null>(null);
  const [resultsProjectId, setResultsProjectId] = useState<string | null>(null);
  const [resultsAnalysisRunId, setResultsAnalysisRunId] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const lastStepIndex = stepLabels.length - 1;
  const serializedForm = JSON.stringify(buildApiPayload(form));
  const hasUnsavedChanges =
    activeProjectId !== null && savedProjectSnapshot !== null && savedProjectSnapshot !== serializedForm;
  const activeProject =
    activeProjectId !== null
      ? savedProjects.find((project) => project.id === activeProjectId) ?? null
      : null;
  const selectedHistoryRun =
    selectedHistoryRunId && projectHistory
      ? projectHistory.analysis_runs.find((run) => run.id === selectedHistoryRunId) ?? null
      : null;

  function toSavedProject(project: {
    id?: string;
    project_name?: string;
    created_at?: string;
    updated_at?: string;
    payload_schema_version?: number;
    last_analysis_at?: string | null;
    last_analysis_run_id?: string | null;
    last_exported_at?: string | null;
    has_analysis_snapshot?: boolean;
  }): SavedProject | null {
    if (
      typeof project.id !== "string" ||
      typeof project.project_name !== "string" ||
      typeof project.created_at !== "string" ||
      typeof project.updated_at !== "string"
    ) {
      return null;
    }

    return {
      id: project.id,
      project_name: project.project_name,
      created_at: project.created_at,
      updated_at: project.updated_at,
      payload_schema_version: project.payload_schema_version ?? 1,
      last_analysis_at: project.last_analysis_at ?? null,
      last_analysis_run_id: project.last_analysis_run_id ?? null,
      last_exported_at: project.last_exported_at ?? null,
      has_analysis_snapshot: project.has_analysis_snapshot ?? false
    };
  }

  function getPersistableAnalysis(state: ResultsState): AnalysisResponse | null {
    if (!state.calculations || !state.report || !state.advice) {
      return null;
    }

    return {
      calculations: state.calculations,
      report: state.report,
      advice: state.advice
    };
  }

  function getDisplayedAnalysis(state: ResultsState, historyRun: ProjectAnalysisRun | null): AnalysisResponse | null {
    if (historyRun) {
      return historyRun.analysis;
    }

    return getPersistableAnalysis(state);
  }

  function upsertSavedProject(project: SavedProject) {
    setSavedProjects((current) =>
      [project, ...current.filter((candidate) => candidate.id !== project.id)].sort((left, right) =>
        right.updated_at.localeCompare(left.updated_at)
      )
    );
  }

  function invalidateResults() {
    setSelectedHistoryRunId(null);
    setResultsProjectId(null);
    setResultsAnalysisRunId(null);
    setResults((current) => (Object.keys(current).length > 0 ? {} : current));
    setStatusMessage((current) => (current ? "" : current));
    setError((current) => (current ? "" : current));
    setValidationErrors((current) => (current.length > 0 ? [] : current));
  }

  function clearProjectComparison() {
    setProjectComparison(null);
    setProjectComparisonError("");
    setLoadingProjectComparison(false);
    setComparingProjectId(null);
  }

  function updateSection(section: FullPayloadSectionKey, key: string, value: DraftFieldValue) {
    setForm((current) => setSectionFieldValue(current, section, key, value));
    invalidateResults();
  }

  function startNewProject() {
    setForm(cloneInitialState());
    setResults({});
    setResultsProjectId(null);
    setResultsAnalysisRunId(null);
    setError("");
    setStatusMessage("Started a new local draft.");
    setActiveProjectId(null);
    setSavedProjectSnapshot(null);
    setLoadingProjectHistory(false);
    setProjectHistory(null);
    setProjectHistoryWindow(initialProjectHistoryWindow);
    setProjectHistoryError("");
    setSelectedHistoryRunId(null);
    clearProjectComparison();
    setValidationErrors([]);
    setStep(0);
  }

  function exportDraft() {
    setError("");
    const safeName = String(form.project.project_name ?? "experiment-draft")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "experiment-draft";
    const content = JSON.stringify(buildDraftTransferFile(form), null, 2);
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${safeName}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setStatusMessage("Draft exported as JSON.");
  }

  function openImportDraft() {
    draftImportRef.current?.click();
  }

  async function importDraftFromFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    setImportingDraft(true);
    setError("");

    try {
      const imported = parseImportedDraft(await file.text());
      setForm(imported);
      setResults({});
      setResultsProjectId(null);
      setResultsAnalysisRunId(null);
      setActiveProjectId(null);
      setSavedProjectSnapshot(null);
      setLoadingProjectHistory(false);
      setProjectHistory(null);
      setProjectHistoryWindow(initialProjectHistoryWindow);
      setProjectHistoryError("");
      setSelectedHistoryRunId(null);
      clearProjectComparison();
      setValidationErrors([]);
      setStatusMessage(`Imported draft from ${file.name}. Save it to create a new local project record.`);
      setStep(0);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected draft import error");
    } finally {
      event.target.value = "";
      setImportingDraft(false);
    }
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

  useEffect(() => {
    if (draftBootstrap.restored) {
      setStatusMessage("Restored unsaved browser draft.");
    }
  }, [draftBootstrap.restored]);

  useEffect(() => {
    try {
      window.localStorage.setItem(browserDraftStorageKey, JSON.stringify(buildDraftTransferFile(form)));
    } catch {
      // Ignore localStorage persistence failures and keep the in-memory draft usable.
    }
  }, [form]);

  useEffect(() => {
    void loadBackendHealth();
    void loadProjects();
  }, []);

  useEffect(() => {
    if (selectedHistoryRunId && projectHistory && !projectHistory.analysis_runs.some((run) => run.id === selectedHistoryRunId)) {
      setSelectedHistoryRunId(null);
    }
  }, [projectHistory, selectedHistoryRunId]);

  async function loadBackendHealth() {
    setLoadingHealth(true);

    try {
      setBackendHealth(await requestHealth());
      setHealthError("");
    } catch (requestError) {
      setBackendHealth(null);
      setHealthError(requestError instanceof Error ? requestError.message : "Unexpected backend health error");
    } finally {
      setLoadingHealth(false);
    }
  }

  async function refreshProjectHistory(
    projectId: string,
    silent = false,
    overrides?: Partial<typeof initialProjectHistoryWindow>
  ) {
    const nextWindow = {
      analysisLimit: overrides?.analysisLimit ?? projectHistoryWindow.analysisLimit,
      exportLimit: overrides?.exportLimit ?? projectHistoryWindow.exportLimit
    };

    if (overrides) {
      setProjectHistoryWindow(nextWindow);
    }
    if (!silent) {
      setLoadingProjectHistory(true);
    }
    setProjectHistoryError("");

    try {
      setProjectHistory(
        await loadProjectHistoryRequest(projectId, {
          analysisLimit: nextWindow.analysisLimit,
          exportLimit: nextWindow.exportLimit
        })
      );
    } catch (requestError) {
      setProjectHistory(null);
      setProjectHistoryError(requestError instanceof Error ? requestError.message : "Unexpected project history error");
    } finally {
      if (!silent) {
        setLoadingProjectHistory(false);
      }
    }
  }

  async function compareProject(candidateProjectId: string) {
    if (!activeProjectId) {
      return;
    }

    const candidateName = savedProjects.find((project) => project.id === candidateProjectId)?.project_name ?? candidateProjectId;
    setLoadingProjectComparison(true);
    setComparingProjectId(candidateProjectId);
    setProjectComparisonError("");

    try {
      const comparison = await compareProjectsRequest(
        activeProjectId,
        candidateProjectId,
        selectedHistoryRunId ?? undefined
      );
      setProjectComparison(comparison);
      setStatusMessage(`Loaded saved-project comparison against ${candidateName}.`);
    } catch (requestError) {
      setProjectComparison(null);
      setProjectComparisonError(
        requestError instanceof Error ? requestError.message : "Unexpected project comparison error"
      );
    } finally {
      setLoadingProjectComparison(false);
      setComparingProjectId(null);
    }
  }

  async function runAnalysis() {
    if (!ensureValidForm()) {
      return;
    }

    const snapshotEligibleProjectId = activeProjectId !== null && !hasUnsavedChanges ? activeProjectId : null;
    setSelectedHistoryRunId(null);
    clearProjectComparison();
    setLoading(true);
    setError("");
    setStatusMessage("");

    try {
      const analysis = await requestAnalysis(form);
      setResults(analysis);
      setResultsProjectId(snapshotEligibleProjectId);
      setResultsAnalysisRunId(null);
      setStep(lastStepIndex);

      if (snapshotEligibleProjectId) {
        try {
          const updatedProject = await recordProjectAnalysisRequest(snapshotEligibleProjectId, analysis);
          const savedProject = toSavedProject(updatedProject);
          if (savedProject) {
            upsertSavedProject(savedProject);
          }
          setResultsAnalysisRunId(updatedProject.last_analysis_run_id ?? null);
          await refreshProjectHistory(snapshotEligibleProjectId, true);
          setStatusMessage("Analysis completed and the latest snapshot was recorded for this saved project.");
        } catch (metadataError) {
          setStatusMessage("Analysis completed, but project snapshot metadata could not be persisted.");
          setError(metadataError instanceof Error ? metadataError.message : "Unexpected analysis snapshot error");
        }
      } else if (activeProjectId) {
        setStatusMessage("Analysis completed for draft changes. Save the project to persist this analysis snapshot.");
      } else {
        setStatusMessage("Analysis completed. Deterministic output and optional AI advice are shown below.");
      }
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

    setSelectedHistoryRunId(null);
    setSaving(true);
    setError("");
    setStatusMessage("");

    try {
      const isUpdate = activeProjectId !== null;
      const normalizedPayload = buildApiPayload(form);
      const persistedAnalysis = getPersistableAnalysis(results);
      const data = await saveProjectRequest(form, activeProjectId);
      const savedProjectId = typeof data.id === "string" ? data.id : activeProjectId;
      let savedProject = toSavedProject(data);
      let saveStatus = isUpdate
        ? `Project ${String(data.project_name)} updated locally.`
        : `Project saved locally with id ${String(data.id)}.`;

      setActiveProjectId(savedProjectId);
      setSavedProjectSnapshot(
        data.payload ? JSON.stringify(data.payload) : JSON.stringify(normalizedPayload)
      );
      if (savedProjectId) {
        setResultsProjectId(savedProjectId);
      }

      if (savedProjectId && persistedAnalysis && resultsAnalysisRunId === null) {
        try {
          const updatedProject = await recordProjectAnalysisRequest(savedProjectId, persistedAnalysis);
          savedProject = toSavedProject(updatedProject) ?? savedProject;
          setResultsAnalysisRunId(updatedProject.last_analysis_run_id ?? null);
          saveStatus = `${saveStatus} Latest analysis snapshot was recorded for this saved project.`;
        } catch (metadataError) {
          setError(metadataError instanceof Error ? metadataError.message : "Unexpected analysis snapshot save error");
          saveStatus = `${saveStatus} Current analysis is still local until the snapshot is recorded.`;
        }
      }

      if (savedProject) {
        upsertSavedProject(savedProject);
      } else {
        await loadProjects();
      }
      if (savedProjectId) {
        await refreshProjectHistory(savedProjectId, true);
      }
      clearProjectComparison();

      setStatusMessage(saveStatus);
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
      setSavedProjects(await listProjectsRequest());
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
      const data = await loadProjectRequest(projectId);
      const savedProject = toSavedProject(data);

      setForm(hydrateLoadedPayload(data.payload));
      setResults({});
      setResultsProjectId(null);
      setResultsAnalysisRunId(null);
      setActiveProjectId(typeof data.id === "string" ? data.id : projectId);
      setSavedProjectSnapshot(JSON.stringify(data.payload));
      setProjectHistory(null);
      setProjectHistoryWindow(initialProjectHistoryWindow);
      setProjectHistoryError("");
      setSelectedHistoryRunId(null);
      clearProjectComparison();
      setValidationErrors([]);
      if (savedProject) {
        upsertSavedProject(savedProject);
      }
      await refreshProjectHistory(typeof data.id === "string" ? data.id : projectId, false, initialProjectHistoryWindow);
      setStatusMessage(`Loaded project ${String(data.project_name)} into the wizard.`);
      setStep(0);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected project load error");
    }
  }

  async function deleteProject(projectId: string, projectName: string) {
    if (!window.confirm(`Delete project "${projectName}" from local storage?`)) {
      return;
    }

    setDeletingProjectId(projectId);
    setError("");
    setStatusMessage("");

    try {
      await deleteProjectRequest(projectId);
      setSavedProjects((current) => current.filter((project) => project.id !== projectId));

      if (activeProjectId === projectId) {
        setActiveProjectId(null);
        setSavedProjectSnapshot(null);
        setResultsProjectId(null);
        setProjectHistory(null);
        setProjectHistoryWindow(initialProjectHistoryWindow);
        setProjectHistoryError("");
        setLoadingProjectHistory(false);
        setSelectedHistoryRunId(null);
        setResultsAnalysisRunId(null);
        clearProjectComparison();
        setStatusMessage(`Project ${projectName} deleted. Current form remains as a new local draft.`);
      } else {
        setStatusMessage(`Project ${projectName} deleted locally.`);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected project delete error");
    } finally {
      setDeletingProjectId(null);
    }
  }

  async function exportReport(format: ExportFormat) {
    const displayedAnalysis = getDisplayedAnalysis(results, selectedHistoryRun);

    if (!displayedAnalysis?.report) {
      setError("Run analysis before exporting a report.");
      return;
    }

    setError("");
    setStatusMessage("");

    try {
      const extension = format === "markdown" ? "md" : "html";
      const content = await exportReportRequest(displayedAnalysis.report, format);
      const blob = new Blob([content], { type: format === "markdown" ? "text/markdown" : "text/html" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `experiment-report.${extension}`;
      anchor.click();
      URL.revokeObjectURL(url);

      const exportProjectId = selectedHistoryRun?.project_id ?? resultsProjectId;

      if (exportProjectId) {
        try {
          const linkedAnalysisRunId =
            selectedHistoryRun?.id ??
            resultsAnalysisRunId ??
            (activeProjectId === exportProjectId ? activeProject?.last_analysis_run_id ?? null : null);
          const updatedProject = await recordProjectExportRequest(exportProjectId, format, linkedAnalysisRunId);
          const savedProject = toSavedProject(updatedProject);
          if (savedProject) {
            upsertSavedProject(savedProject);
          }
          await refreshProjectHistory(exportProjectId, true);
          setStatusMessage(`Exported report as ${extension.toUpperCase()} and updated project export metadata.`);
        } catch (metadataError) {
          setStatusMessage(`Exported report as ${extension.toUpperCase()}, but project export metadata was not updated.`);
          setError(metadataError instanceof Error ? metadataError.message : "Unexpected export metadata error");
        }
      } else {
        setStatusMessage(`Exported report as ${extension.toUpperCase()}.`);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unexpected export error");
    }
  }

  function openHistoryRun(runId: string) {
    if (!projectHistory) {
      return;
    }

    const targetRun = projectHistory.analysis_runs.find((run) => run.id === runId);
    if (!targetRun) {
      return;
    }

    setSelectedHistoryRunId(targetRun.id);
    clearProjectComparison();
    setStatusMessage("Opened a saved analysis snapshot from project history.");
    setError("");
    setStep(lastStepIndex);
  }

  function clearHistoryRunSelection() {
    if (!selectedHistoryRunId) {
      return;
    }

    setSelectedHistoryRunId(null);
    setStatusMessage(
      results.report
        ? "Returned to the current in-memory analysis results."
        : "Closed the saved snapshot preview."
    );
    setError("");
  }

  const displayedAnalysis = getDisplayedAnalysis(results, selectedHistoryRun);

  return (
    <>
      <input
        ref={draftImportRef}
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        aria-label="Import draft file"
        onChange={importDraftFromFile}
      />
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
              hasUnsavedChanges={hasUnsavedChanges}
              validationErrors={validationErrors}
              importingDraft={importingDraft}
              loading={loading}
              saving={saving}
              results={results}
              activeProject={activeProject}
              projectHistory={projectHistory}
              selectedHistoryRun={selectedHistoryRun}
              projectComparison={projectComparison}
              loadingProjectHistory={loadingProjectHistory}
              statusMessage={statusMessage}
              error={error}
              displayedAnalysis={displayedAnalysis}
              onUpdateSection={updateSection}
              onBack={() => setStep((currentStep) => Math.max(0, currentStep - 1))}
              onNext={() => setStep((currentStep) => Math.min(lastStepIndex, currentStep + 1))}
              onSave={saveProject}
              onStartNew={startNewProject}
              onImportDraft={openImportDraft}
              onExportDraft={exportDraft}
              onRunAnalysis={runAnalysis}
              onClearHistorySelection={clearHistoryRunSelection}
              onExportReport={exportReport}
            />
            <SidebarPanel
              loadingHealth={loadingHealth}
              loadingProjects={loadingProjects}
              deletingProjectId={deletingProjectId}
              backendHealth={backendHealth}
              healthError={healthError}
              savedProjects={savedProjects}
              activeProjectId={activeProjectId}
              activeProject={activeProject}
              projectHistory={projectHistory}
              projectHistoryError={projectHistoryError}
              loadingProjectHistory={loadingProjectHistory}
              selectedHistoryRunId={selectedHistoryRunId}
              projectComparison={projectComparison}
              projectComparisonError={projectComparisonError}
              loadingProjectComparison={loadingProjectComparison}
              comparingProjectId={comparingProjectId}
              hasUnsavedChanges={hasUnsavedChanges}
              onRefreshHealth={loadBackendHealth}
              onRefreshProjectHistory={(projectId) => {
                void refreshProjectHistory(projectId);
              }}
              onLoadMoreAnalysisHistory={(projectId) => {
                void refreshProjectHistory(projectId, false, {
                  analysisLimit: projectHistoryWindow.analysisLimit + 5
                });
              }}
              onLoadMoreExportHistory={(projectId) => {
                void refreshProjectHistory(projectId, false, {
                  exportLimit: projectHistoryWindow.exportLimit + 5
                });
              }}
              onOpenHistoryRun={openHistoryRun}
              onClearHistoryRunSelection={clearHistoryRunSelection}
              onCompareProject={(projectId) => {
                void compareProject(projectId);
              }}
              onLoadProjects={loadProjects}
              onLoadProject={loadProject}
              onDeleteProject={deleteProject}
            />
          </div>
        </div>
      </div>
    </>
  );
}
