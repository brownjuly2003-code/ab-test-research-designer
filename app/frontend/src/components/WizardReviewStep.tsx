import type { RefObject } from "react";

import { t } from "../i18n";
import { getReviewSections, type FullPayload, type ReviewItem } from "../lib/experiment";
import Spinner from "./Spinner";
import styles from "./WizardDraftStep.module.css";

const reviewValidationIssueKeys: Record<string, string> = {
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
  "Holdout fraction must be between 0 and 1.": "wizardDraft.validation.holdoutFractionRange",
  "Mutually exclusive experiments must be an integer of at least 1.": "wizardDraft.validation.mutuallyExclusiveMin",
  "Guardrail metrics cannot exceed 3 items.": "wizardDraft.validation.guardrailsMax",
  "Guardrail metric names are required.": "wizardDraft.validation.guardrailNameRequired",
  "Binary guardrails require a baseline % between 0 and 100.": "wizardDraft.validation.guardrailBinaryBaselineRange",
  "Continuous guardrails require baseline mean and positive std dev.": "wizardDraft.validation.guardrailContinuousFields",
  "Guardrail metric type must be either binary or continuous.": "wizardDraft.validation.guardrailMetricType",
  "Metric type must be either binary or continuous.": "wizardDraft.validation.metricType"
};

// analysis_mode has no field.options in field-config.ts (its Draft-step UI is a bespoke radio
// pair, not the generic <select>), so its stored value needs its own translation lookup instead
// of the options-array mechanism the rest of the enum-backed fields use below.
const ANALYSIS_MODE_VALUE_KEYS: Record<string, string> = {
  frequentist: "wizardDraft.analysisFramework.frequentist",
  bayesian: "wizardDraft.analysisFramework.bayesian"
};

function translateReviewValue(item: ReviewItem): string {
  if (typeof item.rawValue === "boolean") {
    return item.rawValue ? t("wizardDraft.common.yes") : t("wizardDraft.common.no");
  }
  if (item.section === "constraints" && item.key === "analysis_mode") {
    const valueKey = ANALYSIS_MODE_VALUE_KEYS[String(item.rawValue ?? "")];
    if (valueKey) {
      return t(valueKey);
    }
  }
  if (item.options && item.options.length > 0) {
    const normalized = String(item.rawValue ?? "").trim();
    const match = item.options.find((option) => option.value === normalized);
    if (match) {
      return t(`wizardDraft.options.${item.section}.${item.key}.${match.value}`, { defaultValue: match.label });
    }
  }
  return item.value;
}

type WizardReviewStepProps = {
  headingRef?: RefObject<HTMLHeadingElement | null>;
  form: FullPayload;
  activeProjectId: string | null;
  hasUnsavedChanges: boolean;
  canMutateBackend: boolean;
  isReadOnlySession: boolean;
  canUseCompute: boolean;
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
  isReadOnlySession,
  canUseCompute,
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
  const reviewSections = getReviewSections(form).map((section) => ({
    ...section,
    title: t(`wizardDraft.sections.${section.section}`, { defaultValue: section.title }),
    items: section.items.map((item) => ({
      ...item,
      label: t(`wizardDraft.fields.${item.section}.${item.key}`, { defaultValue: item.label }),
      value: translateReviewValue(item)
    }))
  }));
  const translatedValidationErrors = validationErrors.map((issue) => {
    const key = reviewValidationIssueKeys[issue];
    return key ? t(key) : issue;
  });

  return (
    <div className={`${styles.section} ${styles["step-content"]}`}>
      <h2 ref={headingRef} tabIndex={-1}>{t("wizardReview.title")}</h2>
      <div className="note">
        <strong>{activeProjectId ? t("wizardReview.savedProjectTitle") : t("wizardReview.newDraftTitle")}</strong>
        <div className="muted">
          {activeProjectId
            ? `${hasUnsavedChanges ? t("wizardReview.unsavedChangesPresent") : t("wizardReview.syncedWithLocalStorage")} ${t("wizardReview.description")}`
            : t("wizardReview.description")}
        </div>
      </div>
      {validationErrors.length > 0 ? (
        <div className="status" role="alert" aria-live="polite">
          <strong>{t("wizardReview.fixFields")}:</strong>
          <ul className="list">
            {translatedValidationErrors.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {!canUseCompute ? (
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
      <div className={styles.footer}>
        <div className={styles["footer-tools"]}>
          <button className="btn ghost" disabled={loading || saving} onClick={onStartNew}>
            {t("wizardReview.newDraftButton")}
          </button>
          <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onImportDraft}>
            {importingDraft ? t("wizardReview.importing") : t("wizardReview.importDraft")}
          </button>
          <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onExportDraft}>
            {t("wizardReview.exportDraft")}
          </button>
        </div>
        <div className={["actions", styles["footer-nav"]].join(" ")}>
          <button className="btn secondary btn-back" disabled={loading} onClick={onBack}>
            {t("wizard.actions.back")}
          </button>
          {isReadOnlySession ? null : (
            <button
              className="btn ghost"
              disabled={!canMutateBackend || loading || saving}
              title={activeProjectId ? t("wizardReview.updateProjectTitle") : t("wizardReview.saveProjectTitle")}
              onClick={onSave}
            >
              {saving ? <><Spinner /> {t("wizardReview.saving")}</> : activeProjectId ? t("wizardReview.updateProject") : t("wizard.actions.save")}
            </button>
          )}
          <button
            className="btn primary"
            disabled={!canUseCompute || loading}
            title={t("wizardReview.runAnalysisTitle")}
            onClick={onRunAnalysis}
          >
            {loading ? <><Spinner /> {t("wizardReview.analyzing")}</> : t("wizard.actions.runAnalysis")}
          </button>
        </div>
      </div>
    </div>
  );
}
