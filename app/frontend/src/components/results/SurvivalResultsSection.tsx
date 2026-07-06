import { useState } from "react";
import { useTranslation } from "react-i18next";

import { apiUrl } from "../../lib/experiment";
import type { SurvivalCurvePoint, SurvivalResultsResponse } from "../../lib/generated/api-contract";
import Icon from "../Icon";
import SurvivalCurveChart, { type SurvivalSeriesPoint } from "../SurvivalCurveChart";
import { buildApiRequestHeaders } from "./resultsShared";

type ParsedArm = { durations: number[]; events_observed: boolean[] };

/**
 * Parse one pasted survival arm: one subject per line, ``duration status``, where ``status`` is 1 for
 * an observed event or 0 for a right-censored observation (still event-free at last follow-up). A line
 * with only a duration is treated as an observed event. Returns ``null`` when the shape is unusable
 * (no rows, a non-numeric / negative duration, or a status token other than 0 / 1) so the caller can
 * show a hint; the server re-validates and owns the statistical degeneracy checks.
 */
export function parseSurvivalArm(raw: string): ParsedArm | null {
  const rows = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  if (rows.length < 1) {
    return null;
  }
  const durations: number[] = [];
  const events: boolean[] = [];
  for (const row of rows) {
    const tokens = row.split(/[\s,;]+/).filter((token) => token.length > 0);
    const duration = Number(tokens[0]);
    if (!Number.isFinite(duration) || duration < 0) {
      return null;
    }
    let event = true;
    if (tokens.length >= 2) {
      if (tokens[1] === "0") {
        event = false;
      } else if (tokens[1] === "1") {
        event = true;
      } else {
        return null;
      }
    }
    durations.push(duration);
    events.push(event);
  }
  return { durations, events_observed: events };
}

/**
 * Merge the two per-arm Kaplan–Meier step curves into a single carry-forward series (both arms start
 * at S(0) = 1) so a single recharts dataset can draw both ``stepAfter`` curves.
 */
export function buildSurvivalSeries(
  control: SurvivalCurvePoint[],
  treatment: SurvivalCurvePoint[]
): SurvivalSeriesPoint[] {
  const times = new Set<number>([0]);
  for (const point of control) {
    times.add(point.time);
  }
  for (const point of treatment) {
    times.add(point.time);
  }
  const survivalAt = (curve: SurvivalCurvePoint[], time: number): number => {
    let survival = 1;
    for (const point of curve) {
      if (point.time <= time) {
        survival = point.survival;
      } else {
        break;
      }
    }
    return survival;
  };
  return Array.from(times)
    .sort((a, b) => a - b)
    .map((time) => ({
      time,
      control: survivalAt(control, time),
      treatment: survivalAt(treatment, time)
    }));
}

