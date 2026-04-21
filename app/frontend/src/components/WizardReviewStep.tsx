import type { RefObject } from "react";

import { t } from "../i18n";
import { getReviewSections, type FullPayload } from "../lib/experiment";
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
  "Guardrail metrics cannot exceed 3 items.": "wizardDraft.validation.guardrailsMax",
  "Guardrail metric names are required.": "wizardDraft.validation.guardrailNameRequired",
  "Binary guardrails require a baseline % between 0 and 100.": "wizardDraft.validation.guardrailBinaryBaselineRange",
  "Continuous guardrails require baseline mean and positive std dev.": "wizardDraft.validation.guardrailContinuousFields",
  "Guardrail metric type must be either binary or continuous.": "wizardDraft.validation.guardrailMetricType",
  "Metric type must be either binary or continuous.": "wizardDraft.validation.metricType"
};

const reviewSectionKeys: Record<string, string> = {
  "Project context": "wizardDraft.sections.project",
  "Hypothesis": "wizardDraft.sections.hypothesis",
  "Experiment setup": "wizardDraft.sections.setup",
  "Metrics": "wizardDraft.sections.metrics",
  "Constraints": "wizardDraft.sections.constraints"
};

const reviewLabelKeys: Record<string, string> = {
  "Project name": "wizardDraft.fields.project.project_name",
  "Domain": "wizardDraft.fields.project.domain",
  "Product type": "wizardDraft.fields.project.product_type",
  "Platform": "wizardDraft.fields.project.platform",
  "Market": "wizardDraft.fields.project.market",
  "Project description": "wizardDraft.fields.project.project_description",
  "Change description": "wizardDraft.fields.hypothesis.change_description",
  "Target audience": "wizardDraft.fields.hypothesis.target_audience",
  "Business problem": "wizardDraft.fields.hypothesis.business_problem",
  "Hypothesis statement": "wizardDraft.fields.hypothesis.hypothesis_statement",
  "What to validate": "wizardDraft.fields.hypothesis.what_to_validate",
  "Desired result": "wizardDraft.fields.hypothesis.desired_result",
  "Experiment type": "wizardDraft.fields.setup.experiment_type",
  "Randomization unit": "wizardDraft.fields.setup.randomization_unit",
  "Traffic split": "wizardDraft.fields.setup.traffic_split",
  "Expected daily traffic": "wizardDraft.fields.setup.expected_daily_traffic",
  "Audience share in test": "wizardDraft.fields.setup.audience_share_in_test",
  "Variants count": "wizardDraft.fields.setup.variants_count",
  "Inclusion criteria": "wizardDraft.fields.setup.inclusion_criteria",
  "Exclusion criteria": "wizardDraft.fields.setup.exclusion_criteria",
  "Primary metric": "wizardDraft.fields.metrics.primary_metric_name",
  "Metric type": "wizardDraft.fields.metrics.metric_type",
  "Baseline value": "wizardDraft.fields.metrics.baseline_value",
  "Expected uplift %": "wizardDraft.fields.metrics.expected_uplift_pct",
  "MDE %": "wizardDraft.fields.metrics.mde_pct",
  "Secondary metrics": "wizardDraft.fields.metrics.secondary_metrics",
  "Guardrail metrics": "wizardDraft.fields.metrics.guardrail_metrics",
  "Seasonality present": "wizardDraft.fields.constraints.seasonality_present",
  "Active campaigns present": "wizardDraft.fields.constraints.active_campaigns_present",
  "Returning users present": "wizardDraft.fields.constraints.returning_users_present",
  "Analysis framework": "wizardDraft.analysisFramework.title",
  "Alpha": "wizardDraft.fields.metrics.alpha",
  "Power": "wizardDraft.fields.metrics.power",
  "Interference risk": "wizardDraft.fields.constraints.interference_risk",
  "Technical constraints": "wizardDraft.fields.constraints.technical_constraints",
  "Legal / ethics constraints": "wizardDraft.fields.constraints.legal_or_ethics_constraints",
  "Known risks": "wizardDraft.fields.constraints.known_risks",
  "Deadline pressure": "wizardDraft.fields.constraints.deadline_pressure",
  "Long test possible": "wizardDraft.fields.constraints.long_test_possible",
  "AI context": "wizardDraft.fields.additional_context.llm_context"
};

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
  const reviewSections = getReviewSections(form).map((section) => ({
    ...section,
    title: reviewSectionKeys[section.title] ? t(reviewSectionKeys[section.title]) : section.title,
    items: section.items.map((item) => ({
      ...item,
      label: reviewLabelKeys[item.label] ? t(reviewLabelKeys[item.label]) : item.label
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
          {t("wizard.actions.back")}
        </button>
        <button className="btn ghost" disabled={loading || saving} onClick={onStartNew}>
          {t("wizardReview.newDraftButton")}
        </button>
        <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onImportDraft}>
          {importingDraft ? t("wizardReview.importing") : t("wizardReview.importDraft")}
        </button>
        <button className="btn ghost" disabled={loading || saving || importingDraft} onClick={onExportDraft}>
          {t("wizardReview.exportDraft")}
        </button>
        <button
          className="btn ghost"
          disabled={!canMutateBackend || loading || saving}
          title={activeProjectId ? t("wizardReview.updateProjectTitle") : t("wizardReview.saveProjectTitle")}
          onClick={onSave}
        >
          {saving ? <><Spinner /> {t("wizardReview.saving")}</> : activeProjectId ? t("wizardReview.updateProject") : t("wizard.actions.save")}
        </button>
        <button
          className="btn primary"
          disabled={!canMutateBackend || loading}
          title={t("wizardReview.runAnalysisTitle")}
          onClick={onRunAnalysis}
        >
          {loading ? <><Spinner /> {t("wizardReview.analyzing")}</> : t("wizard.actions.runAnalysis")}
        </button>
      </div>
    </div>
  );
}
