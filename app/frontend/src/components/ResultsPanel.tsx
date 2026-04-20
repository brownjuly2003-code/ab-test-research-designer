import { useEffect, useState } from "react";

import type { ExportFormat, ResultsAnalysisResponse } from "../lib/experiment";
import { apiUrl, buildApiPayload } from "../lib/experiment";
import { useAnalysisStore } from "../stores/analysisStore";
import { readDraftBootstrap } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import Accordion from "./Accordion";
import ResultsSkeleton from "./ResultsSkeleton";
import styles from "./ResultsPanel.module.css";
import AiAdviceSection from "./results/AiAdviceSection";
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
  const analysis = useAnalysisStore();
  const project = useProjectStore();
  const displayedAnalysis = project.selectedHistoryRun?.analysis ?? analysis.analysisResult;
  const warnings = displayedAnalysis?.calculations.warnings ?? [];
  const warningBadgeColor = warnings.some((item) => item.severity === "high") ? "danger" : warnings.some((item) => item.severity === "medium") ? "warn" : "accent";
  const [sensitivityData, setSensitivityData] = useState<SensitivityResponse | null>(null);
  const [sensitivityLoading, setSensitivityLoading] = useState(false);
  const [sensitivityError, setSensitivityError] = useState("");
  const [resultsAnalysis, setResultsAnalysis] = useState<ResultsAnalysisResponse | null>(null);
  const [standaloneExporting, setStandaloneExporting] = useState(false);
  const [standaloneExportError, setStandaloneExportError] = useState("");

  useEffect(() => {
    if (!displayedAnalysis?.report || project.selectedHistoryRun) {
      setSensitivityData(null);
      setSensitivityLoading(false);
      setSensitivityError(displayedAnalysis?.report && project.selectedHistoryRun ? "Sensitivity analysis is unavailable for historical snapshots." : "");
      return;
    }
    const payload = buildSensitivityPayload(displayedAnalysis);
    if (!payload) {
      setSensitivityData(null);
      setSensitivityLoading(false);
      setSensitivityError("Sensitivity analysis is unavailable for the current draft.");
      return;
    }
    const controller = new AbortController();
    setSensitivityData(null);
    setSensitivityLoading(true);
    setSensitivityError("");
    fetchSensitivityData(payload, controller.signal).then(setSensitivityData).catch((error) => {
      if (!isAbortError(error)) setSensitivityError(error instanceof Error ? error.message : "Sensitivity analysis unavailable.");
    }).finally(() => {
      if (!controller.signal.aborted) setSensitivityLoading(false);
    });
    return () => controller.abort();
  }, [displayedAnalysis, project.selectedHistoryRun]);

  async function handleExportReport(format: "markdown" | "html") {
    if (!project.canMutateBackend) return analysis.showError(project.backendMutationMessage || "Backend is running in read-only mode.", "warning");
    if (!displayedAnalysis?.report) return analysis.showError("Run analysis before exporting a report.", "info");
    analysis.clearFeedback();
    const exportProjectId = project.selectedHistoryRun?.project_id ?? analysis.resultsProjectId;
    const linkedRunId = project.selectedHistoryRun?.id ?? analysis.resultsAnalysisRunId ?? (project.activeProjectId === exportProjectId ? project.activeProject?.last_analysis_run_id ?? null : null);
    const message = await project.exportReport(displayedAnalysis.report, format, exportProjectId, linkedRunId);
    if (message) analysis.showStatus(message, "success");
  }

  async function handleExportStandalone() {
    if (!displayedAnalysis?.report) return setStandaloneExportError("Run analysis before exporting the full report.");
    setStandaloneExporting(true);
    setStandaloneExportError("");
    try {
      const persistedDraft = buildApiPayload(readDraftBootstrap().form);
      const response = await fetch(apiUrl("/api/v1/export/html-standalone"), { method: "POST", headers: buildApiRequestHeaders(), body: JSON.stringify({ project_name: project.activeProject?.project_name || persistedDraft.project.project_name || "AB Test Research Designer", hypothesis: project.selectedHistoryRun ? null : persistedDraft.hypothesis.hypothesis_statement || persistedDraft.hypothesis.change_description || null, calculation: displayedAnalysis.calculations, design: displayedAnalysis.report.experiment_design, ai_advice: displayedAnalysis.advice, sensitivity: sensitivityData, results: resultsAnalysis }) });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Full report export failed.");
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
      setStandaloneExportError(error instanceof Error ? error.message : "Full report export failed.");
    } finally {
      setStandaloneExporting(false);
    }
  }

  return (
    <>
      {project.selectedHistoryRun ? <div className={`${styles["result-block"]} ${styles["results-enter"]}`}><span className="pill">Saved snapshot</span><h3>Viewing historical analysis</h3><p className="muted">Opened snapshot from {new Date(project.selectedHistoryRun.created_at).toLocaleString()}.{analysis.results.report ? " Current in-memory results are still available." : ""}</p><div className="actions"><button className="btn ghost" onClick={() => { if (project.clearHistoryRunSelection()) { analysis.clearFeedback(); analysis.showStatus(analysis.results.report ? "Returned to the current in-memory analysis results." : "Closed the saved snapshot preview.", "info"); } }}>{analysis.results.report ? "Show current analysis" : "Close snapshot view"}</button></div></div> : null}
      {analysis.isAnalyzing && !project.projectComparison ? <div className={`${styles["result-block"]} ${styles["results-enter"]}`}><span className="pill">Analysis in progress</span><h3>Preparing deterministic results</h3><p className="muted">Updating metrics, chart, and report sections.</p><ResultsSkeleton /></div> : null}
      {displayedAnalysis?.report && !analysis.isAnalyzing ? <div className={`${styles.results} ${styles["results-enter"]}`}>
        <Accordion title="Comparison" badge={project.projectComparison ? "Loaded" : "Sidebar"} defaultOpen={Boolean(project.projectComparison)}><ComparisonSection /></Accordion>
        <Accordion title="Sensitivity" badge={`${displayedAnalysis.report.experiment_design?.variants.length ?? 0} variants`} defaultOpen><SensitivitySection sensitivityData={sensitivityData} sensitivityLoading={sensitivityLoading} sensitivityUnavailableMessage={sensitivityError || "Sensitivity analysis unavailable for this configuration."} standaloneExporting={standaloneExporting} standaloneExportError={standaloneExportError} onExportReport={handleExportReport} onExportStandalone={() => void handleExportStandalone()} /></Accordion>
        <Accordion title="Power curve" badge={sensitivityData?.cells?.length ? `${sensitivityData.cells.length} cells` : "Pending"}><PowerCurveSection sensitivityData={sensitivityData} sensitivityLoading={sensitivityLoading} sensitivityUnavailableMessage={sensitivityError || "Sensitivity analysis unavailable for this configuration."} /></Accordion>
        <Accordion title="Observed results" badge={resultsAnalysis ? (resultsAnalysis.is_significant ? "Significant" : "Review") : "Post-test"} badgeColor={resultsAnalysis ? (resultsAnalysis.is_significant ? "accent" : "warn") : "accent"} defaultOpen><ObservedResultsSection onResultsAnalysisChange={setResultsAnalysis} /></Accordion>
        <Accordion title="Sequential design" badge={`${displayedAnalysis.calculations.sequential_boundaries?.length ?? 0} looks`}><SequentialDesignSection /></Accordion>
        <Accordion title="Warnings & Risks" badge={`${warnings.length} warnings`} badgeColor={warningBadgeColor} defaultOpen={warnings.length > 0}><WarningsSection /></Accordion>
        <Accordion title="Experiment design" badge={`${displayedAnalysis.report.experiment_design?.variants.length ?? 0} variants`}><ExperimentDesignSection /></Accordion>
        <Accordion title="Metrics plan" badge={`${(displayedAnalysis.report.metrics_plan?.primary?.length ?? 0) + (displayedAnalysis.report.metrics_plan?.secondary?.length ?? 0) + (displayedAnalysis.report.metrics_plan?.guardrail?.length ?? 0) + (displayedAnalysis.report.metrics_plan?.diagnostic?.length ?? 0)} metrics`}><MetricsPlanSection /></Accordion>
        <Accordion title="Risk assessment" badge={`${(displayedAnalysis.report.risks?.statistical?.length ?? 0) + (displayedAnalysis.report.risks?.product?.length ?? 0) + (displayedAnalysis.report.risks?.technical?.length ?? 0) + (displayedAnalysis.report.risks?.operational?.length ?? 0)} items`}><RisksSection /></Accordion>
        <Accordion title="AI recommendations" badge={displayedAnalysis.advice.available ? "Available" : "Offline"}><AiAdviceSection /></Accordion>
        <Accordion title="SRM check" badge="Manual"><SrmCheckSection /></Accordion>
      </div> : null}
      {!displayedAnalysis?.report && !analysis.isAnalyzing && !project.projectComparison ? <div className="status">No analysis yet. Complete the wizard and run the deterministic backend flow first.</div> : null}
      {analysis.statusMessage ? <div className="status">{analysis.statusMessage}</div> : null}
      {(analysis.analysisError || project.projectError) ? <div className="error">{analysis.analysisError || project.projectError}</div> : null}
    </>
  );
}
