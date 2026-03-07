import {
  getSectionFieldValue,
  type DraftFieldValue,
  type FullPayload,
  type FullPayloadSectionKey,
  type SectionConfig
} from "../lib/experiment";

type WizardDraftStepProps = {
  current: SectionConfig;
  form: FullPayload;
  canGoBack: boolean;
  activeProjectId: string | null;
  hasUnsavedChanges: boolean;
  validationErrors: string[];
  importingDraft: boolean;
  loading: boolean;
  saving: boolean;
  onUpdateSection: (section: FullPayloadSectionKey, key: string, value: DraftFieldValue) => void;
  onBack: () => void;
  onNext: () => void;
  onSave: () => void;
  onStartNew: () => void;
  onImportDraft: () => void;
  onExportDraft: () => void;
};

export default function WizardDraftStep({
  current,
  form,
  canGoBack,
  activeProjectId,
  hasUnsavedChanges,
  validationErrors,
  importingDraft,
  loading,
  saving,
  onUpdateSection,
  onBack,
  onNext,
  onSave,
  onStartNew,
  onImportDraft,
  onExportDraft
}: WizardDraftStepProps) {
  const visibleFields = current.fields.filter((field) => (field.visibleWhen ? field.visibleWhen(form) : true));

  function readNextNumberValue(rawValue: string, emptyValue?: number | "" | null): number | "" | null {
    if (rawValue === "") {
      return emptyValue !== undefined ? emptyValue : 0;
    }

    return Number(rawValue);
  }

  return (
    <div className="section">
      <h2>{current.title}</h2>
      <div className="note">
        <strong>{activeProjectId ? "Editing saved project" : "Working on a new draft"}</strong>
        <div className="muted">
          {activeProjectId
            ? `Project id: ${activeProjectId}. ${hasUnsavedChanges ? "Unsaved changes pending local update." : "All changes saved locally."}`
            : "Saving will create a new local project record."}
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
        {visibleFields.map((field) => {
          const targetSection = field.section ?? current.section;
          const value = getSectionFieldValue(form, targetSection, field.key);
          const fieldType = field.kind ?? "text";
          const fieldId = `${String(targetSection)}-${field.key}`;

          if (fieldType === "textarea") {
            return (
              <div key={fieldId} className="field full">
                <label htmlFor={fieldId}>{field.label}</label>
                <textarea
                  id={fieldId}
                  value={String(value ?? "")}
                  onChange={(event) => onUpdateSection(targetSection, field.key, event.target.value)}
                />
              </div>
            );
          }

          if (fieldType === "boolean") {
            return (
              <div key={fieldId} className="field">
                <label htmlFor={fieldId}>{field.label}</label>
                <select
                  id={fieldId}
                  value={String(value)}
                  onChange={(event) => onUpdateSection(targetSection, field.key, event.target.value === "true")}
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </div>
            );
          }

          if (Array.isArray(field.options) && field.options.length > 0) {
            return (
              <div key={fieldId} className={`field ${field.fullWidth ? "full" : ""}`}>
                <label htmlFor={fieldId}>{field.label}</label>
                <select
                  id={fieldId}
                  value={String(value ?? "")}
                  onChange={(event) => onUpdateSection(targetSection, field.key, event.target.value)}
                >
                  {field.options.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            );
          }

          return (
            <div key={fieldId} className={`field ${field.fullWidth ? "full" : ""}`}>
              <label htmlFor={fieldId}>{field.label}</label>
              <input
                id={fieldId}
                type={fieldType === "number" ? "number" : "text"}
                step={fieldType === "number" ? "any" : undefined}
                value={String(value ?? "")}
                onChange={(event) =>
                  onUpdateSection(
                    targetSection,
                    field.key,
                    fieldType === "number"
                      ? readNextNumberValue(event.target.value, field.emptyValue)
                      : event.target.value
                  )
                }
              />
            </div>
          );
        })}
      </div>

      <div className="actions">
        <button className="btn secondary" disabled={!canGoBack || loading} onClick={onBack}>
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
        <button className="btn ghost" disabled={loading || saving} onClick={onSave}>
          {saving ? "Saving..." : activeProjectId ? "Update project" : "Save project"}
        </button>
        <button className="btn primary" disabled={loading} onClick={onNext}>
          Next
        </button>
      </div>
    </div>
  );
}
