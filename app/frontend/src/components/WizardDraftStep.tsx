import { useState, type RefObject } from "react";

import { t } from "../i18n";
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

const validationIssueKeys: Record<string, string> = {
  "Project name is required.": "wizardDraft.validation.projectNameRequired",
  "Change description is required.": "wizardDraft.validation.changeDescriptionRequired",
  "Traffic split must contain at least two positive weights.": "wizardDraft.validation.trafficSplitPositive",
  "Traffic split length must match variants count.": "wizardDraft.validation.trafficSplitLength",
  "Expected daily traffic must be greater than 0.": "wizardDraft.validation.expectedDailyTrafficPositive",
  "Audience share in test must be between 0 and 1.": "wizardDraft.validation.audienceShareRange",
  "Variants count must be an integer between 2 and 10.": "wizardDraft.validation.variantsCountRange",
  "Primary metric name is required.": "wizardDraft.validation.primaryMetricRequired",
  "Binary baseline value must be between 0 and 1.": "wizardDraft.validation.binaryBaselineRange",
  "Continuous baseline value must be greater than 0.": "wizardDraft.validation.continuousBaselinePositive",
  "MDE % must be greater than 0.": "wizardDraft.validation.mdePositive",
  "Alpha must be between 0 and 1.": "wizardDraft.validation.alphaRange",
  "Power must be between 0 and 1.": "wizardDraft.validation.powerRange",
  "Continuous metrics require a positive std dev.": "wizardDraft.validation.continuousStdPositive",
  "CUPED pre-experiment std dev must be positive.": "wizardDraft.validation.cupedStdPositive",
  "CUPED correlation must be between -1 and 1.": "wizardDraft.validation.cupedCorrelationRange",
  "Desired precision must be greater than 0 in Bayesian mode.": "wizardDraft.validation.desiredPrecisionPositive",
  "Credibility must be between 0.5 and 1.": "wizardDraft.validation.credibilityRange",
  "Guardrail metrics cannot exceed 3 items.": "wizardDraft.validation.guardrailsMax",
  "Guardrail metric names are required.": "wizardDraft.validation.guardrailNameRequired",
  "Binary guardrails require a baseline % between 0 and 100.": "wizardDraft.validation.guardrailBinaryBaselineRange",
  "Continuous guardrails require baseline mean and positive std dev.": "wizardDraft.validation.guardrailContinuousFields",
  "Guardrail metric type must be either binary or continuous.": "wizardDraft.validation.guardrailMetricType",
  "Metric type must be either binary or continuous.": "wizardDraft.validation.metricType"
};

