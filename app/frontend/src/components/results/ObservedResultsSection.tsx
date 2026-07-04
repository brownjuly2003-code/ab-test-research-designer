import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ResultsAnalysisResponse, ResultsRequestPayload } from "../../lib/experiment";
import { apiUrl, buildApiPayload } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { readDraftBootstrap } from "../../stores/draftStore";
import { useProjectStore } from "../../stores/projectStore";
import ObservedResultsView from "./internal/ObservedResultsView";
import { type ActualResultsState, type ObservedMetricType, type ObservedTestSelection, buildActualResultsState, buildResultsRequest, resolveObservedMetricType } from "./observedResultsShared";
import { buildApiRequestHeaders, getDisplayedAnalysis } from "./resultsShared";

type ObservedResultsSectionProps = {
  onResultsAnalysisChange: (analysis: ResultsAnalysisResponse | null) => void;
};

export default function ObservedResultsSection({ onResultsAnalysisChange }: ObservedResultsSectionProps) {
  const { t } = useTranslation();
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const selectedHistoryRun = useProjectStore((state) => state.selectedHistoryRun);
  const activeProject = useProjectStore((state) => state.activeProject);
  const canMutateBackend = useProjectStore((state) => state.canMutateBackend);
  const isReadOnlySession = useProjectStore((state) => state.isReadOnlySession);
  const canUseCompute = useProjectStore((state) => state.canUseCompute);
  const backendMutationMessage = useProjectStore((state) => state.backendMutationMessage);
  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryRun?.analysis ?? null, analysisResult);
  const baseMetricType = displayedAnalysis ? resolveObservedMetricType(displayedAnalysis.calculations.calculation_summary.metric_type) : "binary";
  // Each base metric type offers an alternative test on the same data: Mann–Whitney (non-parametric)
  // for continuous, Fisher's exact (exact small-sample) for binary. The selection is local UI state;
  // "parametric" means the default normal-approximation analysis (t-test / z-test).
  const [observedTest, setObservedTest] = useState<ObservedTestSelection>("parametric");
  const effectiveMetricType: ObservedMetricType =
    observedTest === "count"
      ? "count"
      : baseMetricType === "continuous" && observedTest === "mann_whitney"
        ? "mann_whitney"
        : baseMetricType === "continuous" && observedTest === "bootstrap"
          ? "bootstrap"
          : baseMetricType === "continuous" && observedTest === "quantile"
            ? "quantile"
            : baseMetricType === "continuous" && observedTest === "trimmed_t"
              ? "trimmed_t"
              : baseMetricType === "continuous" && observedTest === "equivalence"
                ? "equivalence"
                : baseMetricType === "binary" && observedTest === "fisher_exact"
                  ? "fisher_exact"
                  // Ratio has no dedicated analyzer; "parametric" is the conscious continuous
                  // approximation offered for it (see ObservedResultsView's ratio disclaimer).
                  : baseMetricType === "ratio"
                    ? "continuous"
                    : baseMetricType;
  const canSaveObservedResults = Boolean(activeProject && !activeProject.is_archived && !selectedHistoryRun);
  const [actualResults, setActualResults] = useState<ActualResultsState>(() => buildActualResultsState("binary", 0.05, null));
  const [resultsRequest, setResultsRequest] = useState<ResultsRequestPayload | null>(null);
  const [resultsAnalysis, setResultsAnalysis] = useState<ResultsAnalysisResponse | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsSaving, setResultsSaving] = useState(false);
  const [resultsError, setResultsError] = useState("");
  const [resultsSaveMessage, setResultsSaveMessage] = useState("");

  useEffect(() => {
    if (!displayedAnalysis?.report) {
      setObservedTest("parametric");
      setActualResults(buildActualResultsState("binary", 0.05, null));
      setResultsRequest(null);
      setResultsAnalysis(null);
      setResultsLoading(false);
      setResultsSaving(false);
      setResultsError("");
      setResultsSaveMessage("");
      return;
    }
    const persistedObservedResults = selectedHistoryRun ? null : readDraftBootstrap().form.additional_context.observed_results ?? null;
    const persistedType = persistedObservedResults?.request?.metric_type;
    // The Poisson rate test ("count") is plan-independent, so it is always a supported restore target.
    const supportedTypes: ObservedMetricType[] =
      baseMetricType === "continuous"
        ? ["continuous", "mann_whitney", "bootstrap", "quantile", "trimmed_t", "equivalence", "count"]
        : baseMetricType === "binary"
          ? ["binary", "fisher_exact", "count"]
          // Ratio has no dedicated analyzer: only the two conscious approximations restore.
          : ["continuous", "count"];
    const nextTest: ObservedTestSelection =
      persistedType === "count"
        ? "count"
        : persistedType === "mann_whitney" && baseMetricType === "continuous"
          ? "mann_whitney"
          : persistedType === "bootstrap" && baseMetricType === "continuous"
            ? "bootstrap"
            : persistedType === "quantile" && baseMetricType === "continuous"
              ? "quantile"
              : persistedType === "trimmed_t" && baseMetricType === "continuous"
                ? "trimmed_t"
                : persistedType === "equivalence" && baseMetricType === "continuous"
                  ? "equivalence"
                  : persistedType === "fisher_exact" && baseMetricType === "binary"
                    ? "fisher_exact"
                    : "parametric";
    const stateMetricType: ObservedMetricType =
      nextTest === "mann_whitney"
        ? "mann_whitney"
        : nextTest === "bootstrap"
          ? "bootstrap"
          : nextTest === "quantile"
            ? "quantile"
            : nextTest === "trimmed_t"
              ? "trimmed_t"
              : nextTest === "equivalence"
                ? "equivalence"
                : nextTest === "fisher_exact"
                  ? "fisher_exact"
                  : nextTest === "count"
                    ? "count"
                    : baseMetricType === "ratio"
                      ? "continuous"
                      : baseMetricType;
    const persistedRequest = persistedType && supportedTypes.includes(persistedType) ? persistedObservedResults?.request ?? null : null;
    const persistedAnalysis =
      persistedObservedResults?.analysis && supportedTypes.includes(persistedObservedResults.analysis.metric_type)
        ? persistedObservedResults.analysis
        : null;
    setObservedTest(nextTest);
    setActualResults(buildActualResultsState(stateMetricType, displayedAnalysis.calculations.calculation_summary.alpha, persistedRequest));
    setResultsRequest(persistedRequest);
    setResultsAnalysis(persistedAnalysis);
    setResultsLoading(false);
    setResultsSaving(false);
    setResultsError("");
    setResultsSaveMessage("");
  }, [baseMetricType, displayedAnalysis, selectedHistoryRun?.id]);

  useEffect(() => {
    onResultsAnalysisChange(resultsAnalysis);
  }, [onResultsAnalysisChange, resultsAnalysis]);

  async function runObservedResultsAnalysis() {
    const payload = buildResultsRequest(effectiveMetricType, actualResults);
    if (!payload) {
      setResultsError(t("results.observedResults.validation.fillAllFields"));
      setResultsSaveMessage("");
      return;
    }
    setResultsLoading(true);
    setResultsError("");
    setResultsSaveMessage("");
    try {
      const response = await fetch(apiUrl("/api/v1/results"), { method: "POST", headers: buildApiRequestHeaders(), body: JSON.stringify(payload) });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : t("results.observedResults.validation.analysisUnavailable"));
      setResultsRequest(payload);
      setResultsAnalysis(body);
    } catch (error) {
      setResultsError(error instanceof Error ? error.message : t("results.observedResults.validation.analysisUnavailable"));
    } finally {
      setResultsLoading(false);
    }
  }

  async function saveObservedResults() {
    if (!activeProject || selectedHistoryRun || !resultsRequest || !resultsAnalysis) {
      setResultsError(t("results.observedResults.validation.analyzeBeforeSaving"));
      setResultsSaveMessage("");
      return;
    }
    setResultsSaving(true);
    setResultsError("");
    setResultsSaveMessage("");
    try {
      const persistedDraft = buildApiPayload(readDraftBootstrap().form);
      const response = await fetch(apiUrl(`/api/v1/projects/${activeProject.id}`), {
        method: "PUT",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify({ ...persistedDraft, additional_context: { ...persistedDraft.additional_context, observed_results: { request: resultsRequest, analysis: resultsAnalysis, saved_at: new Date().toISOString() } } })
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : t("results.observedResults.validation.saveUnavailable"));
      setResultsSaveMessage(t("results.observedResults.validation.savedToProject", {
        projectName: typeof body.project_name === "string" && body.project_name.length > 0 ? body.project_name : activeProject.project_name
      }));
    } catch (error) {
      setResultsError(error instanceof Error ? error.message : t("results.observedResults.validation.saveUnavailable"));
    } finally {
      setResultsSaving(false);
    }
  }

  if (!displayedAnalysis?.report) {
    return null;
  }

  return (
    <ObservedResultsView
      analysisMetricType={effectiveMetricType}
      baseMetricType={baseMetricType}
      showTestToggle={baseMetricType === "continuous" || baseMetricType === "binary" || baseMetricType === "ratio"}
      observedTest={observedTest}
      onSelectTest={setObservedTest}
      actualResults={actualResults}
      setActualResults={setActualResults}
      canMutateBackend={canMutateBackend}
      isReadOnlySession={isReadOnlySession}
      canUseCompute={canUseCompute}
      backendMutationMessage={backendMutationMessage}
      activeProject={activeProject}
      selectedHistoryRun={selectedHistoryRun}
      canSaveObservedResults={canSaveObservedResults}
      resultsAnalysis={resultsAnalysis}
      resultsLoading={resultsLoading}
      resultsSaving={resultsSaving}
      resultsError={resultsError}
      resultsSaveMessage={resultsSaveMessage}
      onRunAnalysis={() => void runObservedResultsAnalysis()}
      onSave={() => void saveObservedResults()}
    />
  );
}
