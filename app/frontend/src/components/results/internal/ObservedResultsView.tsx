import { type Dispatch, type SetStateAction, Suspense, lazy } from "react";
import { useTranslation } from "react-i18next";
import type { ResultsAnalysisResponse, SavedProject } from "../../../lib/experiment";
import type { ProjectAnalysisRun } from "../../../lib/experiment";
import type { ActualResultsState, BinaryResultsForm, ContinuousResultsForm, CountResultsForm, ObservedBaseMetricType, ObservedMetricType, ObservedTestSelection } from "../observedResultsShared";
import { formatObservedValue, observedFormKind, observedTestButtons, observedTestHintKey } from "../observedResultsShared";
import ChartErrorBoundary from "../../ChartErrorBoundary";
import ForestPlot from "../../ForestPlot";
import Icon from "../../Icon";

// The guided "which test should I use?" helper is an optional, collapsed-by-default aid; lazy-loading
// it keeps the main bundle under the 500 kB budget (same pattern as the other lazy result sections).
const TestChooser = lazy(() => import("./TestChooser"));

type FieldConfig<Key extends string> = {
  id: string;
  label: string;
  key: Key;
  step: string;
  min?: string;
  max?: string;
  inputMode?: "numeric";
};

type ObservedResultsViewProps = {
  analysisMetricType: ObservedMetricType;
  baseMetricType: ObservedBaseMetricType;
  showTestToggle: boolean;
  observedTest: ObservedTestSelection;
  onSelectTest: (test: ObservedTestSelection) => void;
  actualResults: ActualResultsState;
  setActualResults: Dispatch<SetStateAction<ActualResultsState>>;
  canMutateBackend: boolean;
  isReadOnlySession: boolean;
  canUseCompute: boolean;
  backendMutationMessage: string;
  activeProject: SavedProject | null;
  selectedHistoryRun: ProjectAnalysisRun | null;
  canSaveObservedResults: boolean;
  resultsAnalysis: ResultsAnalysisResponse | null;
  resultsLoading: boolean;
  resultsSaving: boolean;
  resultsError: string;
  resultsSaveMessage: string;
  onRunAnalysis: () => void;
  onSave: () => void;
};

