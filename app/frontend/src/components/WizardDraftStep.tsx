import { useState, type RefObject } from "react";

import {
  getFieldValidationMessage,
  getSectionFieldValue,
  setSectionFieldValue,
  validateField,
  type DraftFieldValue,
  type FullPayload,
  type FullPayloadSectionKey,
  type GuardrailMetricDraft,
  type SectionConfig
} from "../lib/experiment";
import { useCalculationPreview } from "../hooks/useCalculationPreview";
import LivePreviewPanel from "./LivePreviewPanel";
import SliderInput from "./SliderInput";
import Spinner from "./Spinner";
import Tooltip from "./Tooltip";
import styles from "./WizardDraftStep.module.css";

type WizardDraftStepProps = {
  headingRef?: RefObject<HTMLHeadingElement | null>;
  current: SectionConfig;
  form: FullPayload;
  canGoBack: boolean;
  activeProjectId: string | null;
  hasUnsavedChanges: boolean;
  canMutateBackend: boolean;
  backendMutationMessage: string;
  validationErrors: string[];
  importingDraft: boolean;
  loading: boolean;
  saving: boolean;
  onUpdateSection: (section: FullPayloadSectionKey, key: string, value: DraftFieldValue) => void;
  onBack: () => void;
  onNext: () => void;
  onSave: () => void;
  onStartNew: () => void;
  onOpenTemplateGallery: () => void;
  onImportDraft: () => void;
  onExportDraft: () => void;
};

