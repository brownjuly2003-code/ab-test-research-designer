import { useEffect, useRef, useState, type ChangeEvent } from "react";

import "./App.css";
import SidebarPanel from "./components/SidebarPanel";
import WizardPanel from "./components/WizardPanel";
import {
  exportReportRequest,
  recordProjectAnalysisRequest,
  recordProjectExportRequest,
  requestAnalysis,
  saveProjectRequest
} from "./lib/api";
import {
  buildApiPayload,
  buildDraftTransferFile,
  cloneInitialState,
  type ExportFormat,
  type FullPayload,
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
  const draftImportRef = useRef<HTMLInputElement | null>(null);
  const serializedForm = JSON.stringify(buildApiPayload(form));
  const analysis = useAnalysis();
  const projectManager = useProjectManager(serializedForm);
  const { draftStorageWarning, parseImportedDraftText } = useDraftPersistence(form, draftBootstrap.warning);
  const lastStepIndex = stepLabels.length - 1;
  const displayedAnalysis =
    projectManager.selectedHistoryRun?.analysis ?? analysis.getPersistableAnalysis();
  const uiError = [analysis.error, draftStorageWarning].filter(Boolean).join(" | ");

  useEffect(() => {
    if (draftBootstrap.restored) {
      analysis.setStatusMessage("Restored unsaved browser draft.");
    }
  }, [draftBootstrap.restored]);

  useEffect(() => {
    void projectManager.loadBackendHealth();
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
              loadingProjects={projectManager.loadingProjects}
              deletingProjectId={projectManager.deletingProjectId}
              backendHealth={projectManager.backendHealth}
              healthError={projectManager.healthError}
              savedProjects={projectManager.savedProjects}
              activeProjectId={projectManager.activeProjectId}
              activeProject={projectManager.activeProject}
              projectHistory={projectManager.projectHistory}
              projectHistoryError={projectManager.projectHistoryError}
              loadingProjectHistory={projectManager.loadingProjectHistory}
              selectedHistoryRunId={projectManager.selectedHistoryRunId}
              projectComparison={projectManager.projectComparison}
              projectComparisonError={projectManager.projectComparisonError}
              loadingProjectComparison={projectManager.loadingProjectComparison}
              comparingProjectId={projectManager.comparingProjectId}
              hasUnsavedChanges={projectManager.hasUnsavedChanges}
              onRefreshHealth={projectManager.loadBackendHealth}
              onRefreshProjectHistory={(projectId) => {
                void projectManager.refreshProjectHistory(projectId);
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
              onOpenHistoryRun={openHistoryRun}
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
