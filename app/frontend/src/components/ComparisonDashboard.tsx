import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import "../i18n";
import { exportComparisonRequest } from "../lib/api";
import type { MultiProjectComparison } from "../lib/experiment";
import ForestPlot from "./ForestPlot";
import PowerCurveChart from "./PowerCurveChart";
import SensitivityTable from "./SensitivityTable";

type ComparisonDashboardProps = {
  comparison: MultiProjectComparison;
  onClose: () => void;
};

function downloadBlob(blob: Blob, filename: string) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(objectUrl);
}

function decodeBase64(base64: string): Uint8Array {
  const binary = window.atob(base64);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function severityColor(severity: string): string {
  if (severity === "high") {
    return "var(--color-danger)";
  }
  if (severity === "medium") {
    return "var(--color-warning)";
  }
  return "var(--color-text-secondary)";
}

export default function ComparisonDashboard({ comparison, onClose }: ComparisonDashboardProps) {
  const { t } = useTranslation();
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const [exportingFormat, setExportingFormat] = useState<"markdown" | "pdf" | null>(null);
  const [exportError, setExportError] = useState("");
  const hasMixedMetricTypes = comparison.metric_types_used.length > 1;
  const powerCurveSeries = comparison.projects
    .filter((project) => project.sensitivity?.cells?.length && project.sensitivity.current_power != null)
    .map((project) => ({
      id: project.id,
      label: project.project_name,
      cells: project.sensitivity?.cells ?? [],
      currentPower: project.sensitivity?.current_power ?? 0.8,
      metricType: (project.metric_type === "continuous" ? "continuous" : "binary") as "binary" | "continuous"
    }));
  const observedProjects = comparison.projects.filter((project) => project.observed_results);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  async function handleExport(format: "markdown" | "pdf") {
    setExportingFormat(format);
    setExportError("");
    try {
      const content = await exportComparisonRequest(
        comparison.projects.map((project) => project.id),
        format
      );
      if (format === "pdf") {
        const bytes = decodeBase64(content);
        downloadBlob(
          new Blob([bytes.buffer as ArrayBuffer], { type: "application/pdf" }),
          "comparison-dashboard.pdf"
        );
      } else {
        downloadBlob(
          new Blob([content], { type: "text/markdown" }),
          "comparison-dashboard.md"
        );
      }
    } catch (error) {
      setExportError(error instanceof Error ? error.message : t("comparison.dashboard.exportFailed"));
    } finally {
      setExportingFormat(null);
    }
  }

  function handleClose() {
    onClose();
    document.getElementById("compare-selected-projects-button")?.focus();
  }

  return (
    <div data-testid="comparison-dashboard" style={{ display: "grid", gap: 16 }}>
      <div className="card" style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <span className="pill">{t("comparison.dashboard.loaded", { count: comparison.projects.length })}</span>
            <h3 id="comparison-dashboard-heading" ref={headingRef} tabIndex={-1} style={{ marginTop: 12 }}>
              {t("comparison.dashboard.title")}
            </h3>
            <p className="muted">{t("comparison.dashboard.subtitle")}</p>
          </div>
          <div className="actions">
            <button
              className="btn secondary"
              type="button"
              disabled={exportingFormat !== null}
              onClick={() => void handleExport("markdown")}
            >
              {exportingFormat === "markdown" ? t("comparison.dashboard.exporting") : t("comparison.dashboard.exportMarkdown")}
            </button>
            <button
              className="btn secondary"
              type="button"
              disabled={exportingFormat !== null}
              onClick={() => void handleExport("pdf")}
            >
              {exportingFormat === "pdf" ? t("comparison.dashboard.exporting") : t("comparison.dashboard.exportPdf")}
            </button>
            <button
              className="btn ghost"
              type="button"
              data-testid="comparison-dashboard-close"
              onClick={handleClose}
            >
              {t("comparison.dashboard.close")}
            </button>
          </div>
        </div>
        {exportError ? <div className="error">{exportError}</div> : null}
        {hasMixedMetricTypes ? (
          <div className="callout">
            <strong>{t("comparison.dashboard.mixedMetricTypes")}</strong>
          </div>
        ) : null}
      </div>

      <section role="region" aria-labelledby="comparison-projects-heading" className="card" style={{ display: "grid", gap: 12 }}>
        <div>
          <h3 id="comparison-projects-heading">{t("comparison.dashboard.projectsTitle")}</h3>
          <p className="muted">{t("comparison.dashboard.projectsSubtitle")}</p>
        </div>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          {comparison.projects.map((project) => (
            <article key={project.id} className="card" style={{ display: "grid", gap: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "start" }}>
                <strong>{project.project_name}</strong>
                <span
                  className="pill"
                  style={{ color: severityColor(project.warning_severity), borderColor: severityColor(project.warning_severity) }}
                >
                  {project.warning_severity}
                </span>
              </div>
              <span className="muted">{project.metric_type}</span>
              <span>{t("comparison.dashboard.sampleSize", { value: project.total_sample_size })}</span>
              <span>{t("comparison.dashboard.duration", { value: project.estimated_duration_days })}</span>
              <span>{t("comparison.dashboard.warnings", { value: project.warnings_count })}</span>
            </article>
          ))}
        </div>
      </section>

      <section role="region" aria-labelledby="comparison-power-curves-heading" className="card" style={{ display: "grid", gap: 12 }}>
        <div>
          <h3 id="comparison-power-curves-heading">{t("comparison.dashboard.powerCurvesTitle")}</h3>
          <p className="muted">{t("comparison.dashboard.powerCurvesSubtitle")}</p>
        </div>
        <PowerCurveChart series={powerCurveSeries} />
      </section>

      <section role="region" aria-labelledby="comparison-sensitivity-heading" className="card" style={{ display: "grid", gap: 12 }}>
        <div>
          <h3 id="comparison-sensitivity-heading">{t("comparison.dashboard.sensitivityTitle")}</h3>
          <p className="muted">{t("comparison.dashboard.sensitivitySubtitle")}</p>
        </div>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
          {comparison.projects.map((project) => (
            <article key={project.id} data-testid="comparison-sensitivity-table" className="card" style={{ display: "grid", gap: 8 }}>
              <strong>{project.project_name}</strong>
              {project.sensitivity ? (
                <SensitivityTable
                  cells={project.sensitivity.cells}
                  currentMde={project.sensitivity.current_mde ?? 0}
                  currentPower={project.sensitivity.current_power ?? 0.8}
                  metricType={project.metric_type === "continuous" ? "continuous" : "binary"}
                />
              ) : (
                <span className="muted">{t("comparison.dashboard.sensitivityUnavailable")}</span>
              )}
            </article>
          ))}
        </div>
      </section>

      <section role="region" aria-labelledby="comparison-observed-effects-heading" className="card" style={{ display: "grid", gap: 12 }}>
        <div>
          <h3 id="comparison-observed-effects-heading">{t("comparison.dashboard.observedEffectsTitle")}</h3>
          <p className="muted">{t("comparison.dashboard.observedEffectsSubtitle")}</p>
        </div>
        <div style={{ display: "grid", gap: 12 }}>
          {observedProjects.map((project) => (
            <article key={project.id} data-testid="forest-plot-row" className="card" style={{ display: "grid", gap: 8 }}>
              <strong>{project.project_name}</strong>
              <ForestPlot
                effect={project.observed_results?.observed_effect ?? 0}
                ciLower={project.observed_results?.ci_lower ?? 0}
                ciUpper={project.observed_results?.ci_upper ?? 0}
                metricType={project.metric_type === "continuous" ? "continuous" : "binary"}
              />
            </article>
          ))}
        </div>
      </section>

      <section role="region" aria-labelledby="comparison-insights-heading" className="card" style={{ display: "grid", gap: 12 }}>
        <div>
          <h3 id="comparison-insights-heading">{t("comparison.dashboard.insightsTitle")}</h3>
          <p className="muted">{t("comparison.dashboard.insightsSubtitle")}</p>
        </div>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          <div className="card">
            <strong>{t("comparison.dashboard.sharedWarnings")}</strong>
            <ul className="list">
              {(comparison.shared_warnings.length ? comparison.shared_warnings : [t("comparison.dashboard.none")]).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="card">
            <strong>{t("comparison.dashboard.sharedRisks")}</strong>
            <ul className="list">
              {(comparison.shared_risks.length ? comparison.shared_risks : [t("comparison.dashboard.none")]).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="card">
            <strong>{t("comparison.dashboard.sharedAssumptions")}</strong>
            <ul className="list">
              {(comparison.shared_assumptions.length ? comparison.shared_assumptions : [t("comparison.dashboard.none")]).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          <div className="card">
            <strong>{t("comparison.dashboard.recommendationHighlights")}</strong>
            <ul className="list">
              {(comparison.recommendation_highlights.length ? comparison.recommendation_highlights : [t("comparison.dashboard.none")]).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>{t("comparison.dashboard.project")}</th>
              <th>{t("comparison.dashboard.uniqueWarnings")}</th>
              <th>{t("comparison.dashboard.uniqueRisks")}</th>
              <th>{t("comparison.dashboard.uniqueAssumptions")}</th>
            </tr>
          </thead>
          <tbody>
            {comparison.projects.map((project) => {
              const uniqueInsights = comparison.unique_per_project[project.id];
              return (
                <tr key={project.id}>
                  <th scope="row">{project.project_name}</th>
                  <td>{uniqueInsights?.warnings.join(", ") || t("comparison.dashboard.none")}</td>
                  <td>{uniqueInsights?.risks.join(", ") || t("comparison.dashboard.none")}</td>
                  <td>{uniqueInsights?.assumptions.join(", ") || t("comparison.dashboard.none")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
