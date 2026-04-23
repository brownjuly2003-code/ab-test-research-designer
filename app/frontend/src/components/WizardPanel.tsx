import { useEffect, useRef, useState, type ChangeEvent } from "react";

import sampleProject from "../fixtures/sample-project.json";
import { useToast, type ToastType } from "../hooks/useToast";
import { t } from "../i18n";
import {
  buildApiPayload,
  buildDraftTransferFile,
  parseImportedDraft,
  sections,
  setSectionFieldValue,
  stepLabels,
  validateStep,
  type DraftFieldValue,
  type ExportFormat,
  type FullPayloadSectionKey
} from "../lib/experiment";
import { useAnalysisStore } from "../stores/analysisStore";
import { useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import { useThemeStore } from "../stores/themeStore";
import { useWizardStore } from "../stores/wizardStore";
import EmptyState from "./EmptyState";
import ErrorBoundary from "./ErrorBoundary";
import ProgressBar from "./ProgressBar";
import ResultsPanel from "./ResultsPanel";
import ShortcutHelp from "./ShortcutHelp";
import TemplateGallery from "./TemplateGallery";
import ToastSystem from "./ToastSystem";
import WizardDraftStep from "./WizardDraftStep";
import WizardReviewStep from "./WizardReviewStep";
import styles from "./WizardDraftStep.module.css";

const sampleProjectDraft = parseImportedDraft(JSON.stringify(sampleProject));

function downloadJson(content: string, filename: string) {
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function currentDisplayedAnalysis() {
  const analysis = useAnalysisStore.getState();
  const project = useProjectStore.getState();
  return project.selectedHistoryRun?.analysis ?? analysis.getPersistableAnalysis();
}

function blockMutations(): boolean {
  const analysis = useAnalysisStore.getState();
  const project = useProjectStore.getState();
  if (project.canMutateBackend) {
    return false;
  }
  analysis.clearFeedback();
  analysis.showError(project.backendMutationMessage || t("results.panel.backendReadOnly"), "warning");
  return true;
}

async function showAsyncStatus(action: Promise<string | null>, type: ToastType) {
  const message = await action;
  if (message) {
    useAnalysisStore.getState().showStatus(message, type);
  }
}

function updateDraftSection(section: FullPayloadSectionKey, key: string, value: DraftFieldValue) {
  const analysis = useAnalysisStore.getState();
  const draftStore = useDraftStore.getState();
  const project = useProjectStore.getState();
  const nextDraft = setSectionFieldValue(draftStore.draft, section, key, value);
  project.clearProjectError();
  draftStore.replaceDraft(nextDraft, { markDirty: true });
  project.markDraftChanged(JSON.stringify(buildApiPayload(nextDraft)));
  analysis.invalidateResults();
  analysis.validateDraft(nextDraft);
}

function startNewDraft() {
  const analysis = useAnalysisStore.getState();
  const draftStore = useDraftStore.getState();
  const project = useProjectStore.getState();
  project.clearProjectError();
  draftStore.resetDraft();
  analysis.clearAnalysis();
  project.resetProjectSelection();
  analysis.showStatus(t("wizardPanel.status.startedNewDraft"), "info");
  useWizardStore.getState().openWizard();
}

function loadExampleDraft() {
  const analysis = useAnalysisStore.getState();
  const draftStore = useDraftStore.getState();
  const project = useProjectStore.getState();
  project.clearProjectError();
  draftStore.replaceDraft(sampleProjectDraft, { markDirty: true });
  analysis.clearAnalysis();
  project.resetProjectSelection();
  analysis.showStatus(t("toasts.example_loaded"), "info");
  useWizardStore.getState().openWizard();
}

function exportDraftFile() {
  const analysis = useAnalysisStore.getState();
  const draftStore = useDraftStore.getState();
  useProjectStore.getState().clearProjectError();
  analysis.clearFeedback();
  const safeName = String(draftStore.draft.project.project_name ?? "experiment-draft")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "experiment-draft";
  downloadJson(
    JSON.stringify(buildDraftTransferFile(draftStore.draft), null, 2),
    `${safeName}.json`
  );
  analysis.showStatus(t("wizardPanel.status.draftExported"), "success");
}

async function importDraftFromFile(event: ChangeEvent<HTMLInputElement>) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  const analysis = useAnalysisStore.getState();
  const draftStore = useDraftStore.getState();
  const project = useProjectStore.getState();
  const wizard = useWizardStore.getState();
  wizard.setImportingDraft(true);
  project.clearProjectError();
  analysis.clearFeedback();
  try {
    draftStore.replaceDraft(draftStore.parseImportedDraftText(await file.text()), { markDirty: true });
    analysis.clearAnalysis();
    project.resetProjectSelection();
    analysis.showStatus(t("wizardPanel.status.importedDraftFrom", { fileName: file.name }), "success");
    wizard.openWizard();
  } catch (error) {
    analysis.showError(error instanceof Error ? error.message : t("wizardPanel.errors.unexpectedDraftImport"), "error");
  } finally {
    event.target.value = "";
    wizard.setImportingDraft(false);
  }
}

async function runAnalysisFlow() {
  if (blockMutations()) {
    return;
  }
  const analysis = useAnalysisStore.getState();
  const draftStore = useDraftStore.getState();
  const project = useProjectStore.getState();
  const llmProvider = typeof window === "undefined"
    ? "local"
    : String(window.sessionStorage.getItem("ab_llm_provider") ?? "").trim().toLowerCase();
  const llmToken = typeof window === "undefined"
    ? ""
    : String(window.sessionStorage.getItem("ab_llm_token") ?? "").trim();
  project.clearProjectError();
  const result = await analysis.runAnalysis(draftStore.draft);
  if (!result) {
    return;
  }
  if ((llmProvider === "openai" || llmProvider === "anthropic") && llmToken.length === 0) {
    analysis.showStatus(t("app.preferences.llm.tokenRequiredFallback"), "warning");
  }
  const outcome = await project.persistAnalysisSnapshot(draftStore.draft, result);
  analysis.linkResultToProject(outcome.projectId, outcome.analysisRunId);
  analysis.showStatus(
    outcome.message,
    outcome.projectId !== null && outcome.analysisRunId === null ? "warning" : "success"
  );
  useWizardStore.getState().openWizard(stepLabels.length - 1);
}

async function saveProjectFlow() {
  const analysis = useAnalysisStore.getState();
  const draftStore = useDraftStore.getState();
  if (blockMutations() || !analysis.ensureValidForm(draftStore.draft)) {
    return;
  }
  analysis.clearFeedback();
  const persistedAnalysis = analysis.getPersistableAnalysis();
  const currentAnalysisRunId = analysis.resultsAnalysisRunId;
  const outcome = await useProjectStore.getState().saveProject(
    draftStore.draft,
    persistedAnalysis,
    currentAnalysisRunId
  );
  if (!outcome) {
    return;
  }
  if (outcome.savedProjectId) {
    analysis.linkResultToProject(outcome.savedProjectId, outcome.analysisRunId);
  }
  analysis.showStatus(
    outcome.message,
    persistedAnalysis && currentAnalysisRunId === null && outcome.analysisRunId === null
      ? "warning"
      : "success"
  );
}

function clearHistoryRunSelection() {
  const analysis = useAnalysisStore.getState();
  const project = useProjectStore.getState();
  if (!project.clearHistoryRunSelection()) {
    return;
  }
  analysis.clearFeedback();
  analysis.showStatus(
    analysis.results.report
      ? t("results.panel.returnedToCurrentAnalysis")
      : t("results.panel.closedSnapshotPreview"),
    "info"
  );
}

async function exportReportFlow(format: ExportFormat) {
  if (blockMutations()) {
    return;
  }
  const analysis = useAnalysisStore.getState();
  const project = useProjectStore.getState();
  const displayedAnalysis = currentDisplayedAnalysis();
  if (!displayedAnalysis?.report) {
    analysis.clearFeedback();
    analysis.showError(t("results.panel.runAnalysisBeforeExportingReport"), "info");
    return;
  }
  analysis.clearFeedback();
  const exportProjectId = project.selectedHistoryRun?.project_id ?? analysis.resultsProjectId;
  const linkedRunId =
    project.selectedHistoryRun?.id ??
    analysis.resultsAnalysisRunId ??
    (project.activeProjectId === exportProjectId ? project.activeProject?.last_analysis_run_id ?? null : null);
  await showAsyncStatus(project.exportReport(displayedAnalysis.report, format, exportProjectId, linkedRunId), "success");
}

export function GlobalSideEffects() {
  const hydrateTheme = useThemeStore((state) => state.hydrateTheme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const draftStorageWarning = useDraftStore((state) => state.draftStorageWarning);
  const draftStorageMessage = useDraftStore((state) => state.draftStorageMessage);
  const clearDraftStorageWarning = useDraftStore((state) => state.clearDraftStorageWarning);
  const { toasts, addToast, removeToast } = useToast();
  const [shortcutHelpOpen, setShortcutHelpOpen] = useState(false);
  const lastStatusToastRef = useRef("");
  const lastAnalysisErrorToastRef = useRef("");
  const lastProjectErrorToastRef = useRef("");
  const lastStorageWarningToastRef = useRef("");
  const storageWarningToastIdRef = useRef<string | null>(null);
  const statusMessage = useAnalysisStore((state) => state.statusMessage);
  const statusToastType = useAnalysisStore((state) => state.statusToastType);
  const analysisError = useAnalysisStore((state) => state.analysisError);
  const errorToastType = useAnalysisStore((state) => state.errorToastType);
  const projectError = useProjectStore((state) => state.projectError);

  useEffect(() => {
    hydrateTheme();
    useWizardStore.getState().hydrateWizard();
    useProjectStore.getState().resetProjectSelection();
    const bootstrap = useDraftStore.getState().readDraftBootstrap();
    useAnalysisStore.getState().clearAnalysis();
    if (bootstrap.restored) {
      useWizardStore.getState().setShowOnboarding(false);
      useAnalysisStore.getState().showStatus(t("wizardPanel.status.restoredBrowserDraft"), "info");
    }
    void useProjectStore.getState().refreshBackendState();
  }, [hydrateTheme]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target;
      const isFormField =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement;
      const ctrl = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      if (event.key === "Escape" && shortcutHelpOpen) {
        event.preventDefault();
        setShortcutHelpOpen(false);
        return;
      }
      if (!ctrl && isFormField) {
        return;
      }
      if (!ctrl && event.key === "?") {
        event.preventDefault();
        setShortcutHelpOpen(true);
        return;
      }
      if (!ctrl && event.key === "/") {
        event.preventDefault();
        document.getElementById("saved-projects-search")?.focus();
        return;
      }
      if (event.key === "ArrowRight") {
        useWizardStore.getState().setStep((current) => Math.min(stepLabels.length - 1, current + 1));
        return;
      }
      if (event.key === "ArrowLeft") {
        useWizardStore.getState().setStep((current) => Math.max(0, current - 1));
        return;
      }
      if (!ctrl) {
        return;
      }
      if (event.shiftKey && key === "d") {
        event.preventDefault();
        toggleTheme();
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        void runAnalysisFlow();
        return;
      }
      if (key === "e") {
        event.preventDefault();
        void exportReportFlow("markdown");
        return;
      }
      if (key === "s") {
        event.preventDefault();
        void saveProjectFlow();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [shortcutHelpOpen, toggleTheme]);

  useEffect(() => {
    if (!statusMessage || !statusToastType) {
      lastStatusToastRef.current = "";
      return;
    }
    const toastKey = `${statusToastType}:${statusMessage}`;
    if (lastStatusToastRef.current === toastKey) {
      return;
    }
    lastStatusToastRef.current = toastKey;
    addToast(statusToastType, statusMessage);
  }, [statusMessage, statusToastType, addToast]);

  useEffect(() => {
    if (!analysisError) {
      lastAnalysisErrorToastRef.current = "";
      return;
    }
    if (lastAnalysisErrorToastRef.current === analysisError) {
      return;
    }
    lastAnalysisErrorToastRef.current = analysisError;
    addToast(errorToastType ?? "error", analysisError, 0);
  }, [analysisError, errorToastType, addToast]);

  useEffect(() => {
    if (!projectError) {
      lastProjectErrorToastRef.current = "";
      return;
    }
    if (lastProjectErrorToastRef.current === projectError) {
      return;
    }
    lastProjectErrorToastRef.current = projectError;
    addToast("error", projectError, 0);
  }, [projectError, addToast]);

  useEffect(() => {
    if (!draftStorageWarning || !draftStorageMessage) {
      lastStorageWarningToastRef.current = "";
      if (storageWarningToastIdRef.current) {
        removeToast(storageWarningToastIdRef.current);
        storageWarningToastIdRef.current = null;
      }
      return;
    }
    const toastKey = `${draftStorageWarning}:${draftStorageMessage}`;
    if (lastStorageWarningToastRef.current === toastKey) {
      return;
    }
    lastStorageWarningToastRef.current = toastKey;
    if (storageWarningToastIdRef.current) {
      removeToast(storageWarningToastIdRef.current);
    }
    storageWarningToastIdRef.current = addToast(
      draftStorageWarning === "full" ? "warning" : "info",
      draftStorageMessage
    );
  }, [draftStorageWarning, draftStorageMessage, addToast, removeToast]);

  return (
    <>
      <input
        id="global-draft-import-input"
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        aria-label={t("wizardPanel.aria.importDraftFile")}
        onChange={importDraftFromFile}
      />
      {draftStorageWarning === "full" && draftStorageMessage ? (
        <div className="error" role="alert">
          {t("wizardPanel.status.draftNotSavedStorageFull")} {draftStorageMessage}
          <button className="btn secondary" onClick={clearDraftStorageWarning}>{t("wizardPanel.dismiss")}</button>
        </div>
      ) : null}
      {shortcutHelpOpen ? <ShortcutHelp onClose={() => setShortcutHelpOpen(false)} /> : null}
      <ToastSystem toasts={toasts} onDismiss={removeToast} />
    </>
  );
}

export function OnboardingPanel() {
  const inputRef = useRef<HTMLInputElement | null>(null);

  async function importWorkspaceFromFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    event.target.value = "";
    if (blockMutations()) {
      return;
    }
    useAnalysisStore.getState().clearFeedback();
    await showAsyncStatus(useProjectStore.getState().importWorkspace(await file.text()), "success");
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        aria-label={t("wizardPanel.aria.importWorkspaceFile")}
        onChange={importWorkspaceFromFile}
      />
      <EmptyState
        onNewExperiment={startNewDraft}
        onLoadExample={loadExampleDraft}
        onImportProject={() => inputRef.current?.click()}
      />
    </>
  );
}

export default function WizardPanel() {
  const openWizard = useWizardStore((state) => state.openWizard);
  const step = useWizardStore((state) => state.step);
  const importingDraft = useWizardStore((state) => state.importingDraft);
  const setStep = useWizardStore((state) => state.setStep);
  const draftStore = useDraftStore();
  const analysis = useAnalysisStore();
  const project = useProjectStore();
  const stepHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const [templateGalleryOpen, setTemplateGalleryOpen] = useState(false);
  const form = draftStore.draft;
  const displayedAnalysis = currentDisplayedAnalysis();
  const stepErrors = stepLabels.reduce<Record<number, boolean>>((current, _label, index) => {
    current[index] = validateStep(index, form).length > 0;
    return current;
  }, {});
  const isReviewStep = step >= sections.length;
  const current = sections[Math.min(step, sections.length - 1)];
  const uiError = analysis.analysisError || project.projectError;
  const translatedStepLabels = [
    t("wizard.steps.1"),
    t("wizard.steps.2"),
    t("wizard.steps.3"),
    t("wizard.steps.4"),
    t("wizard.steps.5"),
    t("wizard.steps.6")
  ];

  useEffect(() => {
    stepHeadingRef.current?.focus();
  }, [step]);

  function handleApplyTemplate(nextDraft: typeof form, templateName: string) {
    project.clearProjectError();
    draftStore.replaceDraft(nextDraft, { markDirty: true });
    analysis.clearAnalysis();
    project.resetProjectSelection();
    analysis.showStatus(t("wizardPanel.status.templateLoaded", { templateName }), "success");
    setTemplateGalleryOpen(false);
    openWizard();
  }

  return (
    <section className="panel">
      <ProgressBar currentStep={step} totalSteps={stepLabels.length - 1} />
      <div className={styles.steps}>
        {translatedStepLabels.map((label, index) => (
          <div
            key={label}
            className={[
              styles.step,
              "step",
              index === step ? `${styles.active} active` : index < step ? styles.done : ""
            ].filter(Boolean).join(" ")}
            data-step-index={index}
          >
            {index + 1}. {label}
            {stepErrors[index] ? <span className={styles["error-dot"]} aria-label={t("wizardPanel.aria.stepHasErrors")} /> : null}
          </div>
        ))}
      </div>
      {!isReviewStep ? (
        <WizardDraftStep
          headingRef={stepHeadingRef}
          current={current}
          form={form}
          canGoBack={step > 0}
          activeProjectId={project.activeProjectId}
          hasUnsavedChanges={project.hasUnsavedChanges}
          canMutateBackend={project.canMutateBackend}
          backendMutationMessage={project.backendMutationMessage}
          validationErrors={analysis.validationErrors}
          importingDraft={importingDraft}
          loading={analysis.isAnalyzing}
          saving={project.isSavingProject}
          onUpdateSection={updateDraftSection}
          onBack={() => setStep((value) => Math.max(0, value - 1))}
          onNext={() => setStep((value) => Math.min(stepLabels.length - 1, value + 1))}
          onSave={() => void saveProjectFlow()}
          onStartNew={startNewDraft}
          onOpenTemplateGallery={() => setTemplateGalleryOpen(true)}
          onImportDraft={() => document.getElementById("global-draft-import-input")?.click()}
          onExportDraft={exportDraftFile}
        />
      ) : (
        <WizardReviewStep
          headingRef={stepHeadingRef}
          form={form}
          activeProjectId={project.activeProjectId}
          hasUnsavedChanges={project.hasUnsavedChanges}
          canMutateBackend={project.canMutateBackend}
          backendMutationMessage={project.backendMutationMessage}
          validationErrors={analysis.validationErrors}
          importingDraft={importingDraft}
          loading={analysis.isAnalyzing}
          saving={project.isSavingProject}
          onBack={() => setStep((value) => Math.max(0, value - 1))}
          onSave={() => void saveProjectFlow()}
          onStartNew={startNewDraft}
          onImportDraft={() => document.getElementById("global-draft-import-input")?.click()}
          onExportDraft={exportDraftFile}
          onRunAnalysis={() => void runAnalysisFlow()}
        />
      )}
      <ErrorBoundary>
        <ResultsPanel
          results={analysis.results}
          displayedAnalysis={displayedAnalysis}
          loading={analysis.isAnalyzing}
          canMutateBackend={project.canMutateBackend}
          backendMutationMessage={project.backendMutationMessage}
          activeProject={project.activeProject}
          projectHistory={project.projectHistory}
          selectedHistoryRun={project.selectedHistoryRun}
          projectComparison={project.projectComparison}
          loadingProjectHistory={project.loadingProjectHistory}
          statusMessage={analysis.statusMessage}
          error={uiError}
          onClearHistorySelection={clearHistoryRunSelection}
          onExportReport={(format) => void exportReportFlow(format)}
        />
      </ErrorBoundary>
      {templateGalleryOpen ? (
        <TemplateGallery
          onClose={() => setTemplateGalleryOpen(false)}
          onApplyTemplate={handleApplyTemplate}
        />
      ) : null}
    </section>
  );
}