function translateValidationIssue(issue: string): string {
  const key = validationIssueKeys[issue];
  return key ? t(key) : issue;
}

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
  const translatedValidationErrors = validationErrors.map((issue) => translateValidationIssue(issue));

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
      <h2 ref={headingRef} tabIndex={-1}>{t(`wizardDraft.sections.${current.section}`)}</h2>
      <div className="note">
        <strong>{activeProjectId ? t("wizardDraft.note.editingSavedProject") : t("wizardDraft.note.workingOnNewDraft")}</strong>
        <div className="muted">
          {activeProjectId
            ? t("wizardDraft.note.projectIdStatus", {
                projectId: activeProjectId,
                status: hasUnsavedChanges
                  ? t("wizardDraft.note.unsavedChangesPending")
                  : t("wizardDraft.note.allChangesSaved")
              })
            : t("wizardDraft.note.savingCreatesProject")}
        </div>
      </div>
      {validationErrors.length > 0 ? (
        <div className="status" role="alert" aria-live="polite">
          <strong>{t("wizardDraft.fixFields")}:</strong>
          <ul className="list">
            {translatedValidationErrors.map((issue) => (
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
                  {t("wizardDraft.analysisFramework.title")}
                </label>
                <p className={styles["guardrail-hint"]}>
                  {t("wizardDraft.analysisFramework.description")}
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
                  <strong>{t("wizardDraft.analysisFramework.frequentist")}</strong>
                </span>
                <span className="muted">{t("wizardDraft.analysisFramework.frequentistDescription")}</span>
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
                  <strong>{t("wizardDraft.analysisFramework.bayesian")}</strong>
                </span>
                <span className="muted">{t("wizardDraft.analysisFramework.bayesianDescription")}</span>
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
          const translatedFieldLabel = t(`wizardDraft.fields.${String(targetSection)}.${field.key}`, { defaultValue: field.label });
          const translatedFieldError = fieldError ? translateValidationIssue(fieldError) : fieldError;
          const translatedGlobalFieldError = globalFieldError ? translateValidationIssue(globalFieldError) : globalFieldError;
          const translatedHelpText = field.helpText
            ? t(`wizardDraft.helpText.${field.key}`, { defaultValue: field.helpText })
            : null;
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
                  ? `${translatedFieldLabel} (${precisionUnit})`
                  : translatedFieldLabel}
              </span>
              {translatedHelpText ? <Tooltip content={translatedHelpText} /> : null}
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
                  <option value="true">{t("wizardDraft.common.yes")}</option>
                  <option value="false">{t("wizardDraft.common.no")}</option>
                </select>
                {translatedFieldError ? <span className={styles["field-error"]}>{translatedFieldError}</span> : null}
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
                      {t(`wizardDraft.options.${String(targetSection)}.${field.key}.${option.value}`, { defaultValue: option.label })}
                    </option>
                  ))}
                </select>
                {translatedFieldError ? <span className={styles["field-error"]}>{translatedFieldError}</span> : null}
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
                {translatedFieldError ? <span className={styles["field-error"]}>{translatedFieldError}</span> : null}
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
                {translatedFieldError ? <span className={styles["field-error"]}>{translatedFieldError}</span> : null}
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
                {translatedFieldError ? <span className={styles["field-error"]}>{translatedFieldError}</span> : null}
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
              {translatedFieldError ? <span className={styles["field-error"]}>{translatedFieldError}</span> : null}
            </div>
          );
        })}
      {current.section === "constraints" ? (
          <div className={["field", styles.full].join(" ")}>
            <label htmlFor="constraints-n_looks">
              <span className={styles["field-label"]}>
                <span>{t("wizardDraft.interimAnalyses.title")}</span>
                <Tooltip content={t("wizardDraft.interimAnalyses.tooltip")} />
              </span>
            </label>
            <select
              id="constraints-n_looks"
              value={String(interimLooks)}
              onChange={(event) => handleFieldChange("constraints", "n_looks", Number(event.target.value), "constraints-n_looks")}
              onBlurCapture={() => handleFieldBlur("constraints-n_looks", "constraints", "n_looks")}
              onBlur={() => handleFieldBlur("constraints-n_looks", "constraints", "n_looks")}
            >
              <option value="1">{t("wizardDraft.interimAnalyses.options.1")}</option>
              <option value="2">{t("wizardDraft.interimAnalyses.options.2")}</option>
              <option value="3">{t("wizardDraft.interimAnalyses.options.3")}</option>
              <option value="4">{t("wizardDraft.interimAnalyses.options.4")}</option>
              <option value="5">{t("wizardDraft.interimAnalyses.options.5")}</option>
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
                {t("wizardDraft.cuped.title")}
              </label>
              <p className={styles["guardrail-hint"]}>
                {t("wizardDraft.cuped.description")}
              </p>
            </div>
            <span className={styles["optional-badge"]}>{t("wizardDraft.common.optional")}</span>
          </div>
          <label className={styles["cuped-toggle"]} htmlFor="metrics-cuped_enabled">
            <input
              id="metrics-cuped_enabled"
              type="checkbox"
              checked={form.metrics.cuped_enabled}
              onChange={(event) => handleFieldChange("metrics", "cuped_enabled", event.target.checked, "metrics-cuped_enabled")}
            />
            <span>{t("wizardDraft.cuped.enable")}</span>
            <Tooltip content={t("wizardDraft.cuped.enableTooltip")} />
          </label>
          {form.metrics.cuped_enabled ? (
            <div className={styles["cuped-fields"]}>
              <div className={["field", cupedStdFieldError || cupedStdGlobalError ? styles["error-state"] : ""].filter(Boolean).join(" ")}>
                <label htmlFor={cupedStdFieldId}>
                  <span className={styles["field-label"]}>
                    <span>{t("wizardDraft.cuped.preExperimentStdDev")}</span>
                    <Tooltip content={t("wizardDraft.cuped.preExperimentStdDevTooltip")} />
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
                  <span className={styles["field-error"]}>{translateValidationIssue((cupedStdFieldError || cupedStdGlobalError) ?? "")}</span>
                ) : null}
              </div>
              <div className={["field", cupedCorrelationFieldError || cupedCorrelationGlobalError ? styles["error-state"] : ""].filter(Boolean).join(" ")}>
                <label htmlFor={cupedCorrelationFieldId}>
                  <span className={styles["field-label"]}>
                    <span>{t("wizardDraft.cuped.correlationWithOutcome")}</span>
                    <Tooltip content={t("wizardDraft.cuped.correlationWithOutcomeTooltip")} />
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
                  <span className={styles["field-error"]}>{translateValidationIssue((cupedCorrelationFieldError || cupedCorrelationGlobalError) ?? "")}</span>
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
                {t("wizardDraft.guardrails.title")}
              </label>
              <p className={styles["guardrail-hint"]}>
                {t("wizardDraft.guardrails.description")}
              </p>
            </div>
            <span className={styles["optional-badge"]}>{t("wizardDraft.common.optional")}</span>
          </div>
          <div className={styles["guardrail-list"]}>
            {guardrailMetrics.map((guardrail, index) => (
              <div key={`${guardrail.name}-${index}`} className={styles["guardrail-item"]}>
                <div className={styles["guardrail-row"]}>
                  <div className="field">
                    <label htmlFor={`guardrail-metric-name-${index + 1}`}>{t("wizardDraft.guardrails.metricName")}</label>
                    <input
                      id={`guardrail-metric-name-${index + 1}`}
                      aria-label={t("wizardDraft.guardrails.metricNameAriaLabel", { index: index + 1 })}
                      value={guardrail.name}
                      onChange={(event) => updateGuardrail(index, "name", event.target.value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor={`guardrail-metric-type-${index + 1}`}>{t("wizardDraft.guardrails.metricType")}</label>
                    <select
                      id={`guardrail-metric-type-${index + 1}`}
                      aria-label={t("wizardDraft.guardrails.metricTypeAriaLabel", { index: index + 1 })}
                      value={guardrail.metric_type}
                      onChange={(event) => updateGuardrail(index, "metric_type", event.target.value)}
                    >
                      <option value="binary">{t("wizardDraft.guardrails.binaryPct")}</option>
                      <option value="continuous">{t("wizardDraft.guardrails.continuous")}</option>
                    </select>
                  </div>
                  <button
                    className="btn ghost"
                    type="button"
                    aria-label={t("wizardDraft.guardrails.removeAriaLabel", { index: index + 1 })}
                    onClick={() => removeGuardrail(index)}
                  >
                    {t("wizardDraft.guardrails.remove")}
                  </button>
                </div>
                <div className={styles["guardrail-metric-fields"]}>
                  {guardrail.metric_type === "binary" ? (
                    <div className="field">
                      <label htmlFor={`guardrail-baseline-rate-${index + 1}`}>{t("wizardDraft.guardrails.baselinePct")}</label>
                      <input
                        id={`guardrail-baseline-rate-${index + 1}`}
                        aria-label={t("wizardDraft.guardrails.baselineRateAriaLabel", { index: index + 1 })}
                        type="number"
                        step="any"
                        value={String(guardrail.baseline_rate ?? "")}
                        onChange={(event) => updateGuardrail(index, "baseline_rate", readNextNumberValue(event.target.value, ""))}
                      />
                    </div>
                  ) : (
                    <>
                      <div className="field">
                        <label htmlFor={`guardrail-baseline-mean-${index + 1}`}>{t("wizardDraft.guardrails.baselineMean")}</label>
                        <input
                          id={`guardrail-baseline-mean-${index + 1}`}
                          aria-label={t("wizardDraft.guardrails.baselineMeanAriaLabel", { index: index + 1 })}
                          type="number"
                          step="any"
                          value={String(guardrail.baseline_mean ?? "")}
                          onChange={(event) => updateGuardrail(index, "baseline_mean", readNextNumberValue(event.target.value, ""))}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor={`guardrail-std-dev-${index + 1}`}>{t("wizardDraft.guardrails.stdDev")}</label>
                        <input
                          id={`guardrail-std-dev-${index + 1}`}
                          aria-label={t("wizardDraft.guardrails.stdDevAriaLabel", { index: index + 1 })}
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
              {t("wizardDraft.guardrails.add")}
            </button>
          ) : null}
          {guardrailIssues.length > 0 ? (
            <ul className={`list ${styles["guardrail-errors"]}`}>
              {guardrailIssues.map((issue) => (
                <li key={issue}>{translateValidationIssue(issue)}</li>
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
          {t("wizard.actions.back")}
        </button>
        <button className="btn ghost" disabled={loading || saving} onClick={onStartNew}>
          {t("wizardDraft.buttons.newDraft")}
        </button>
        {current.section === "project" ? (
          <button className="btn ghost" disabled={loading || saving} onClick={onOpenTemplateGallery}>
            {t("wizardDraft.buttons.startFromTemplate")}
          </button>
        ) : null}
        <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onImportDraft}>
          {importingDraft ? <><Spinner /> {t("wizardDraft.buttons.importing")}</> : t("wizardDraft.buttons.importDraft")}
        </button>
        <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onExportDraft}>
          {t("wizardDraft.buttons.exportDraft")}
        </button>
        <button
          className="btn ghost"
          disabled={!canMutateBackend || loading || saving}
          title={activeProjectId ? t("wizardDraft.buttons.updateProjectTitle") : t("wizardDraft.buttons.saveProjectTitle")}
          onClick={onSave}
        >
          {saving ? <><Spinner /> {t("wizardDraft.buttons.saving")}</> : activeProjectId ? t("wizardDraft.buttons.updateProject") : t("wizard.actions.save")}
        </button>
        <button className="btn primary" disabled={loading} onClick={onNext}>
          {t("wizard.actions.next")}
        </button>
      </div>
    </div>
  );
}