export default function ObservedResultsView({
  analysisMetricType,
  baseMetricType,
  showTestToggle,
  observedTest,
  onSelectTest,
  actualResults,
  setActualResults,
  canMutateBackend,
  isReadOnlySession,
  canUseCompute,
  backendMutationMessage,
  activeProject,
  selectedHistoryRun,
  canSaveObservedResults,
  resultsAnalysis,
  resultsLoading,
  resultsSaving,
  resultsError,
  resultsSaveMessage,
  onRunAnalysis,
  onSave
}: ObservedResultsViewProps) {
  const { t } = useTranslation();
  const binaryFields: FieldConfig<keyof BinaryResultsForm>[] = [
    { id: "results-control-conversions", label: t("results.observedResults.fields.controlConversions"), key: "control_conversions", min: "0", step: "1", inputMode: "numeric" },
    { id: "results-control-users", label: t("results.observedResults.fields.controlUsers"), key: "control_users", min: "1", step: "1", inputMode: "numeric" },
    { id: "results-treatment-conversions", label: t("results.observedResults.fields.treatmentConversions"), key: "treatment_conversions", min: "0", step: "1", inputMode: "numeric" },
    { id: "results-treatment-users", label: t("results.observedResults.fields.treatmentUsers"), key: "treatment_users", min: "1", step: "1", inputMode: "numeric" },
    { id: "results-alpha-binary", label: t("results.observedResults.fields.alpha"), key: "alpha", min: "0.001", max: "0.1", step: "0.001" }
  ] as const;
  const continuousFields: FieldConfig<keyof ContinuousResultsForm>[] = [
    { id: "results-control-mean", label: t("results.observedResults.fields.controlMean"), key: "control_mean", step: "any" },
    { id: "results-control-std", label: t("results.observedResults.fields.controlStdDev"), key: "control_std", min: "0.0001", step: "any" },
    { id: "results-control-n", label: t("results.observedResults.fields.controlN"), key: "control_n", min: "1", step: "1", inputMode: "numeric" },
    { id: "results-treatment-mean", label: t("results.observedResults.fields.treatmentMean"), key: "treatment_mean", step: "any" },
    { id: "results-treatment-std", label: t("results.observedResults.fields.treatmentStdDev"), key: "treatment_std", min: "0.0001", step: "any" },
    { id: "results-treatment-n", label: t("results.observedResults.fields.treatmentN"), key: "treatment_n", min: "1", step: "1", inputMode: "numeric" },
    { id: "results-alpha-continuous", label: t("results.observedResults.fields.alpha"), key: "alpha", min: "0.001", max: "0.1", step: "0.001" }
  ] as const;

  // The TOST equivalence test reuses the continuous summary fields and adds the equivalence margin
  // (the tolerated mean difference, ±margin).
  const equivalenceFields: FieldConfig<keyof ContinuousResultsForm>[] = [
    ...continuousFields,
    { id: "results-equivalence-margin", label: t("results.observedResults.fields.equivalenceMargin"), key: "equivalence_margin", min: "0.0001", step: "any" }
  ];

  const countFields: FieldConfig<keyof CountResultsForm>[] = [
    { id: "results-control-events", label: t("results.observedResults.fields.controlEvents"), key: "control_events", min: "0", step: "1", inputMode: "numeric" },
    { id: "results-control-exposure", label: t("results.observedResults.fields.controlExposure"), key: "control_exposure", min: "0.0001", step: "any" },
    { id: "results-treatment-events", label: t("results.observedResults.fields.treatmentEvents"), key: "treatment_events", min: "0", step: "1", inputMode: "numeric" },
    { id: "results-treatment-exposure", label: t("results.observedResults.fields.treatmentExposure"), key: "treatment_exposure", min: "0.0001", step: "any" },
    { id: "results-alpha-count", label: t("results.observedResults.fields.alpha"), key: "alpha", min: "0.001", max: "0.1", step: "0.001" }
  ] as const;

  function renderFieldInputs<Key extends keyof BinaryResultsForm | keyof ContinuousResultsForm | keyof CountResultsForm>(
    formKey: "binary" | "continuous" | "count",
    fieldConfig: FieldConfig<Key>[],
    fieldState: Record<Key, string>
  ) {
    return fieldConfig.map((field) => (
      <div key={field.id} className="field">
        <label htmlFor={field.id}>{field.label}</label>
        <input
          id={field.id}
          type="number"
          min={field.min}
          max={field.max}
          step={field.step}
          inputMode={field.inputMode}
          value={fieldState[field.key]}
          onChange={(event) =>
            setActualResults((current) => ({
              ...current,
              [formKey]: { ...current[formKey], [field.key]: event.target.value }
            }))
          }
        />
      </div>
    ));
  }

  function updateRanked(key: keyof ActualResultsState["ranked"], value: string) {
    setActualResults((current) => ({ ...current, ranked: { ...current.ranked, [key]: value } }));
  }

  // Ratio plans are analyzed post-hoc in the dedicated "Ratio metric" section (raw per-user pairs,
  // delta method); this form's toggle offers only the two conscious approximations, continuous and
  // count, and the disclaimer points at that section.
  const isRatioBase = baseMetricType === "ratio";
  // The toggle buttons, the hint and the input form are all derived from the test registry
  // (observedResultsShared): the button list is the base plan's default plus its alternatives, in
  // display order, and the hint tracks the current selection.
  const testButtons = observedTestButtons(baseMetricType);
  const testTypeHint = t(observedTestHintKey(baseMetricType, observedTest));
  const formKind = observedFormKind(analysisMetricType);

  return (
    <div className="card">
      <h3>{t("results.observedResults.title")}</h3>
      <p className="muted">{t("results.observedResults.description")}</p>
      {selectedHistoryRun ? <div className="callout"><Icon name="info" className="icon icon-inline" /><span>{t("results.observedResults.historicalReadOnly")}</span></div> : null}
      {!canUseCompute ? <div className="callout"><Icon name="info" className="icon icon-inline" /><span>{backendMutationMessage}</span></div> : null}
      {isRatioBase ? <div className="callout"><Icon name="info" className="icon icon-inline" /><span>{t("results.observedResults.ratioDisclaimer")}</span></div> : null}
      {showTestToggle ? (
        <div className="field" style={{ marginTop: "var(--space-4)" }}>
          <span>{t("results.observedResults.testType.label")}</span>
          <div className="actions" role="group" aria-label={t("results.observedResults.testType.label")} style={{ flexWrap: "wrap", marginTop: "var(--space-2)" }}>
            {testButtons.map((button) => (
              <button
                key={button.test}
                type="button"
                className={observedTest === button.test ? "btn secondary" : "btn ghost"}
                aria-pressed={observedTest === button.test}
                onClick={() => onSelectTest(button.test)}
              >
                {t(button.labelKey)}
              </button>
            ))}
          </div>
          <p className="muted" style={{ marginTop: "var(--space-2)" }}>{testTypeHint}</p>
          {isRatioBase ? null : (
            <Suspense fallback={null}>
              <TestChooser baseMetricType={baseMetricType} onSelectTest={onSelectTest} />
            </Suspense>
          )}
        </div>
      ) : null}
      {formKind === "ranked" ? (
        <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
          <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
            <div className="field">
              <label htmlFor="results-mw-control">{t("results.observedResults.fields.controlValues")}</label>
              <textarea id="results-mw-control" rows={6} value={actualResults.ranked.control_values} placeholder={t("results.observedResults.fields.rawValuesPlaceholder")} onChange={(event) => updateRanked("control_values", event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="results-mw-treatment">{t("results.observedResults.fields.treatmentValues")}</label>
              <textarea id="results-mw-treatment" rows={6} value={actualResults.ranked.treatment_values} placeholder={t("results.observedResults.fields.rawValuesPlaceholder")} onChange={(event) => updateRanked("treatment_values", event.target.value)} />
            </div>
          </div>
          <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
            <div className="field" style={{ maxWidth: "200px" }}>
              <label htmlFor="results-alpha-ranked">{t("results.observedResults.fields.alpha")}</label>
              <input id="results-alpha-ranked" type="number" min="0.001" max="0.1" step="0.001" value={actualResults.ranked.alpha} onChange={(event) => updateRanked("alpha", event.target.value)} />
            </div>
            {analysisMetricType === "quantile" ? (
              <div className="field" style={{ maxWidth: "200px" }}>
                <label htmlFor="results-quantile-ranked">{t("results.observedResults.fields.quantile")}</label>
                <input id="results-quantile-ranked" type="number" min="0.01" max="0.99" step="0.01" value={actualResults.ranked.quantile} onChange={(event) => updateRanked("quantile", event.target.value)} />
              </div>
            ) : null}
            {analysisMetricType === "trimmed_t" ? (
              <div className="field" style={{ maxWidth: "200px" }}>
                <label htmlFor="results-trim-ranked">{t("results.observedResults.fields.trim")}</label>
                <input id="results-trim-ranked" type="number" min="0" max="0.49" step="0.05" value={actualResults.ranked.trim} onChange={(event) => updateRanked("trim", event.target.value)} />
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", marginTop: "var(--space-4)" }}>
          {formKind === "binary"
            ? renderFieldInputs("binary", binaryFields, actualResults.binary)
            : formKind === "count"
              ? renderFieldInputs("count", countFields, actualResults.count)
              : formKind === "equivalence"
                ? renderFieldInputs("continuous", equivalenceFields, actualResults.continuous)
                : renderFieldInputs("continuous", continuousFields, actualResults.continuous)}
        </div>
      )}
      <div className="actions" style={{ marginTop: "var(--space-4)", flexWrap: "wrap" }}>
        <button className="btn secondary" type="button" onClick={onRunAnalysis} disabled={!canUseCompute || resultsLoading}>{resultsLoading ? t("results.observedResults.analyzing") : t("results.observedResults.analyzeButton")}</button>
        {isReadOnlySession ? null : (
          <button className="btn ghost" type="button" onClick={onSave} disabled={!canMutateBackend || !canSaveObservedResults || !resultsAnalysis || resultsSaving}>{resultsSaving ? t("results.observedResults.saving") : t("results.observedResults.saveButton")}</button>
        )}
      </div>
      {!isReadOnlySession && !activeProject && !selectedHistoryRun ? <p className="muted" style={{ marginTop: "var(--space-3)" }}>{t("results.observedResults.saveProjectFirst")}</p> : null}
      {resultsError ? <div className="error">{resultsError}</div> : null}
      {resultsSaveMessage ? <div className="status">{resultsSaveMessage}</div> : null}
      {resultsAnalysis ? (
        <div style={{ display: "grid", gap: "var(--space-4)", marginTop: "var(--space-4)" }}>
          <div className="callout" style={{ borderColor: resultsAnalysis.is_significant ? "var(--color-success)" : "var(--color-warning)", background: resultsAnalysis.is_significant ? "var(--color-success-light)" : "var(--color-warning-light)" }}>
            <Icon name={resultsAnalysis.is_significant ? "check" : "info"} className="icon icon-inline" />
            <div style={{ display: "grid", gap: "6px" }}><strong>{resultsAnalysis.verdict}</strong><span>{resultsAnalysis.interpretation}</span></div>
          </div>
          <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
            <div className="card"><strong>{t("results.observedResults.cards.effect")}</strong><div style={{ marginTop: "8px" }}>{formatObservedValue(resultsAnalysis.observed_effect, analysisMetricType, { signed: true, withUnit: true })}</div></div>
            <div className="card"><strong>{t("results.observedResults.cards.ciLabel", { percent: Math.round(resultsAnalysis.ci_level * 100) })}</strong><div style={{ marginTop: "8px" }}>[{formatObservedValue(resultsAnalysis.ci_lower, analysisMetricType, { withUnit: true })}, {formatObservedValue(resultsAnalysis.ci_upper, analysisMetricType, { withUnit: true })}]</div></div>
            <div className="card"><strong>{t("results.observedResults.cards.pValue")}</strong><div style={{ marginTop: "8px" }}>{resultsAnalysis.p_value.toFixed(6)}</div></div>
            <div className="card"><strong>{t("results.observedResults.cards.testStatistic")}</strong><div style={{ marginTop: "8px" }}>{resultsAnalysis.test_statistic.toFixed(4)}</div></div>
            <div className="card"><strong>{t("results.observedResults.cards.relativeChange")}</strong><div style={{ marginTop: "8px" }}>{resultsAnalysis.observed_effect_relative.toFixed(2)}%</div></div>
            <div className="card"><strong>{t("results.observedResults.cards.powerAchieved")}</strong><div style={{ marginTop: "8px" }}>{resultsAnalysis.power_achieved.toFixed(3)}</div></div>
            {resultsAnalysis.effect_size != null ? (
              <div className="card"><strong>{resultsAnalysis.effect_size_label ?? t("results.observedResults.cards.effectSize")}</strong><div style={{ marginTop: "8px" }}>{resultsAnalysis.effect_size.toFixed(4)}</div>{resultsAnalysis.effect_size_ci_lower != null ? (<div style={{ marginTop: "4px", fontSize: "0.85em", opacity: 0.75 }}>{t("results.observedResults.cards.ciLabel", { percent: Math.round(resultsAnalysis.ci_level * 100) })}: [{resultsAnalysis.effect_size_ci_lower.toFixed(4)}, {resultsAnalysis.effect_size_ci_upper != null ? resultsAnalysis.effect_size_ci_upper.toFixed(4) : "∞"}]</div>) : null}</div>
            ) : null}
          </div>
          <div className="two-col">
            <div className="card"><h3>{t("results.observedResults.cards.forestPlot")}</h3><ChartErrorBoundary data={resultsAnalysis}><ForestPlot effect={resultsAnalysis.observed_effect} ciLower={resultsAnalysis.ci_lower} ciUpper={resultsAnalysis.ci_upper} metricType={formKind === "binary" ? "binary" : "continuous"} /></ChartErrorBoundary></div>
            <div className="card"><h3>{t("results.observedResults.cards.observedSummary")}</h3><ul className="list">{formKind === "binary" ? <><li>{t("results.observedResults.cards.controlRate")}: {resultsAnalysis.control_rate?.toFixed(4) ?? "-"}%</li><li>{t("results.observedResults.cards.treatmentRate")}: {resultsAnalysis.treatment_rate?.toFixed(4) ?? "-"}%</li></> : null}<li>{t("results.observedResults.cards.significant")}: {resultsAnalysis.is_significant ? t("results.observedResults.yes") : t("results.observedResults.no")}</li><li>{t("results.observedResults.cards.verdict")}: {resultsAnalysis.verdict}</li></ul></div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
