import type { RefObject } from "react";

import { getReviewSections, type FullPayload } from "../lib/experiment";
import Spinner from "./Spinner";
import styles from "./WizardDraftStep.module.css";

type WizardReviewStepProps = {
  headingRef?: RefObject<HTMLHeadingElement | null>;
  form: FullPayload;
  activeProjectId: string | null;
  hasUnsavedChanges: boolean;
  canMutateBackend: boolean;
  backendMutationMessage: string;
  validationErrors: string[];
  importingDraft: boolean;
  loading: boolean;
  saving: boolean;
  onBack: () => void;
  onSave: () => void;
  onStartNew: () => void;
  onImportDraft: () => void;
  onExportDraft: () => void;
  onRunAnalysis: () => void;
};

export default function WizardReviewStep({
  headingRef,
  form,
  activeProjectId,
  hasUnsavedChanges,
  canMutateBackend,
  backendMutationMessage,
  validationErrors,
  importingDraft,
  loading,
  saving,
  onBack,
  onSave,
  onStartNew,
  onImportDraft,
  onExportDraft,
  onRunAnalysis
}: WizardReviewStepProps) {
  const reviewSections = getReviewSections(form);

  return (
    <div className={`${styles.section} ${styles["step-content"]}`}>
      <h2 ref={headingRef} tabIndex={-1}>Review inputs</h2>
      <div className="note">
        <strong>{activeProjectId ? "Reviewing a saved project" : "Reviewing a new draft"}</strong>
        <div className="muted">
          {activeProjectId
            ? `${hasUnsavedChanges ? "Unsaved changes are present." : "This loaded project is in sync with local storage."} Check the values below before saving or running the deterministic backend flow.`
            : "Check the values below before saving or running the deterministic backend flow."}
        </div>
      </div>
      {validationErrors.length > 0 ? (
        <div className="status" role="alert" aria-live="polite">
          <strong>Fix these fields before saving or running analysis:</strong>
          <ul className="list">
            {validationErrors.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {!canMutateBackend ? (
        <div className="callout">
          <span>{backendMutationMessage}</span>
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
        <button
          className="btn ghost"
          disabled={!canMutateBackend || loading || saving}
          title={activeProjectId ? "Update project (Ctrl+S)" : "Save project (Ctrl+S)"}
          onClick={onSave}
        >
          {saving ? <><Spinner /> Saving...</> : activeProjectId ? "Update project" : "Save project"}
        </button>
        <button
          className="btn primary"
          disabled={!canMutateBackend || loading}
          title="Run analysis (Ctrl+Enter)"
          onClick={onRunAnalysis}
        >
          {loading ? <><Spinner /> Analyzing...</> : "Run analysis"}
        </button>
      </div>
    </div>
  );
}
