import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { ExportFormat, ResultsAnalysisResponse } from "../lib/experiment";
import { apiUrl, buildApiPayload } from "../lib/experiment";
import { formatLocalizedTimestamp } from "../lib/formatDate";
import { useAnalysisStore } from "../stores/analysisStore";
import { readDraftBootstrap, useDraftStore } from "../stores/draftStore";
import { useProjectStore } from "../stores/projectStore";
import Accordion from "./Accordion";
import ResultsSkeleton from "./ResultsSkeleton";
import styles from "./ResultsPanel.module.css";
import AiAdviceSection from "./results/AiAdviceSection";
import AssignmentSection from "./results/AssignmentSection";
import BanditSection from "./results/BanditSection";
import BayesianSection from "./results/BayesianSection";
import ComparisonSection from "./results/ComparisonSection";
import DecisionReadoutSection from "./results/DecisionReadoutSection";
import ExperimentDesignSection from "./results/ExperimentDesignSection";
import LiveStatsSection from "./results/LiveStatsSection";
import MetricsPlanSection from "./results/MetricsPlanSection";
import MultipleTestingSection from "./results/MultipleTestingSection";
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

// The four experiment-lifecycle stages the flat accordion list is grouped into (audit §6.2).
type StageKey = "planning" | "posthoc" | "execution" | "decision";
// Fixed to the lifecycle order (Planning=1 … Decision=4) even when the display order changes,
// so a Decision block surfaced to the top still reads as the final stage, not "step 1".
const STAGE_ORDINAL: Record<StageKey, number> = { planning: 1, posthoc: 2, execution: 3, decision: 4 };

