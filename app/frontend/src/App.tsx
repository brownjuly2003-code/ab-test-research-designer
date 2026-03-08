import { useEffect, useRef, useState, type ChangeEvent } from "react";

import "./App.css";
import Icon from "./components/Icon";
import SidebarPanel from "./components/SidebarPanel";
import WizardPanel from "./components/WizardPanel";
import {
  exportWorkspaceRequest,
  exportReportRequest,
  importWorkspaceRequest,
  recordProjectAnalysisRequest,
  recordProjectExportRequest,
  requestAnalysis,
  saveProjectRequest,
  validateWorkspaceRequest
} from "./lib/api";
import {
  buildApiPayload,
  buildDraftTransferFile,
  cloneInitialState,
  type ExportFormat,
  type FullPayload,
  type WorkspaceBundleInput,
  hydrateLoadedPayload,
  setSectionFieldValue,
  stepLabels
} from "./lib/experiment";
import { useAnalysis } from "./hooks/useAnalysis";
import { readDraftBootstrap, useDraftPersistence } from "./hooks/useDraftPersistence";
import { useProjectManager } from "./hooks/useProjectManager";

export default function App() {
  const [draftBootstrap] = useState(readDraftBootstrap);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FullPayload>(draftBootstrap.form);
  const [importingDraft, setImportingDraft] = useState(false);
  const [importingWorkspace, setImportingWorkspace] = useState(false);
  const [exportingWorkspace, setExportingWorkspace] = useState(false);
  const draftImportRef = useRef<HTMLInputElement | null>(null);
  const workspaceImportRef = useRef<HTMLInputElement | null>(null);
  const serializedForm = JSON.stringify(buildApiPayload(form));
  const analysis = useAnalysis();
  const projectManager = useProjectManager(serializedForm);
  const { draftStorageWarning, clearDraftStorageWarning, parseImportedDraftText } = useDraftPersistence(form, draftBootstrap.warning);
  const lastStepIndex = stepLabels.length - 1;
  const displayedAnalysis =
    projectManager.selectedHistoryRun?.analysis ?? analysis.getPersistableAnalysis();
  const uiError = analysis.error;

  useEffect(() => {
    if (draftBootstrap.restored) {
      analysis.setStatusMessage("Restored unsaved browser draft.");
    }
  }, [draftBootstrap.restored]);

  useEffect(() => {
    void projectManager.loadBackendHealth();
    void projectManager.loadBackendDiagnostics();
    void loadProjects();
  }, []);

  function updateSection(section: keyof FullPayload, key: string, value: string | number | boolean | null) {
    setForm((current) => setSectionFieldValue(current, section, key, value));
    projectManager.setSelectedHistoryRunId(null);
    analysis.invalidateResults();
  }

  function startNewProject() {
    setForm(cloneInitialState());
    analysis.resetAnalysisState();
    projectManager.resetProjectSelection();
    analysis.setStatusMessage("Started a new local draft.");
    setStep(0);
  }

  function exportDraft() {
    analysis.setError("");
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
    analysis.setStatusMessage("Draft exported as JSON.");
  }

  function openImportDraft() {
    draftImportRef.current?.click();
  }

  function openImportWorkspace() {
    workspaceImportRef.current?.click();
  }

  async function importDraftFromFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    setImportingDraft(true);
    analysis.setError("");

    try {
      const imported = parseImportedDraftText(await file.text());
      setForm(imported);
      analysis.resetAnalysisState();
      projectManager.resetProjectSelection();
      analysis.setStatusMessage(`Imported draft from ${file.name}. Save it to create a new local project record.`);
      setStep(0);
    } catch (requestError) {
      analysis.setError(requestError instanceof Error ? requestError.message : "Unexpected draft import error");
    } finally {
      event.target.value = "";
      setImportingDraft(false);
    }
  }

  async function exportWorkspace() {
    setExportingWorkspace(true);
    analysis.setError("");

    try {
      const bundle = await exportWorkspaceRequest();
      const safeTimestamp = bundle.generated_at.replace(/[:]/g, "-");
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `ab-test-workspace-${safeTimestamp}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      analysis.setStatusMessage(
        `Exported workspace backup with ${String(bundle.projects.length)} project(s).`
      );
    } catch (requestError) {
      analysis.setError(requestError instanceof Error ? requestError.message : "Unexpected workspace export error");
    } finally {
      setExportingWorkspace(false);
    }
  }

  async function importWorkspaceFromFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    setImportingWorkspace(true);
    analysis.setError("");

    try {
      const parsed = JSON.parse(await file.text()) as WorkspaceBundleInput;
      const validation = await validateWorkspaceRequest(parsed);
      const result = await importWorkspaceRequest(parsed);
      await loadProjects();
      await projectManager.loadBackendDiagnostics();
      const shortChecksum = validation.checksum_sha256.slice(0, 12);
      analysis.setStatusMessage(
        `Validated workspace backup (schema v${String(validation.schema_version)}, checksum ${shortChecksum}...). ` +
        `Imported workspace backup: ${String(result.imported_projects)} project(s), ` +
        `${String(result.imported_analysis_runs)} analysis run(s), ` +
        `${String(result.imported_export_events)} export event(s), ` +
        `${String(result.imported_project_revisions ?? 0)} revision(s).`
      );
    } catch (requestError) {
      analysis.setError(requestError instanceof Error ? requestError.message : "Unexpected workspace import error");
    } finally {
      event.target.value = "";
      setImportingWorkspace(false);
    }
  }

  async function loadProjects() {
    analysis.setError("");

    try {
      await projectManager.loadProjects();
    } catch (requestError) {
      analysis.setError(requestError instanceof Error ? requestError.message : "Unexpected project list error");
    }
  }

  async function runAnalysis() {
    if (!analysis.ensureValidForm(form)) {
      return;
    }

    const snapshotEligibleProjectId =
      projectManager.activeProjectId !== null && !projectManager.hasUnsavedChanges
        ? projectManager.activeProjectId
        : null;

    projectManager.setSelectedHistoryRunId(null);
    projectManager.clearProjectComparison();
    analysis.setLoading(true);
    analysis.setError("");
    analysis.setStatusMessage("");

    try {
      const result = await requestAnalysis(form);
      analysis.setResults(result);
      analysis.setResultsProjectId(snapshotEligibleProjectId);
      analysis.setResultsAnalysisRunId(null);
      setStep(lastStepIndex);

      if (snapshotEligibleProjectId) {
        try {
          const updatedProject = await recordProjectAnalysisRequest(snapshotEligibleProjectId, result);
          projectManager.syncPersistedProject(updatedProject, JSON.stringify(buildApiPayload(form)));
          analysis.setResultsAnalysisRunId(updatedProject.last_analysis_run_id ?? null);
          await projectManager.refreshProjectHistory(snapshotEligibleProjectId, true);
          analysis.setStatusMessage("Analysis completed and the latest snapshot was recorded for this saved project.");
        } catch (metadataError) {
          analysis.setStatusMessage("Analysis completed, but project snapshot metadata could not be persisted.");
          analysis.setError(metadataError instanceof Error ? metadataError.message : "Unexpected analysis snapshot error");
        }
      } else if (projectManager.activeProjectId) {
        analysis.setStatusMessage("Analysis completed for draft changes. Save the project to persist this analysis snapshot.");
      } else {
        analysis.setStatusMessage("Analysis completed. Deterministic output and optional AI advice are shown below.");
      }
    } catch (requestError) {
      analysis.setError(requestError instanceof Error ? requestError.message : "Unexpected request error");
    } finally {
      analysis.setLoading(false);
    }
  }

  async function saveProject() {
    if (!analysis.ensureValidForm(form)) {
      return;
    }

    projectManager.setSelectedHistoryRunId(null);
    analysis.setSaving(true);
    analysis.setError("");
    analysis.setStatusMessage("");

    try {
      const normalizedPayload = buildApiPayload(form);
      const normalizedPayloadJson = JSON.stringify(normalizedPayload);
      const persistedAnalysis = analysis.getPersistableAnalysis();
      const data = await saveProjectRequest(form, projectManager.activeProjectId);
      const { savedProjectId, savedProject } = projectManager.syncPersistedProject(data, normalizedPayloadJson);
      let saveStatus = projectManager.activeProjectId
        ? `Project ${String(data.project_name)} updated locally.`
        : `Project saved locally with id ${String(data.id)}.`;

      if (savedProjectId) {
        analysis.setResultsProjectId(savedProjectId);
      }

      if (savedProjectId && persistedAnalysis && analysis.resultsAnalysisRunId === null) {
        try {
          const updatedProject = await recordProjectAnalysisRequest(savedProjectId, persistedAnalysis);
          projectManager.syncPersistedProject(updatedProject, normalizedPayloadJson);
          analysis.setResultsAnalysisRunId(updatedProject.last_analysis_run_id ?? null);
          saveStatus = `${saveStatus} Latest analysis snapshot was recorded for this saved project.`;
        } catch (metadataError) {
          analysis.setError(metadataError instanceof Error ? metadataError.message : "Unexpected analysis snapshot save error");
          saveStatus = `${saveStatus} Current analysis is still local until the snapshot is recorded.`;
        }
      }

      if (!savedProject) {
        await loadProjects();
      }
      if (savedProjectId) {
        await projectManager.refreshProjectHistory(savedProjectId, true);
        await projectManager.refreshProjectRevisions(savedProjectId, true);
      }
      projectManager.clearProjectComparison();
      analysis.setStatusMessage(saveStatus);
    } catch (requestError) {
      analysis.setError(requestError instanceof Error ? requestError.message : "Unexpected save error");
    } finally {
      analysis.setSaving(false);
    }
  }

  async function loadProject(projectId: string) {
    analysis.setError("");
    analysis.setStatusMessage("");

    try {
      const data = await projectManager.loadProject(projectId);
      setForm(hydrateLoadedPayload(data.payload));
      analysis.resetAnalysisState();
      analysis.setStatusMessage(`Loaded project ${String(data.project_name)} into the wizard.`);
      setStep(0);
    } catch (requestError) {
      analysis.setError(requestError instanceof Error ? requestError.message : "Unexpected project load error");
    }
  }

  async function deleteProject(projectId: string, projectName: string) {
    analysis.setError("");
    analysis.setStatusMessage("");

    try {
      const result = await projectManager.deleteProject(projectId, projectName);
      if (!result.deleted) {
        return;
      }

      if (result.deletedActive) {
        analysis.resetAnalysisState();
        analysis.setStatusMessage(`Project ${projectName} deleted. Current form remains as a new local draft.`);
      } else {
        analysis.setStatusMessage(`Project ${projectName} deleted locally.`);
      }
    } catch (requestError) {
      analysis.setError(requestError instanceof Error ? requestError.message : "Unexpected project delete error");
    }
  }

  async function exportReport(format: ExportFormat) {
    if (!displayedAnalysis?.report) {
      analysis.setError("Run analysis before exporting a report.");
      return;
    }

    analysis.setError("");
    analysis.setStatusMessage("");

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

      const exportProjectId = projectManager.selectedHistoryRun?.project_id ?? analysis.resultsProjectId;

      if (exportProjectId) {
        try {
          const linkedAnalysisRunId =
            projectManager.selectedHistoryRun?.id ??
            analysis.resultsAnalysisRunId ??
            (projectManager.activeProjectId === exportProjectId
              ? projectManager.activeProject?.last_analysis_run_id ?? null
              : null);
          const updatedProject = await recordProjectExportRequest(exportProjectId, format, linkedAnalysisRunId);
          projectManager.syncPersistedProject(
            updatedProject,
            projectManager.savedProjectSnapshot ?? JSON.stringify(buildApiPayload(form))
          );
          await projectManager.refreshProjectHistory(exportProjectId, true);
          analysis.setStatusMessage(`Exported report as ${extension.toUpperCase()} and updated project export metadata.`);
        } catch (metadataError) {
          analysis.setStatusMessage(`Exported report as ${extension.toUpperCase()}, but project export metadata was not updated.`);
          analysis.setError(metadataError instanceof Error ? metadataError.message : "Unexpected export metadata error");
        }
      } else {
        analysis.setStatusMessage(`Exported report as ${extension.toUpperCase()}.`);
      }
    } catch (requestError) {
      analysis.setError(requestError instanceof Error ? requestError.message : "Unexpected export error");
    }
  }

  function openHistoryRun(runId: string) {
    if (!projectManager.openHistoryRun(runId)) {
      return;
    }

    analysis.setStatusMessage("Opened a saved analysis snapshot from project history.");
    analysis.setError("");
    setStep(lastStepIndex);
  }

  function clearHistoryRunSelection() {
    if (!projectManager.clearHistoryRunSelection()) {
      return;
    }

    analysis.setStatusMessage(
      analysis.results.report
        ? "Returned to the current in-memory analysis results."
        : "Closed the saved snapshot preview."
    );
    analysis.setError("");
  }

  function loadProjectRevision(revisionId: string) {
    const revision = projectManager.projectRevisions?.revisions.find((item) => item.id === revisionId);
    if (!revision) {
      analysis.setError("Saved revision not found.");
      return;
    }

    setForm(hydrateLoadedPayload(revision.payload));
    projectManager.setSelectedHistoryRunId(null);
    projectManager.clearProjectComparison();
    analysis.resetAnalysisState();
    analysis.setStatusMessage(
      `Loaded ${revision.source.replace("_", " ")} revision from ${revision.created_at}. Save the project to persist it as the latest local version.`
    );
    analysis.setError("");
    setStep(0);
  }

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
      <input
        ref={workspaceImportRef}
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        aria-label="Import workspace file"
        onChange={importWorkspaceFromFile}
      />
      <div className="page">
        <div className="shell">
          {draftStorageWarning ? (
            <div className="toast-banner" role="status">
              <div className="toast-copy">
                <Icon name="warning" className="icon icon-inline" />
                <span>{draftStorageWarning}</span>
              </div>
              <button className="btn secondary" onClick={clearDraftStorageWarning}>
                Dismiss
              </button>
            </div>
          ) : null}
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
              activeProjectId={projectManager.activeProjectId}
              hasUnsavedChanges={projectManager.hasUnsavedChanges}
              validationErrors={analysis.validationErrors}
              importingDraft={importingDraft}
              loading={analysis.loading}
              saving={analysis.saving}
              results={analysis.results}
              displayedAnalysis={displayedAnalysis}
              activeProject={projectManager.activeProject}
              projectHistory={projectManager.projectHistory}
              selectedHistoryRun={projectManager.selectedHistoryRun}
              projectComparison={projectManager.projectComparison}
              loadingProjectHistory={projectManager.loadingProjectHistory}
              statusMessage={analysis.statusMessage}
              error={uiError}
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
              loadingHealth={projectManager.loadingHealth}
              loadingDiagnostics={projectManager.loadingDiagnostics}
              loadingProjects={projectManager.loadingProjects}
              importingWorkspace={importingWorkspace}
              exportingWorkspace={exportingWorkspace}
              deletingProjectId={projectManager.deletingProjectId}
              backendHealth={projectManager.backendHealth}
              backendDiagnostics={projectManager.backendDiagnostics}
              healthError={projectManager.healthError}
              diagnosticsError={projectManager.diagnosticsError}
              savedProjects={projectManager.savedProjects}
              activeProjectId={projectManager.activeProjectId}
              activeProject={projectManager.activeProject}
              projectHistory={projectManager.projectHistory}
              projectRevisions={projectManager.projectRevisions}
              projectHistoryError={projectManager.projectHistoryError}
              projectRevisionsError={projectManager.projectRevisionsError}
              loadingProjectHistory={projectManager.loadingProjectHistory}
              loadingProjectRevisions={projectManager.loadingProjectRevisions}
              selectedHistoryRunId={projectManager.selectedHistoryRunId}
              projectComparison={projectManager.projectComparison}
              projectComparisonError={projectManager.projectComparisonError}
              loadingProjectComparison={projectManager.loadingProjectComparison}
              comparingProjectId={projectManager.comparingProjectId}
              hasUnsavedChanges={projectManager.hasUnsavedChanges}
              onRefreshHealth={projectManager.loadBackendHealth}
              onRefreshDiagnostics={projectManager.loadBackendDiagnostics}
              onRefreshProjectHistory={(projectId) => {
                void projectManager.refreshProjectHistory(projectId);
              }}
              onRefreshProjectRevisions={(projectId) => {
                void projectManager.refreshProjectRevisions(projectId);
              }}
              onLoadMoreAnalysisHistory={(projectId) => {
                void projectManager.refreshProjectHistory(projectId, false, {
                  analysisLimit: projectManager.projectHistoryWindow.analysisLimit + 5
                });
              }}
              onLoadMoreExportHistory={(projectId) => {
                void projectManager.refreshProjectHistory(projectId, false, {
                  exportLimit: projectManager.projectHistoryWindow.exportLimit + 5
                });
              }}
              onLoadMoreProjectRevisions={(projectId) => {
                void projectManager.refreshProjectRevisions(projectId, false, {
                  limit: projectManager.projectRevisionWindow.limit + 5
                });
              }}
              onOpenHistoryRun={openHistoryRun}
              onLoadProjectRevision={loadProjectRevision}
              onClearHistoryRunSelection={clearHistoryRunSelection}
              onCompareProject={(projectId) => {
                void projectManager.compareProject(projectId).then((message) => {
                  if (message) {
                    analysis.setStatusMessage(message);
                  }
                });
              }}
              onLoadProjects={() => {
                void loadProjects();
              }}
              onExportWorkspace={() => {
                void exportWorkspace();
              }}
              onImportWorkspace={openImportWorkspace}
              onLoadProject={(projectId) => {
                void loadProject(projectId);
              }}
              onDeleteProject={(projectId, projectName) => {
                void deleteProject(projectId, projectName);
              }}
            />
          </div>
        </div>
      </div>
    </>
  );
}
