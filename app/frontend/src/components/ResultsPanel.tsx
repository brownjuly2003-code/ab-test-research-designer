import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { ExportFormat, ResultsAnalysisResponse } from "../lib/experiment";
import { apiUrl, buildApiPayload } from "../lib/experiment";
import { useAnalysisStore } from "../stores/analysisStore";
import { readDraftBootstrap, useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import Accordion from "./Accordion";
import ResultsSkeleton from "./ResultsSkeleton";
import styles from "./ResultsPanel.module.css";
import AiAdviceSection from "./results/AiAdviceSection";
import BayesianSection from "./results/BayesianSection";
import ComparisonSection from "./results/ComparisonSection";
import ExperimentDesignSection from "./results/ExperimentDesignSection";
import MetricsPlanSection from "./results/MetricsPlanSection";
import ObservedResultsSection from "./results/ObservedResultsSection";
import PowerCurveSection from "./results/PowerCurveSection";
import RisksSection from "./results/RisksSection";
import SensitivitySection from "./results/SensitivitySection";
import SequentialDesignSection from "./results/SequentialDesignSection";
import SrmCheckSection from "./results/SrmCheckSection";
import WarningsSection from "./results/WarningsSection";
import type { SensitivityResponse } from "../lib/generated/api-contract";
import { buildApiRequestHeaders } from "./results/resultsShared";
import { buildSensitivityPayload, fetchSensitivityData, isAbortError } from "./results/sensitivityShared";

type ResultsPanelProps = { onExportReport?: (format: ExportFormat) => void; readonly [key: string]: unknown };

export default function ResultsPanel(_props: ResultsPanelProps) {
  const { t } = useTranslation();
  const analysis = useAnalysisStore();
  const project = useProjectStore();
  const analysisMode = useDraftStore((state) => state.draft.constraints.analysis_mode ?? "frequentist");
  const displayedAnalysis = project.selectedHistoryRun?.analysis ?? analysis.analysisResult;
  const warnings = displayedAnalysis?.calculations.warnings ?? [];
  const showBayesianPosterior = Boolean(
    project.selectedHistoryRun
      ? displayedAnalysis?.calculations.bayesian_sample_size_per_variant != null ||
        displayedAnalysis?.calculations.bayesian_credibility != null ||
        displayedAnalysis?.calculations.bayesian_note
      : analysisMode === "bayesian"
  );
  const warningBadgeColor = warnings.some((item) => item.severity === "high") ? "danger" : warnings.some((item) => item.severity === "medium") ? "warn" : "accent";
  const [sensitivityData, setSensitivityData] = useState<SensitivityResponse | null>(null);
  const [sensitivityLoading, setSensitivityLoading] = useState(false);
  const [sensitivityError, setSensitivityError] = useState("");
  const [resultsAnalysis, setResultsAnalysis] = useState<ResultsAnalysisResponse | null>(null);
  const [standaloneExporting, setStandaloneExporting] = useState(false);
  const [standaloneExportError, setStandaloneExportError] = useState("");
  const exportProjectId = project.selectedHistoryRun?.project_id ?? analysis.resultsProjectId ?? project.activeProjectId;
  const linkedRunId =
    project.selectedHistoryRun?.id ??
    analysis.resultsAnalysisRunId ??
    (project.activeProjectId === exportProjectId ? project.activeProject?.last_analysis_run_id ?? null : null);
  const canExportPdf = Boolean(exportProjectId && linkedRunId);

  useEffect(() => {
    if (!displayedAnalysis?.report || project.selectedHistoryRun) {
      setSensitivityData(null);
      setSensitivityLoading(false);
      setSensitivityError(displayedAnalysis?.report && project.selectedHistoryRun ? t("results.panel.sensitivityUnavailableHistorical") : "");
      return;
    }
    const payload = buildSensitivityPayload(displayedAnalysis);
    if (!payload) {
      setSensitivityData(null);
      setSensitivityLoading(false);
      setSensitivityError(t("results.panel.sensitivityUnavailableCurrentDraft"));
      return;
    }
    const controller = new AbortController();
    setSensitivityData(null);
    setSensitivityLoading(true);
    setSensitivityError("");
    fetchSensitivityData(payload, controller.signal).then(setSensitivityData).catch((error) => {
      if (!isAbortError(error)) setSensitivityError(error instanceof Error ? error.message : t("results.panel.sensitivityUnavailable"));
    }).finally(() => {
      if (!controller.signal.aborted) setSensitivityLoading(false);
    });
    return () => controller.abort();
  }, [displayedAnalysis, project.selectedHistoryRun, t]);

  async function handleExportReport(format: "markdown" | "html") {
    if (!project.canMutateBackend) return analysis.showError(project.backendMutationMessage || t("results.panel.backendReadOnly"), "warning");
    if (!displayedAnalysis?.report) return analysis.showError(t("results.panel.runAnalysisBeforeExportingReport"), "info");
    analysis.clearFeedback();
    const message = await project.exportReport(displayedAnalysis.report, format, exportProjectId, linkedRunId);
    if (message) analysis.showStatus(message, "success");
  }

  async function handleExportPdf() {
    if (!project.canMutateBackend) return analysis.showError(project.backendMutationMessage || t("results.panel.backendReadOnly"), "warning");
    if (!displayedAnalysis?.report) return analysis.showError(t("results.panel.runAnalysisBeforeExportingReport"), "info");
    if (!exportProjectId || !linkedRunId) return analysis.showError(t("results.panel.saveProjectBeforePdf"), "info");
    analysis.clearFeedback();
    const message = await project.exportProjectPdf(exportProjectId, linkedRunId);
    if (message) analysis.showStatus(message, "success");
  }

  async function handleExportProjectData(format: "csv" | "xlsx") {
    if (!project.canMutateBackend) return analysis.showError(project.backendMutationMessage || t("results.panel.backendReadOnly"), "warning");
    if (!displayedAnalysis?.report) return analysis.showError(t("results.panel.runAnalysisBeforeExportingProjectData"), "info");
    if (!exportProjectId) return analysis.showError(t("results.panel.saveProjectBeforeProjectData"), "info");
    analysis.clearFeedback();
    const message = await project.exportProjectData(exportProjectId, format);
    if (message) analysis.showStatus(message, "success");
  }

  async function handleExportStandalone() {
    if (!displayedAnalysis?.report) return setStandaloneExportError(t("results.panel.runAnalysisBeforeStandaloneExport"));
    setStandaloneExporting(true);
    setStandaloneExportError("");
    try {
      const persistedDraft = buildApiPayload(readDraftBootstrap().form);
      const response = await fetch(apiUrl("/api/v1/export/html-standalone"), { method: "POST", headers: buildApiRequestHeaders(), body: JSON.stringify({ project_name: project.activeProject?.project_name || persistedDraft.project.project_name || "AB Test Research Designer", hypothesis: project.selectedHistoryRun ? null : persistedDraft.hypothesis.hypothesis_statement || persistedDraft.hypothesis.change_description || null, calculation: displayedAnalysis.calculations, design: displayedAnalysis.report.experiment_design, ai_advice: displayedAnalysis.advice, sensitivity: sensitivityData, results: resultsAnalysis }) });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : t("results.panel.standaloneExportFailed"));
      }
      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const filename = /filename=\"([^\"]+)\"/i.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? "ab-test-report.html";
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch (error) {
      setStandaloneExportError(error instanceof Error ? error.message : t("results.panel.standaloneExportFailed"));
    } finally {
      setStandaloneExporting(false);
    }
  }

  return (
    <>
      {project.selectedHistoryRun ? <div className={`${styles["result-block"]} ${styles["results-enter"]}`}><span className="pill">{t("results.panel.savedSnapshot")}</span><h3>{t("results.panel.viewingHistoricalAnalysis")}</h3><p className="muted">{t("results.panel.openedSnapshotFrom", { timestamp: new Date(project.selectedHistoryRun.created_at).toLocaleString() })}{analysis.results.report ? ` ${t("results.panel.currentResultsAvailable")}` : ""}</p><div className="actions"><button className="btn ghost" onClick={() => { if (project.clearHistoryRunSelection()) { analysis.clearFeedback(); analysis.showStatus(analysis.results.report ? t("results.panel.returnedToCurrentAnalysis") : t("results.panel.closedSnapshotPreview"), "info"); } }}>{analysis.results.report ? t("results.panel.showCurrentAnalysis") : t("results.panel.closeSnapshotView")}</button></div></div> : null}
      {analysis.isAnalyzing && !project.projectComparison && !project.projectMultiComparison ? <div className={`${styles["result-block"]} ${styles["results-enter"]}`}><span className="pill">{t("results.panel.analysisInProgress")}</span><h3>{t("results.panel.preparingDeterministicResults")}</h3><p className="muted">{t("results.panel.updatingSections")}</p><ResultsSkeleton /></div> : null}
      {displayedAnalysis?.report && !analysis.isAnalyzing ? <div className={`${styles.results} ${styles["results-enter"]}`}>
        <Accordion title={t("results.panel.accordion.comparison")} badge={project.projectComparison || project.projectMultiComparison ? t("results.panel.badges.loaded") : t("results.panel.badges.sidebar")} defaultOpen={Boolean(project.projectComparison || project.projectMultiComparison)}><ComparisonSection /></Accordion>
        <Accordion title={t("results.panel.accordion.sensitivity")} badge={t("results.panel.variantsCount", { count: displayedAnalysis.report.experiment_design?.variants.length ?? 0 })} defaultOpen><SensitivitySection sensitivityData={sensitivityData} sensitivityLoading={sensitivityLoading} sensitivityUnavailableMessage={sensitivityError || t("results.panel.sensitivityUnavailableForConfiguration")} standaloneExporting={standaloneExporting} standaloneExportError={standaloneExportError} canExportPdf={canExportPdf} onExportReport={handleExportReport} onExportPdf={() => void handleExportPdf()} onExportProjectData={(format) => void handleExportProjectData(format)} onExportStandalone={() => void handleExportStandalone()} /></Accordion>
        <Accordion title={t("results.panel.accordion.powerCurve")} badge={sensitivityData?.cells?.length ? t("results.panel.cellsCount", { count: sensitivityData.cells.length }) : t("results.panel.badges.pending")}><PowerCurveSection sensitivityData={sensitivityData} sensitivityLoading={sensitivityLoading} sensitivityUnavailableMessage={sensitivityError || t("results.panel.sensitivityUnavailableForConfiguration")} /></Accordion>
        <Accordion title={t("results.panel.accordion.sequentialDesign")} badge={t("results.panel.looksCount", { count: displayedAnalysis.calculations.sequential_boundaries?.length ?? 0 })}><SequentialDesignSection /></Accordion>
        {showBayesianPosterior ? <Accordion title={t("results.panel.accordion.bayesianPosterior")} badge={displayedAnalysis.calculations.bayesian_credibility != null ? t("results.panel.credibilityInterval", { percent: Math.round(displayedAnalysis.calculations.bayesian_credibility * 100) }) : t("results.panel.badges.planning")}><BayesianSection /></Accordion> : null}
        <Accordion title={t("results.panel.accordion.observedResults")} badge={resultsAnalysis ? (resultsAnalysis.is_significant ? t("results.panel.badges.significant") : t("results.panel.badges.review")) : t("results.panel.badges.postTest")} badgeColor={resultsAnalysis ? (resultsAnalysis.is_significant ? "accent" : "warn") : "accent"} defaultOpen><ObservedResultsSection onResultsAnalysisChange={setResultsAnalysis} /></Accordion>
        <Accordion title={t("results.panel.accordion.warningsAndRisks")} badge={t("results.panel.warningsCount", { count: warnings.length })} badgeColor={warningBadgeColor} defaultOpen={warnings.length > 0}><WarningsSection /></Accordion>
        <Accordion title={t("results.panel.accordion.experimentDesign")} badge={t("results.panel.variantsCount", { count: displayedAnalysis.report.experiment_design?.variants.length ?? 0 })}><ExperimentDesignSection /></Accordion>
        <Accordion title={t("results.panel.accordion.metricsPlan")} badge={t("results.panel.metricsCount", { count: (displayedAnalysis.report.metrics_plan?.primary?.length ?? 0) + (displayedAnalysis.report.metrics_plan?.secondary?.length ?? 0) + (displayedAnalysis.report.metrics_plan?.guardrail?.length ?? 0) + (displayedAnalysis.report.metrics_plan?.diagnostic?.length ?? 0) })}><MetricsPlanSection /></Accordion>
        <Accordion title={t("results.panel.accordion.riskAssessment")} badge={t("results.panel.itemsCount", { count: (displayedAnalysis.report.risks?.statistical?.length ?? 0) + (displayedAnalysis.report.risks?.product?.length ?? 0) + (displayedAnalysis.report.risks?.technical?.length ?? 0) + (displayedAnalysis.report.risks?.operational?.length ?? 0) })}><RisksSection /></Accordion>
        <Accordion title={t("results.panel.accordion.aiRecommendations")} badge={displayedAnalysis.advice.available ? t("results.panel.badges.available") : t("results.panel.badges.offline")}><AiAdviceSection /></Accordion>
        <Accordion title={t("results.panel.accordion.srmCheck")} badge={t("results.panel.badges.manual")}><SrmCheckSection /></Accordion>
      </div> : null}
      {!displayedAnalysis?.report && !analysis.isAnalyzing && !project.projectComparison && !project.projectMultiComparison ? <div className="status">{t("results.panel.noAnalysisYet")}</div> : null}
      {analysis.statusMessage ? <div className="status">{analysis.statusMessage}</div> : null}
      {(analysis.analysisError || project.projectError) ? <div className="error">{analysis.analysisError || project.projectError}</div> : null}
    </>
  );
}