// Code-split the omnibus analyzer into its own async chunk (like ComparisonDashboard / PosteriorPlot)
// so it stays out of the main bundle, keeping index.js under the 500 kB chunkSizeWarningLimit.
const OmnibusResultsSection = lazy(() => import("./results/OmnibusResultsSection"));
// The survival section pulls in recharts for the Kaplan–Meier curve; code-split it into its own async
// chunk for the same reason (keep recharts out of the main bundle).
const SurvivalResultsSection = lazy(() => import("./results/SurvivalResultsSection"));
// The remaining manual post-hoc analyzers are individually light, but the main bundle sits right at
// the 500 kB warning limit (it crossed it when the survival section's accordion landed), so they are
// code-split the same way — they only load when a user actually opens a post-hoc form.
const RatioResultsSection = lazy(() => import("./results/RatioResultsSection"));
const CategoricalResultsSection = lazy(() => import("./results/CategoricalResultsSection"));
const PairedResultsSection = lazy(() => import("./results/PairedResultsSection"));

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
  const [hasLiveData, setHasLiveData] = useState(false);
  const exportProjectId = project.selectedHistoryRun?.project_id ?? analysis.resultsProjectId ?? project.activeProjectId;
  const experimentId = project.selectedHistoryRun?.project_id ?? analysis.resultsProjectId ?? project.activeProjectId ?? null;
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

  // Lightweight probe that only decides the stage order: does this experiment have live
  // execution data? If so we lead with the Decision readout instead of burying it under the
  // planning sections. Sections keep their own on-demand fetch; this is abortable and stays
  // silent on error (an anonymous/unsaved run simply keeps the default planning-first order).
  useEffect(() => {
    if (!displayedAnalysis?.report || !experimentId) {
      setHasLiveData(false);
      return;
    }
    const controller = new AbortController();
    setHasLiveData(false);
    fetch(apiUrl(`/api/v1/experiments/${encodeURIComponent(experimentId)}/live-stats`), {
      method: "GET",
      headers: buildApiRequestHeaders(),
      signal: controller.signal
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (body && typeof body.exposures_total === "number") {
          setHasLiveData(body.exposures_total > 0);
        }
      })
      .catch(() => {
        /* absence of live data just keeps the default planning-first order */
      });
    return () => controller.abort();
  }, [displayedAnalysis, experimentId]);

  async function handleExportReport(format: "markdown" | "html") {
    if (!project.canUseCompute) return analysis.showError(project.backendMutationMessage || t("results.panel.backendReadOnly"), "warning");
    if (!displayedAnalysis?.report) return analysis.showError(t("results.panel.runAnalysisBeforeExportingReport"), "info");
    analysis.clearFeedback();
    const message = await project.exportReport(displayedAnalysis.report, format, exportProjectId, linkedRunId);
    if (message) analysis.showStatus(message, "success");
  }

  async function handleExportPdf() {
    if (!project.canUseCompute) return analysis.showError(project.backendMutationMessage || t("results.panel.backendReadOnly"), "warning");
    if (!displayedAnalysis?.report) return analysis.showError(t("results.panel.runAnalysisBeforeExportingReport"), "info");
    if (!exportProjectId || !linkedRunId) return analysis.showError(t("results.panel.saveProjectBeforePdf"), "info");
    analysis.clearFeedback();
    const message = await project.exportProjectPdf(exportProjectId, linkedRunId);
    if (message) analysis.showStatus(message, "success");
  }

  async function handleExportProjectData(format: "csv" | "xlsx") {
    if (!project.canUseCompute) return analysis.showError(project.backendMutationMessage || t("results.panel.backendReadOnly"), "warning");
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

  const variantCount = displayedAnalysis?.report?.experiment_design?.variants.length ?? 0;
  const metricsPlan = displayedAnalysis?.report?.metrics_plan;
  const metricsCount =
    (metricsPlan?.primary?.length ?? 0) +
    (metricsPlan?.secondary?.length ?? 0) +
    (metricsPlan?.guardrail?.length ?? 0) +
    (metricsPlan?.diagnostic?.length ?? 0);
  const risks = displayedAnalysis?.report?.risks;
  const riskItemsCount =
    (risks?.statistical?.length ?? 0) +
    (risks?.product?.length ?? 0) +
    (risks?.technical?.length ?? 0) +
    (risks?.operational?.length ?? 0);

  // With live execution data, lead with the Decision readout; otherwise follow the planning-first
  // lifecycle. The stage instances are reused across reorders (stable keys), so the Decision
  // accordion is re-keyed on hasLiveData to actually open when live data first arrives.
  const stageOrder: StageKey[] = hasLiveData
    ? ["decision", "execution", "planning", "posthoc"]
    : ["planning", "posthoc", "execution", "decision"];

  const stageContent: Record<StageKey, ReactNode> = {
    planning: (
      <>
        <Accordion title={t("results.panel.accordion.experimentDesign")} badge={t("results.panel.variantsCount", { count: variantCount })}><ExperimentDesignSection /></Accordion>
        <Accordion title={t("results.panel.accordion.metricsPlan")} badge={t("results.panel.metricsCount", { count: metricsCount })}><MetricsPlanSection /></Accordion>
        <Accordion title={t("results.panel.accordion.sensitivity")} badge={t("results.panel.variantsCount", { count: variantCount })} defaultOpen><SensitivitySection sensitivityData={sensitivityData} sensitivityLoading={sensitivityLoading} sensitivityUnavailableMessage={sensitivityError || t("results.panel.sensitivityUnavailableForConfiguration")} standaloneExporting={standaloneExporting} standaloneExportError={standaloneExportError} canExportPdf={canExportPdf} onExportReport={handleExportReport} onExportPdf={() => void handleExportPdf()} onExportProjectData={(format) => void handleExportProjectData(format)} onExportStandalone={() => void handleExportStandalone()} /></Accordion>
        <Accordion title={t("results.panel.accordion.powerCurve")} badge={sensitivityData?.cells?.length ? t("results.panel.cellsCount", { count: sensitivityData.cells.length }) : t("results.panel.badges.pending")}><PowerCurveSection sensitivityData={sensitivityData} sensitivityLoading={sensitivityLoading} sensitivityUnavailableMessage={sensitivityError || t("results.panel.sensitivityUnavailableForConfiguration")} /></Accordion>
        <Accordion title={t("results.panel.accordion.sequentialDesign")} badge={t("results.panel.looksCount", { count: displayedAnalysis?.calculations.sequential_boundaries?.length ?? 0 })}><SequentialDesignSection /></Accordion>
        {showBayesianPosterior ? <Accordion title={t("results.panel.accordion.bayesianPosterior")} badge={displayedAnalysis?.calculations.bayesian_credibility != null ? t("results.panel.credibilityInterval", { percent: Math.round(displayedAnalysis.calculations.bayesian_credibility * 100) }) : t("results.panel.badges.planning")}><BayesianSection /></Accordion> : null}
        <Accordion title={t("results.panel.accordion.bandit")} badge={t("results.panel.badges.planning")}><BanditSection /></Accordion>
        <Accordion title={t("results.panel.accordion.riskAssessment")} badge={t("results.panel.itemsCount", { count: riskItemsCount })}><RisksSection /></Accordion>
        <Accordion title={t("results.panel.accordion.warningsAndRisks")} badge={t("results.panel.warningsCount", { count: warnings.length })} badgeColor={warningBadgeColor} defaultOpen={warnings.length > 0}><WarningsSection /></Accordion>
      </>
    ),
    posthoc: (
      <>
        <Accordion title={t("results.panel.accordion.observedResults")} badge={resultsAnalysis ? (resultsAnalysis.is_significant ? t("results.panel.badges.significant") : t("results.panel.badges.review")) : t("results.panel.badges.postTest")} badgeColor={resultsAnalysis ? (resultsAnalysis.is_significant ? "accent" : "warn") : "accent"} defaultOpen><ObservedResultsSection onResultsAnalysisChange={setResultsAnalysis} /></Accordion>
        <Accordion title={t("results.panel.accordion.ratioResults")} badge={t("results.panel.badges.manual")}><Suspense fallback={<div className="status" aria-busy={true} />}><RatioResultsSection onResultsAnalysisChange={setResultsAnalysis} /></Suspense></Accordion>
        <Accordion title={t("results.panel.accordion.categoricalResults")} badge={t("results.panel.badges.manual")}><Suspense fallback={<div className="status" aria-busy={true} />}><CategoricalResultsSection /></Suspense></Accordion>
        <Accordion title={t("results.panel.accordion.pairedResults")} badge={t("results.panel.badges.manual")}><Suspense fallback={<div className="status" aria-busy={true} />}><PairedResultsSection /></Suspense></Accordion>
        <Accordion title={t("results.panel.accordion.omnibusResults")} badge={t("results.panel.badges.manual")}><Suspense fallback={<div className="status" aria-busy={true} />}><OmnibusResultsSection /></Suspense></Accordion>
        <Accordion title={t("results.panel.accordion.survivalResults")} badge={t("results.panel.badges.manual")}><Suspense fallback={<div className="status" aria-busy={true} />}><SurvivalResultsSection /></Suspense></Accordion>
        <Accordion title={t("results.panel.accordion.srmCheck")} badge={t("results.panel.badges.manual")}><SrmCheckSection /></Accordion>
        <Accordion title={t("results.panel.accordion.multipleTesting")} badge={t("results.panel.badges.manual")}><MultipleTestingSection /></Accordion>
      </>
    ),
    execution: (
      <>
        <Accordion title={t("results.panel.accordion.assignment")} badge={t("results.panel.badges.execution")}><AssignmentSection /></Accordion>
        <Accordion title={t("results.panel.accordion.liveStats")} badge={t("results.panel.badges.execution")}><LiveStatsSection /></Accordion>
      </>
    ),
    decision: (
      <>
        <Accordion key={`decision-${hasLiveData}`} title={t("results.panel.accordion.decision")} badge={t("results.panel.badges.execution")} defaultOpen={hasLiveData}><DecisionReadoutSection /></Accordion>
        <Accordion title={t("results.panel.accordion.aiRecommendations")} badge={displayedAnalysis?.advice.available ? t("results.panel.badges.available") : t("results.panel.badges.offline")}><AiAdviceSection /></Accordion>
      </>
    )
  };

  return (
    <>
      {project.selectedHistoryRun ? <div className={`${styles["result-block"]} ${styles["results-enter"]}`}><span className="pill">{t("results.panel.savedSnapshot")}</span><h3>{t("results.panel.viewingHistoricalAnalysis")}</h3><p className="muted">{t("results.panel.openedSnapshotFrom", { timestamp: formatLocalizedTimestamp(project.selectedHistoryRun.created_at) })}{analysis.results.report ? ` ${t("results.panel.currentResultsAvailable")}` : ""}</p><div className="actions"><button className="btn ghost" onClick={() => { if (project.clearHistoryRunSelection()) { analysis.clearFeedback(); analysis.showStatus(analysis.results.report ? t("results.panel.returnedToCurrentAnalysis") : t("results.panel.closedSnapshotPreview"), "info"); } }}>{analysis.results.report ? t("results.panel.showCurrentAnalysis") : t("results.panel.closeSnapshotView")}</button></div></div> : null}
      {analysis.isAnalyzing && !project.projectComparison && !project.projectMultiComparison ? <div className={`${styles["result-block"]} ${styles["results-enter"]}`}><span className="pill">{t("results.panel.analysisInProgress")}</span><h3>{t("results.panel.preparingDeterministicResults")}</h3><p className="muted">{t("results.panel.updatingSections")}</p><ResultsSkeleton /></div> : null}
      {displayedAnalysis?.report && !analysis.isAnalyzing ? <div className={`${styles.results} ${styles["results-enter"]}`}>
        <Accordion title={t("results.panel.accordion.comparison")} badge={project.projectComparison || project.projectMultiComparison ? t("results.panel.badges.loaded") : t("results.panel.badges.sidebar")} defaultOpen={Boolean(project.projectComparison || project.projectMultiComparison)}><ComparisonSection /></Accordion>
        <nav className={styles.toc} aria-label={t("results.panel.stages.tocLabel")}>
          <span className={styles["toc-heading"]}>{t("results.panel.stages.tocHeading")}</span>
          {stageOrder.map((key) => (
            <a key={key} className={styles["toc-link"]} href={`#stage-${key}`}>{t(`results.panel.stages.${key}.title`)}</a>
          ))}
        </nav>
        {stageOrder.map((key) => (
          <section key={key} id={`stage-${key}`} data-stage={key} className={styles.stage} aria-labelledby={`stage-${key}-heading`}>
            <header className={styles["stage-header"]}>
              <span className={styles["stage-index"]} aria-hidden="true">{STAGE_ORDINAL[key]}</span>
              <span className={styles["stage-heading-group"]}>
                <h3 id={`stage-${key}-heading`} className={styles["stage-title"]}>{t(`results.panel.stages.${key}.title`)}</h3>
                <span className={styles["stage-caption"]}>{t(`results.panel.stages.${key}.caption`)}</span>
              </span>
            </header>
            <div className={styles["stage-body"]}>{stageContent[key]}</div>
          </section>
        ))}
      </div> : null}
      {!displayedAnalysis?.report && !analysis.isAnalyzing && !project.projectComparison && !project.projectMultiComparison ? <div className="status">{t("results.panel.noAnalysisYet")}</div> : null}
      {analysis.statusMessage ? <div className="status">{analysis.statusMessage}</div> : null}
      {(analysis.analysisError || project.projectError) ? <div className="error">{analysis.analysisError || project.projectError}</div> : null}
    </>
  );
}
