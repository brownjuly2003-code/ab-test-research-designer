import { sections, stepLabels, type DraftFieldValue, type ExportFormat, type FullPayload, type FullPayloadSectionKey, type ResultsState } from "../lib/experiment";
import ResultsPanel from "./ResultsPanel";
import WizardDraftStep from "./WizardDraftStep";
import WizardReviewStep from "./WizardReviewStep";

type WizardPanelProps = {
  step: number;
  form: FullPayload;
  activeProjectId: string | null;
  hasUnsavedChanges: boolean;
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
  hasUnsavedChanges,
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
        <WizardDraftStep
          current={current}
          form={form}
          canGoBack={step > 0}
          activeProjectId={activeProjectId}
          hasUnsavedChanges={hasUnsavedChanges}
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
        loading={loading}
        statusMessage={statusMessage}
        error={error}
        onExportReport={onExportReport}
      />
    </section>
  );
}
