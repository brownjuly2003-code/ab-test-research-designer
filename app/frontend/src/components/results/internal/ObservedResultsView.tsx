import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import type { ResultsAnalysisResponse, SavedProject } from "../../../lib/experiment";
import type { ProjectAnalysisRun } from "../../../lib/experiment";
import type { ActualResultsState, BinaryResultsForm, ContinuousResultsForm } from "../observedResultsShared";
import { formatObservedValue } from "../observedResultsShared";
import ChartErrorBoundary from "../../ChartErrorBoundary";
import ForestPlot from "../../ForestPlot";
import Icon from "../../Icon";

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
  analysisMetricType: "binary" | "continuous";
  actualResults: ActualResultsState;
  setActualResults: Dispatch<SetStateAction<ActualResultsState>>;
  canMutateBackend: boolean;
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
  actualResults,
  setActualResults,
  canMutateBackend,
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

  function renderFieldInputs<Key extends keyof BinaryResultsForm | keyof ContinuousResultsForm>(
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
              [analysisMetricType]: { ...current[analysisMetricType], [field.key]: event.target.value }
            }))
          }
        />
      </div>
    ));
  }

  return (
    <div className="card">
      <h3>{t("results.observedResults.title")}</h3>
      <p className="muted">{t("results.observedResults.description")}</p>
      {selectedHistoryRun ? <div className="callout"><Icon name="info" className="icon icon-inline" /><span>{t("results.observedResults.historicalReadOnly")}</span></div> : null}
      {!canMutateBackend ? <div className="callout"><Icon name="info" className="icon icon-inline" /><span>{backendMutationMessage}</span></div> : null}
      <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", marginTop: "var(--space-4)" }}>
        {analysisMetricType === "binary"
          ? renderFieldInputs(binaryFields, actualResults.binary)
          : renderFieldInputs(continuousFields, actualResults.continuous)}
      </div>
      <div className="actions" style={{ marginTop: "var(--space-4)", flexWrap: "wrap" }}>
        <button className="btn secondary" type="button" onClick={onRunAnalysis} disabled={!canMutateBackend || resultsLoading}>{resultsLoading ? t("results.observedResults.analyzing") : t("results.observedResults.analyzeButton")}</button>
        <button className="btn ghost" type="button" onClick={onSave} disabled={!canMutateBackend || !canSaveObservedResults || !resultsAnalysis || resultsSaving}>{resultsSaving ? t("results.observedResults.saving") : t("results.observedResults.saveButton")}</button>
      </div>
      {!activeProject && !selectedHistoryRun ? <p className="muted" style={{ marginTop: "var(--space-3)" }}>{t("results.observedResults.saveProjectFirst")}</p> : null}
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
          </div>
          <div className="two-col">
            <div className="card"><h3>{t("results.observedResults.cards.forestPlot")}</h3><ChartErrorBoundary data={resultsAnalysis}><ForestPlot effect={resultsAnalysis.observed_effect} ciLower={resultsAnalysis.ci_lower} ciUpper={resultsAnalysis.ci_upper} metricType={analysisMetricType} /></ChartErrorBoundary></div>
            <div className="card"><h3>{t("results.observedResults.cards.observedSummary")}</h3><ul className="list">{analysisMetricType === "binary" ? <><li>{t("results.observedResults.cards.controlRate")}: {resultsAnalysis.control_rate?.toFixed(4) ?? "-"}%</li><li>{t("results.observedResults.cards.treatmentRate")}: {resultsAnalysis.treatment_rate?.toFixed(4) ?? "-"}%</li></> : null}<li>{t("results.observedResults.cards.significant")}: {resultsAnalysis.is_significant ? t("results.observedResults.yes") : t("results.observedResults.no")}</li><li>{t("results.observedResults.cards.verdict")}: {resultsAnalysis.verdict}</li></ul></div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