export default function WizardDraftStep({
  headingRef,
  current,
  form,
  canGoBack,
  activeProjectId,
  hasUnsavedChanges,
  canMutateBackend,
  backendMutationMessage,
  validationErrors,
  importingDraft,
  loading,
  saving,
  onUpdateSection,
  onBack,
  onNext,
  onSave,
  onStartNew,
  onOpenTemplateGallery,
  onImportDraft,
  onExportDraft
}: WizardDraftStepProps) {
  const visibleFields = current.fields
    .filter((field) => (field.visibleWhen ? field.visibleWhen(form) : true))
    .filter((field) => !(current.section === "metrics" && field.key === "guardrail_metrics"))
    .filter((field) => !(current.section === "constraints" && field.key === "analysis_mode"));
  const showLivePreview = current.section === "setup" || current.section === "metrics";
  const previewState = useCalculationPreview(form, showLivePreview);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const guardrailMetrics = form.metrics.guardrail_metrics ?? [];
  const interimLooks = form.constraints.n_looks ?? 1;
  const analysisMode = form.constraints.analysis_mode ?? "frequentist";
  const precisionUnit = form.metrics.metric_type === "binary" ? "pp" : "units";
  const cupedStdFieldId = "metrics-cuped_pre_experiment_std";
  const cupedCorrelationFieldId = "metrics-cuped_correlation";
  const cupedStdFieldError =
    fieldErrors[cupedStdFieldId] ||
    (cupedStdFieldId in fieldErrors ? "" : null);
  const cupedCorrelationFieldError =
    fieldErrors[cupedCorrelationFieldId] ||
    (cupedCorrelationFieldId in fieldErrors ? "" : null);
  const cupedStdGlobalError = getFieldValidationMessage("metrics", "cuped_pre_experiment_std", validationErrors);
  const cupedCorrelationGlobalError = getFieldValidationMessage("metrics", "cuped_correlation", validationErrors);
  const guardrailIssues = validationErrors.filter((issue) => (
    issue === "Guardrail metrics cannot exceed 3 items." ||
    issue === "Guardrail metric names are required." ||
    issue === "Binary guardrails require a baseline % between 0 and 100." ||
    issue === "Continuous guardrails require baseline mean and positive std dev." ||
    issue === "Guardrail metric type must be either binary or continuous."
  ));

  function readNextNumberValue(rawValue: string): number;
  function readNextNumberValue(rawValue: string, emptyValue: number | "" | null | undefined): number | "" | null;
  function readNextNumberValue(rawValue: string, emptyValue: ""): number | "";
  function readNextNumberValue(rawValue: string, emptyValue: null): number | null;
  function readNextNumberValue(rawValue: string, emptyValue: number): number;
  function readNextNumberValue(rawValue: string, emptyValue?: number | "" | null): number | "" | null {
    if (rawValue === "") {
      return emptyValue !== undefined ? emptyValue : 0;
    }

    return Number(rawValue);
  }

  function updateFieldError(fieldId: string, nextForm: FullPayload, section: FullPayloadSectionKey, key: string) {
    setFieldErrors((current) => (
      fieldId in current
        ? {
            ...current,
            [fieldId]: validateField(nextForm, section, key) ?? ""
          }
        : current
    ));
  }

  function handleFieldBlur(fieldId: string, section: FullPayloadSectionKey, key: string) {
    setFieldErrors((current) => ({
      ...current,
      [fieldId]: validateField(form, section, key) ?? ""
    }));
  }

  function handleFieldChange(section: FullPayloadSectionKey, key: string, value: DraftFieldValue, fieldId: string) {
    const nextForm = setSectionFieldValue(form, section, key, value);
    onUpdateSection(section, key, value);
    updateFieldError(fieldId, nextForm, section, key);
  }

  function updateGuardrail(index: number, key: keyof GuardrailMetricDraft, value: GuardrailMetricDraft[keyof GuardrailMetricDraft]) {
    const nextGuardrails: GuardrailMetricDraft[] = guardrailMetrics.map((guardrail, guardrailIndex) => {
      if (guardrailIndex !== index) {
        return guardrail;
      }

      if (key === "metric_type") {
        return value === "continuous"
          ? {
              name: guardrail.name,
              metric_type: "continuous" as const,
              baseline_mean: guardrail.baseline_mean ?? "",
              std_dev: guardrail.std_dev ?? ""
            }
          : {
              name: guardrail.name,
              metric_type: "binary" as const,
              baseline_rate: guardrail.baseline_rate ?? ""
            };
      }

      return {
        ...guardrail,
        [key]: value
      };
    });

    onUpdateSection("metrics", "guardrail_metrics", nextGuardrails);
  }

  function addGuardrail() {
    onUpdateSection("metrics", "guardrail_metrics", [
      ...guardrailMetrics,
      {
        name: "",
        metric_type: "binary",
        baseline_rate: ""
      }
    ]);
  }

  function removeGuardrail(index: number) {
    onUpdateSection(
      "metrics",
      "guardrail_metrics",
      guardrailMetrics.filter((_, guardrailIndex) => guardrailIndex !== index)
    );
  }

  return (
    <div className={`${styles.section} ${styles["step-content"]}`}>
      <h2 ref={headingRef} tabIndex={-1}>{current.title}</h2>
      <div className="note">
        <strong>{activeProjectId ? "Editing saved project" : "Working on a new draft"}</strong>
        <div className="muted">
          {activeProjectId
            ? `Project id: ${activeProjectId}. ${hasUnsavedChanges ? "Unsaved changes pending local update." : "All changes saved locally."}`
            : "Saving will create a new local project record."}
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
      <div className={styles.fields}>
        {current.section === "constraints" ? (
          <div className={["field", styles.full, styles["guardrail-section"]].join(" ")}>
            <div className={styles["guardrail-header"]}>
              <div>
                <label className={styles["guardrail-title"]} htmlFor="constraints-analysis_mode-frequentist">
                  Analysis framework
                </label>
                <p className={styles["guardrail-hint"]}>
                  Choose whether planning uses classic NHST power or Bayesian precision.
                </p>
              </div>
            </div>
            <div
              style={{
                display: "grid",
                gap: "12px",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))"
              }}
            >
              <label
                style={{
                  display: "grid",
                  gap: "8px",
                  padding: "14px",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--color-border-soft)",
                  background: "var(--color-surface-elevated)",
                  cursor: "pointer"
                }}
              >
                <span style={{ display: "inline-flex", alignItems: "center", gap: "10px" }}>
                  <input
                    id="constraints-analysis_mode-frequentist"
                    type="radio"
                    name="analysis_mode"
                    value="frequentist"
                    checked={analysisMode === "frequentist"}
                    onChange={() => handleFieldChange("constraints", "analysis_mode", "frequentist", "constraints-analysis_mode")}
                  />
                  <strong>Frequentist</strong>
                </span>
                <span className="muted">Set alpha and power for the classic fixed-horizon approach.</span>
              </label>
              <label
                style={{
                  display: "grid",
                  gap: "8px",
                  padding: "14px",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--color-border-soft)",
                  background: "var(--color-surface-elevated)",
                  cursor: "pointer"
                }}
              >
                <span style={{ display: "inline-flex", alignItems: "center", gap: "10px" }}>
                  <input
                    id="constraints-analysis_mode-bayesian"
                    type="radio"
                    name="analysis_mode"
                    value="bayesian"
                    checked={analysisMode === "bayesian"}
                    onChange={() => handleFieldChange("constraints", "analysis_mode", "bayesian", "constraints-analysis_mode")}
                  />
                  <strong>Bayesian</strong>
                </span>
                <span className="muted">Set desired precision and credibility for interval-based planning.</span>
              </label>
            </div>
          </div>
        ) : null}
        {visibleFields.map((field) => {
          const targetSection = field.section ?? current.section;
          const value = getSectionFieldValue(form, targetSection, field.key);
          const fieldType = field.kind ?? "text";
          const fieldId = `${String(targetSection)}-${field.key}`;
          const fieldError =
            fieldErrors[fieldId] ||
            (fieldId in fieldErrors ? "" : null);
          const globalFieldError = getFieldValidationMessage(targetSection, field.key, validationErrors);
          const showFieldState = Boolean(fieldError || globalFieldError);
          const filled =
            typeof value === "boolean"
              ? true
              : Array.isArray(value)
                ? value.length > 0
                : String(value ?? "").trim().length > 0;
          const fieldClassName = [
            "field",
            field.fullWidth ? styles.full : "",
            showFieldState ? styles["error-state"] : "",
            filled ? styles.filled : ""
          ]
            .filter(Boolean)
            .join(" ");
          const label = (
            <span className={styles["field-label"]}>
              <span>
                {targetSection === "constraints" && field.key === "desired_precision"
                  ? `${field.label} (${precisionUnit})`
                  : field.label}
              </span>
              {field.helpText ? <Tooltip content={field.helpText} /> : null}
            </span>
          );

          if (fieldType === "textarea") {
            return (
              <div key={fieldId} className={fieldClassName}>
                <label htmlFor={fieldId}>{label}</label>
                <textarea
                  id={fieldId}
                  aria-invalid={showFieldState ? "true" : undefined}
                  value={String(value ?? "")}
                  onChange={(event) => handleFieldChange(targetSection, field.key, event.target.value, fieldId)}
                  onBlurCapture={() => handleFieldBlur(fieldId, targetSection, field.key)}
                  onBlur={() => handleFieldBlur(fieldId, targetSection, field.key)}
                />
                {fieldError ? <span className={styles["field-error"]}>{fieldError}</span> : null}
              </div>
            );
          }

          if (fieldType === "boolean") {
            return (
              <div key={fieldId} className={fieldClassName}>
                <label htmlFor={fieldId}>{label}</label>
                <select
                  id={fieldId}
                  aria-invalid={showFieldState ? "true" : undefined}
                  value={String(value)}
                  onChange={(event) => handleFieldChange(targetSection, field.key, event.target.value === "true", fieldId)}
                  onBlurCapture={() => handleFieldBlur(fieldId, targetSection, field.key)}
                  onBlur={() => handleFieldBlur(fieldId, targetSection, field.key)}
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
                {fieldError ? <span className={styles["field-error"]}>{fieldError}</span> : null}
              </div>
            );
          }

          if (Array.isArray(field.options) && field.options.length > 0) {
            return (
              <div key={fieldId} className={fieldClassName}>
                <label htmlFor={fieldId}>{label}</label>
                <select
                  id={fieldId}
                  aria-invalid={showFieldState ? "true" : undefined}
                  value={String(value ?? "")}
                  onChange={(event) => handleFieldChange(targetSection, field.key, event.target.value, fieldId)}
                  onBlurCapture={() => handleFieldBlur(fieldId, targetSection, field.key)}
                  onBlur={() => handleFieldBlur(fieldId, targetSection, field.key)}
                >
                  {field.options.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                {fieldError ? <span className={styles["field-error"]}>{fieldError}</span> : null}
              </div>
            );
          }

          if (targetSection === "metrics" && field.key === "mde_pct" && typeof value === "number") {
            return (
              <div key={fieldId} className={fieldClassName}>
                <SliderInput
                  id={fieldId}
                  label={field.label}
                  helpText={field.helpText}
                  value={value}
                  min={0.1}
                  max={form.metrics.metric_type === "continuous" ? 50 : 20}
                  step={0.1}
                  unit="%"
                  formatValue={(nextValue) => `${nextValue.toFixed(1)}%`}
                  ariaInvalid={showFieldState}
                  onBlur={() => handleFieldBlur(fieldId, targetSection, field.key)}
                  onChange={(nextValue) => handleFieldChange(targetSection, field.key, nextValue, fieldId)}
                />
                {fieldError ? <span className={styles["field-error"]}>{fieldError}</span> : null}
              </div>
            );
          }

          if (targetSection === "metrics" && field.key === "power" && typeof value === "number") {
            return (
              <div key={fieldId} className={fieldClassName}>
                <SliderInput
                  id={fieldId}
                  label={field.label}
                  helpText={field.helpText}
                  value={value}
                  min={0.7}
                  max={0.99}
                  step={0.01}
                  formatValue={(nextValue) => `${Math.round(nextValue * 100)}%`}
                  ariaInvalid={showFieldState}
                  onBlur={() => handleFieldBlur(fieldId, targetSection, field.key)}
                  onChange={(nextValue) => handleFieldChange(targetSection, field.key, nextValue, fieldId)}
                />
                {fieldError ? <span className={styles["field-error"]}>{fieldError}</span> : null}
              </div>
            );
          }

          if (targetSection === "constraints" && field.key === "credibility" && typeof value === "number") {
            return (
              <div key={fieldId} className={fieldClassName}>
                <SliderInput
                  id={fieldId}
                  label={field.label}
                  helpText={field.helpText}
                  value={value}
                  min={0.8}
                  max={0.99}
                  step={0.01}
                  formatValue={(nextValue) => `${Math.round(nextValue * 100)}%`}
                  ariaInvalid={showFieldState}
                  onBlur={() => handleFieldBlur(fieldId, targetSection, field.key)}
                  onChange={(nextValue) => handleFieldChange(targetSection, field.key, nextValue, fieldId)}
                />
                {fieldError ? <span className={styles["field-error"]}>{fieldError}</span> : null}
              </div>
            );
          }

          return (
            <div key={fieldId} className={fieldClassName}>
              <label htmlFor={fieldId}>{label}</label>
              <input
                id={fieldId}
                type={fieldType === "number" ? "number" : "text"}
                step={fieldType === "number" ? "any" : undefined}
                aria-invalid={showFieldState ? "true" : undefined}
                value={String(value ?? "")}
                onChange={(event) =>
                  handleFieldChange(
                    targetSection,
                    field.key,
                    fieldType === "number"
                      ? readNextNumberValue(event.target.value, field.emptyValue)
                      : event.target.value,
                    fieldId
                  )
                }
                onBlurCapture={() => handleFieldBlur(fieldId, targetSection, field.key)}
                onBlur={() => handleFieldBlur(fieldId, targetSection, field.key)}
              />
              {fieldError ? <span className={styles["field-error"]}>{fieldError}</span> : null}
            </div>
          );
        })}
        {current.section === "constraints" ? (
          <div className={["field", styles.full].join(" ")}>
            <label htmlFor="constraints-n_looks">
              <span className={styles["field-label"]}>
                <span>Interim analyses</span>
                <Tooltip content="Number of times you plan to check results during the experiment. 1 keeps the standard fixed-horizon test. 2-5 enables O'Brien-Fleming group sequential monitoring with early stopping boundaries." />
              </span>
            </label>
            <select
              id="constraints-n_looks"
              value={String(interimLooks)}
              onChange={(event) => handleFieldChange("constraints", "n_looks", Number(event.target.value), "constraints-n_looks")}
              onBlurCapture={() => handleFieldBlur("constraints-n_looks", "constraints", "n_looks")}
              onBlur={() => handleFieldBlur("constraints-n_looks", "constraints", "n_looks")}
            >
              <option value="1">1 - Fixed horizon (no interim analyses)</option>
              <option value="2">2 - One interim + final</option>
              <option value="3">3 - Two interims + final</option>
              <option value="4">4 - Three interims + final</option>
              <option value="5">5 - Four interims + final</option>
            </select>
          </div>
        ) : null}
      </div>
      {current.section === "metrics" && form.metrics.metric_type === "continuous" ? (
        <div
          className={[
            "field",
            styles.full,
            styles["cuped-section"],
            cupedStdGlobalError || cupedCorrelationGlobalError ? styles["error-state"] : ""
          ].filter(Boolean).join(" ")}
        >
          <div className={styles["cuped-header"]}>
            <div>
              <label className={styles["guardrail-title"]} htmlFor="metrics-cuped_enabled">
                CUPED variance reduction
              </label>
              <p className={styles["guardrail-hint"]}>
                Use correlated pre-experiment behavior to reduce variance and compare naive versus CUPED-adjusted sample size.
              </p>
            </div>
            <span className={styles["optional-badge"]}>Optional</span>
          </div>
          <label className={styles["cuped-toggle"]} htmlFor="metrics-cuped_enabled">
            <input
              id="metrics-cuped_enabled"
              type="checkbox"
              checked={form.metrics.cuped_enabled}
              onChange={(event) => handleFieldChange("metrics", "cuped_enabled", event.target.checked, "metrics-cuped_enabled")}
            />
            <span>Enable CUPED variance reduction</span>
            <Tooltip content="If you have pre-experiment data correlated with the outcome metric, CUPED can reduce required sample size by rho squared." />
          </label>
          {form.metrics.cuped_enabled ? (
            <div className={styles["cuped-fields"]}>
              <div className={["field", cupedStdFieldError || cupedStdGlobalError ? styles["error-state"] : ""].filter(Boolean).join(" ")}>
                <label htmlFor={cupedStdFieldId}>
                  <span className={styles["field-label"]}>
                    <span>Pre-experiment std dev</span>
                    <Tooltip content="Standard deviation of the pre-experiment covariate, such as revenue in the week before the test." />
                  </span>
                </label>
                <input
                  id={cupedStdFieldId}
                  type="number"
                  step="any"
                  value={String(form.metrics.cuped_pre_experiment_std ?? "")}
                  onChange={(event) =>
                    handleFieldChange("metrics", "cuped_pre_experiment_std", readNextNumberValue(event.target.value, ""), cupedStdFieldId)
                  }
                  onBlurCapture={() => handleFieldBlur(cupedStdFieldId, "metrics", "cuped_pre_experiment_std")}
                  onBlur={() => handleFieldBlur(cupedStdFieldId, "metrics", "cuped_pre_experiment_std")}
                />
                {cupedStdFieldError || cupedStdGlobalError ? (
                  <span className={styles["field-error"]}>{cupedStdFieldError || cupedStdGlobalError}</span>
                ) : null}
              </div>
              <div className={["field", cupedCorrelationFieldError || cupedCorrelationGlobalError ? styles["error-state"] : ""].filter(Boolean).join(" ")}>
                <label htmlFor={cupedCorrelationFieldId}>
                  <span className={styles["field-label"]}>
                    <span>Correlation with outcome</span>
                    <Tooltip content="Pearson correlation between the pre-experiment covariate and the experiment outcome. Typical values are 0.3 to 0.7." />
                  </span>
                </label>
                <input
                  id={cupedCorrelationFieldId}
                  type="number"
                  min="-0.99"
                  max="0.99"
                  step="any"
                  value={String(form.metrics.cuped_correlation ?? "")}
                  onChange={(event) =>
                    handleFieldChange("metrics", "cuped_correlation", readNextNumberValue(event.target.value, ""), cupedCorrelationFieldId)
                  }
                  onBlurCapture={() => handleFieldBlur(cupedCorrelationFieldId, "metrics", "cuped_correlation")}
                  onBlur={() => handleFieldBlur(cupedCorrelationFieldId, "metrics", "cuped_correlation")}
                />
                {cupedCorrelationFieldError || cupedCorrelationGlobalError ? (
                  <span className={styles["field-error"]}>{cupedCorrelationFieldError || cupedCorrelationGlobalError}</span>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      {current.section === "metrics" ? (
        <div
          className={[
            "field",
            styles.full,
            styles["guardrail-section"],
            guardrailIssues.length > 0 ? styles["error-state"] : ""
          ].join(" ")}
        >
          <div className={styles["guardrail-header"]}>
            <div>
              <label className={styles["guardrail-title"]} htmlFor="guardrail-metric-name-1">
                Guardrail metrics
              </label>
              <p className={styles["guardrail-hint"]}>
                Metrics to monitor without changing primary sample size. Up to 3 guardrails are supported.
              </p>
            </div>
            <span className={styles["optional-badge"]}>Optional</span>
          </div>
          <div className={styles["guardrail-list"]}>
            {guardrailMetrics.map((guardrail, index) => (
              <div key={`${guardrail.name}-${index}`} className={styles["guardrail-item"]}>
                <div className={styles["guardrail-row"]}>
                  <div className="field">
                    <label htmlFor={`guardrail-metric-name-${index + 1}`}>Metric name</label>
                    <input
                      id={`guardrail-metric-name-${index + 1}`}
                      aria-label={`Guardrail metric name ${index + 1}`}
                      value={guardrail.name}
                      onChange={(event) => updateGuardrail(index, "name", event.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor={`guardrail-metric-type-${index + 1}`}>Metric type</label>
                    <select
                      id={`guardrail-metric-type-${index + 1}`}
                      aria-label={`Guardrail metric type ${index + 1}`}
                      value={guardrail.metric_type}
                      onChange={(event) => updateGuardrail(index, "metric_type", event.target.value)}
                    >
                      <option value="binary">Binary (%)</option>
                      <option value="continuous">Continuous</option>
                    </select>
                  </div>
                  <button
                    className="btn ghost"
                    type="button"
                    aria-label={`Remove guardrail ${index + 1}`}
                    onClick={() => removeGuardrail(index)}
                  >
                    Remove
                  </button>
                </div>
                <div className={styles["guardrail-metric-fields"]}>
                  {guardrail.metric_type === "binary" ? (
                    <div className="field">
                      <label htmlFor={`guardrail-baseline-rate-${index + 1}`}>Baseline %</label>
                      <input
                        id={`guardrail-baseline-rate-${index + 1}`}
                        aria-label={`Guardrail baseline rate ${index + 1}`}
                        type="number"
                        step="any"
                        value={String(guardrail.baseline_rate ?? "")}
                        onChange={(event) => updateGuardrail(index, "baseline_rate", readNextNumberValue(event.target.value, ""))}
                      />
                    </div>
                  ) : (
                    <>
                      <div className="field">
                        <label htmlFor={`guardrail-baseline-mean-${index + 1}`}>Baseline mean</label>
                        <input
                          id={`guardrail-baseline-mean-${index + 1}`}
                          aria-label={`Guardrail baseline mean ${index + 1}`}
                          type="number"
                          step="any"
                          value={String(guardrail.baseline_mean ?? "")}
                          onChange={(event) => updateGuardrail(index, "baseline_mean", readNextNumberValue(event.target.value, ""))}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor={`guardrail-std-dev-${index + 1}`}>Std dev</label>
                        <input
                          id={`guardrail-std-dev-${index + 1}`}
                          aria-label={`Guardrail std dev ${index + 1}`}
                          type="number"
                          step="any"
                          value={String(guardrail.std_dev ?? "")}
                          onChange={(event) => updateGuardrail(index, "std_dev", readNextNumberValue(event.target.value, ""))}
                        />
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
          {guardrailMetrics.length < 3 ? (
            <button className="btn secondary" type="button" onClick={addGuardrail}>
              Add guardrail metric
            </button>
          ) : null}
          {guardrailIssues.length > 0 ? (
            <ul className={`list ${styles["guardrail-errors"]}`}>
              {guardrailIssues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {showLivePreview ? (
        <LivePreviewPanel
          result={previewState.result}
          isLoading={previewState.isLoading}
          error={previewState.error}
        />
      ) : null}

      <div className="actions">
        <button className="btn secondary" disabled={!canGoBack || loading} onClick={onBack}>
          Back
        </button>
        <button className="btn ghost" disabled={loading || saving} onClick={onStartNew}>
          New draft
        </button>
        {current.section === "project" ? (
          <button className="btn ghost" disabled={loading || saving} onClick={onOpenTemplateGallery}>
            Start from template
          </button>
        ) : null}
        <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onImportDraft}>
          {importingDraft ? <><Spinner /> Importing...</> : "Import draft JSON"}
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
        <button className="btn primary" disabled={loading} onClick={onNext}>
          Next
        </button>
      </div>
    </div>
  );
}
