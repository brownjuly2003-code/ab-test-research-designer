import { sections, stepLabels, type AnalysisResponsePayload, type DraftFieldValue, type ExportFormat, type FullPayload, type FullPayloadSectionKey, type ProjectAnalysisRun, type ProjectComparison, type ProjectHistory, type ResultsState, type SavedProject } from "../lib/experiment";
import ProgressBar from "./ProgressBar";
import ResultsPanel from "./ResultsPanel";
import WizardDraftStep from "./WizardDraftStep";
import WizardReviewStep from "./WizardReviewStep";

type WizardPanelProps = {
  step: number;
  form: FullPayload;
  activeProjectId: string | null;
  hasUnsavedChanges: boolean;
  canMutateBackend: boolean;
  backendMutationMessage: string;
  validationErrors: string[];
  importingDraft: boolean;
  loading: boolean;
  saving: boolean;
  results: ResultsState;
  displayedAnalysis: AnalysisResponsePayload | null;
  activeProject: SavedProject | null;
  projectHistory: ProjectHistory | null;
  selectedHistoryRun: ProjectAnalysisRun | null;
  projectComparison: ProjectComparison | null;
  loadingProjectHistory: boolean;
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
  onClearHistorySelection: () => void;
  onExportReport: (format: ExportFormat) => void;
};

export default function WizardPanel({
  step,
  form,
  activeProjectId,
  hasUnsavedChanges,
  canMutateBackend,
  backendMutationMessage,
  validationErrors,
  importingDraft,
  loading,
  saving,
  results,
  displayedAnalysis,
  activeProject,
  projectHistory,
  selectedHistoryRun,
  projectComparison,
  loadingProjectHistory,
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
  onClearHistorySelection,
  onExportReport
}: WizardPanelProps) {
  const isReviewStep = step >= sections.length;
  const current = sections[Math.min(step, sections.length - 1)];

  return (
    <section className="panel">
      <ProgressBar currentStep={step} totalSteps={stepLabels.length - 1} />
      <div className="steps">
        {stepLabels.map((label, index) => (
          <div key={label} className={`step ${index === step ? "active" : index < step ? "done" : ""}`}>
            {index + 1}. {label}
          </div>
        ))}
      </div>

      {!isReviewStep ? (
        <WizardDraftStep
          current={current}
          form={form}
          canGoBack={step > 0}
          activeProjectId={activeProjectId}
          hasUnsavedChanges={hasUnsavedChanges}
          canMutateBackend={canMutateBackend}
          backendMutationMessage={backendMutationMessage}
          validationErrors={validationErrors}
          importingDraft={importingDraft}
          loading={loading}
          saving={saving}
          onUpdateSection={onUpdateSection}
          onBack={onBack}
          onNext={onNext}
          onSave={onSave}
          onStartNew={onStartNew}
          onImportDraft={onImportDraft}
          onExportDraft={onExportDraft}
        />
      ) : (
        <WizardReviewStep
          form={form}
          activeProjectId={activeProjectId}
          hasUnsavedChanges={hasUnsavedChanges}
          canMutateBackend={canMutateBackend}
          backendMutationMessage={backendMutationMessage}
          validationErrors={validationErrors}
          importingDraft={importingDraft}
          loading={loading}
          saving={saving}
          onBack={onBack}
          onSave={onSave}
          onStartNew={onStartNew}
          onImportDraft={onImportDraft}
          onExportDraft={onExportDraft}
          onRunAnalysis={onRunAnalysis}
        />
      )}
      <ResultsPanel
        results={results}
        displayedAnalysis={displayedAnalysis}
        loading={loading}
        canMutateBackend={canMutateBackend}
        backendMutationMessage={backendMutationMessage}
        activeProject={activeProject}
        projectHistory={projectHistory}
        selectedHistoryRun={selectedHistoryRun}
        projectComparison={projectComparison}
        loadingProjectHistory={loadingProjectHistory}
        statusMessage={statusMessage}
        error={error}
        onClearHistorySelection={onClearHistorySelection}
        onExportReport={onExportReport}
      />
    </section>
  );
}