function CurveTable({ points, caption }: { points: SurvivalCurvePoint[]; caption: string }) {
  const { t } = useTranslation();
  return (
    <div className="card">
      <strong>{caption}</strong>
      <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
        <table>
          <thead>
            <tr>
              <th>{t("results.survivalResults.curve.time")}</th>
              <th>{t("results.survivalResults.curve.atRisk")}</th>
              <th>{t("results.survivalResults.curve.events")}</th>
              <th>{t("results.survivalResults.curve.survival")}</th>
              <th>{t("results.survivalResults.curve.ci")}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point, index) => (
              <tr key={index}>
                <td>{point.time}</td>
                <td>{point.at_risk}</td>
                <td>{point.n_events}</td>
                <td>{point.survival.toFixed(4)}</td>
                <td>
                  {point.ci_lower.toFixed(3)} – {point.ci_upper.toFixed(3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function SurvivalResultsSection() {
  const { t } = useTranslation();
  const [controlText, setControlText] = useState("");
  const [treatmentText, setTreatmentText] = useState("");
  const [alpha, setAlpha] = useState("0.05");
  const [analysis, setAnalysis] = useState<SurvivalResultsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runAnalysis() {
    const control = parseSurvivalArm(controlText);
    const treatment = parseSurvivalArm(treatmentText);
    if (!control || !treatment) {
      setError(t("results.survivalResults.validation.parseError"));
      setAnalysis(null);
      return;
    }
    const alphaValue = Number(alpha);
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/v1/results/survival"), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify({
          control_arm: control,
          treatment_arm: treatment,
          alpha: Number.isFinite(alphaValue) ? alphaValue : 0.05
        })
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : t("results.survivalResults.validation.analysisUnavailable")
        );
      }
      setAnalysis(body as SurvivalResultsResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("results.survivalResults.validation.analysisUnavailable"));
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }

  const controlLabel = t("results.survivalResults.controlLabel");
  const treatmentLabel = t("results.survivalResults.treatmentLabel");

  return (
    <div className="card">
      <h3>{t("results.survivalResults.title")}</h3>
      <p className="muted">{t("results.survivalResults.description")}</p>
      <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
        <div className="field">
          <label htmlFor="survival-control">{controlLabel}</label>
          <textarea
            id="survival-control"
            rows={5}
            value={controlText}
            placeholder={t("results.survivalResults.controlPlaceholder")}
            onChange={(event) => setControlText(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="survival-treatment">{treatmentLabel}</label>
          <textarea
            id="survival-treatment"
            rows={5}
            value={treatmentText}
            placeholder={t("results.survivalResults.treatmentPlaceholder")}
            onChange={(event) => setTreatmentText(event.target.value)}
          />
        </div>
        <p className="muted">{t("results.survivalResults.dataHelp")}</p>
        <div className="field" style={{ maxWidth: "220px" }}>
          <label htmlFor="survival-alpha">{t("results.survivalResults.alphaLabel")}</label>
          <input
            id="survival-alpha"
            type="number"
            min="0.001"
            max="0.1"
            step="0.001"
            value={alpha}
            onChange={(event) => setAlpha(event.target.value)}
          />
        </div>
      </div>
      <div className="actions" style={{ marginTop: "var(--space-4)" }}>
        <button className="btn secondary" type="button" onClick={() => void runAnalysis()} disabled={loading}>
          {loading ? t("results.survivalResults.analyzing") : t("results.survivalResults.analyzeButton")}
        </button>
      </div>
      {error ? <div className="error">{error}</div> : null}
      {analysis ? (
        <div style={{ display: "grid", gap: "var(--space-4)", marginTop: "var(--space-4)" }}>
          <div
            className="callout"
            style={{
              borderColor: analysis.is_significant ? "var(--color-success)" : "var(--color-warning)",
              background: analysis.is_significant ? "var(--color-success-light)" : "var(--color-warning-light)"
            }}
          >
            <Icon name={analysis.is_significant ? "check" : "info"} className="icon icon-inline" />
            <div style={{ display: "grid", gap: "6px" }}>
              <strong>{analysis.verdict}</strong>
              <span>{analysis.interpretation}</span>
            </div>
          </div>
          <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
            <div className="card">
              <strong>{t("results.survivalResults.statistic.chiSquare")}</strong>
              <div style={{ marginTop: "8px" }}>{analysis.chi_square.toFixed(4)}</div>
            </div>
            <div className="card">
              <strong>{t("results.survivalResults.results.degreesOfFreedom")}</strong>
              <div style={{ marginTop: "8px" }}>{analysis.degrees_of_freedom}</div>
            </div>
            <div className="card">
              <strong>{t("results.survivalResults.results.pValue")}</strong>
              <div style={{ marginTop: "8px" }}>{analysis.p_value.toFixed(6)}</div>
            </div>
            <div className="card">
              <strong>{t("results.survivalResults.results.observedControl")}</strong>
              <div style={{ marginTop: "8px" }}>
                {analysis.observed_control} / {analysis.expected_control.toFixed(2)}
              </div>
            </div>
            <div className="card">
              <strong>{t("results.survivalResults.results.observedTreatment")}</strong>
              <div style={{ marginTop: "8px" }}>
                {analysis.observed_treatment} / {analysis.expected_treatment.toFixed(2)}
              </div>
            </div>
            <div className="card">
              <strong>{t("results.survivalResults.results.sampleSize")}</strong>
              <div style={{ marginTop: "8px" }}>
                {analysis.n_control} / {analysis.n_treatment}
              </div>
            </div>
          </div>
          <SurvivalCurveChart
            series={buildSurvivalSeries(analysis.control_curve, analysis.treatment_curve)}
            controlLabel={controlLabel}
            treatmentLabel={treatmentLabel}
            ariaLabel={t("results.survivalResults.chart.ariaLabel")}
            timeAxisLabel={t("results.survivalResults.chart.timeAxis")}
            survivalAxisLabel={t("results.survivalResults.chart.survivalAxis")}
          />
          <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
            <CurveTable points={analysis.control_curve} caption={controlLabel} />
            <CurveTable points={analysis.treatment_curve} caption={treatmentLabel} />
          </div>
        </div>
      ) : null}
    </div>
  );
}
