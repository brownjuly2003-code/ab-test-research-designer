import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ResultsAnalysisResponse, ResultsRequestPayload } from "../../lib/experiment";
import { apiUrl, buildApiPayload } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { readDraftBootstrap } from "../../stores/draftStore";
import { useProjectStore } from "../../stores/projectStore";
import ObservedResultsView from "./internal/ObservedResultsView";
import { type ActualResultsState, buildActualResultsState, buildResultsRequest, resolveObservedMetricType } from "./observedResultsShared";
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
  const backendMutationMessage = useProjectStore((state) => state.backendMutationMessage);
  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryRun?.analysis ?? null, analysisResult);
  const analysisMetricType = displayedAnalysis ? resolveObservedMetricType(displayedAnalysis.calculations.calculation_summary.metric_type) : "binary";
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
    const persistedRequest = persistedObservedResults?.request?.metric_type === analysisMetricType ? persistedObservedResults.request : null;
    const persistedAnalysis = persistedObservedResults?.analysis?.metric_type === analysisMetricType ? persistedObservedResults.analysis : null;
    setActualResults(buildActualResultsState(analysisMetricType, displayedAnalysis.calculations.calculation_summary.alpha, persistedRequest));
    setResultsRequest(persistedRequest);
    setResultsAnalysis(persistedAnalysis);
    setResultsLoading(false);
    setResultsSaving(false);
    setResultsError("");
    setResultsSaveMessage("");
  }, [analysisMetricType, displayedAnalysis, selectedHistoryRun?.id]);

  useEffect(() => {
    onResultsAnalysisChange(resultsAnalysis);
  }, [onResultsAnalysisChange, resultsAnalysis]);

  async function runObservedResultsAnalysis() {
    const payload = buildResultsRequest(analysisMetricType, actualResults);
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
      analysisMetricType={analysisMetricType}
      actualResults={actualResults}
      setActualResults={setActualResults}
      canMutateBackend={canMutateBackend}
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
