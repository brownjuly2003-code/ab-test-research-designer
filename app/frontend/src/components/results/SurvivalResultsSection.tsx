import { useState } from "react";
import { useTranslation } from "react-i18next";

import { apiUrl } from "../../lib/experiment";
import type { SurvivalCurvePoint, SurvivalResultsResponse } from "../../lib/generated/api-contract";
import { formatPValue, formatStat } from "../../lib/formatNumber";
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
                <td>{point.survival.toFixed(3)}</td>
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

// Total arms are capped server-side at MAX_SURVIVAL_ARMS = 10 (control + treatment + 8 additional).
const MAX_ADDITIONAL_ARMS = 8;

type SurvivalTestType = "log_rank" | "fleming_harrington" | "cox";

export default function SurvivalResultsSection() {
  const { t } = useTranslation();
  const [controlText, setControlText] = useState("");
  const [treatmentText, setTreatmentText] = useState("");
  const [additionalArmsText, setAdditionalArmsText] = useState<string[]>([]);
  const [testType, setTestType] = useState<SurvivalTestType>("log_rank");
  const [fhRho, setFhRho] = useState("1");
  const [fhGamma, setFhGamma] = useState("0");
  const [alpha, setAlpha] = useState("0.05");
  const [analysis, setAnalysis] = useState<SurvivalResultsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runAnalysis() {
    const control = parseSurvivalArm(controlText);
    const treatment = parseSurvivalArm(treatmentText);
    const additional = additionalArmsText.map((text) => parseSurvivalArm(text));
    if (!control || !treatment || additional.some((arm) => arm === null)) {
      setError(t("results.survivalResults.validation.parseError"));
      setAnalysis(null);
      return;
    }
    if (testType === "cox" && additional.length > 0) {
      setError(t("results.survivalResults.validation.coxTwoArmsOnly"));
      setAnalysis(null);
      return;
    }
    const alphaValue = Number(alpha);
    const rhoValue = Number(fhRho);
    const gammaValue = Number(fhGamma);
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/v1/results/survival"), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify({
          control_arm: control,
          treatment_arm: treatment,
          additional_arms: additional,
          test_type: testType,
          fh_rho: Number.isFinite(rhoValue) ? rhoValue : 1,
          fh_gamma: Number.isFinite(gammaValue) ? gammaValue : 0,
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
        {additionalArmsText.map((text, index) => (
          <div className="field" key={index}>
            <label htmlFor={`survival-additional-${index}`}>
              {t("results.survivalResults.additionalArmLabel", { index: index + 3 })}
            </label>
            <textarea
              id={`survival-additional-${index}`}
              rows={5}
              value={text}
              placeholder={t("results.survivalResults.treatmentPlaceholder")}
              onChange={(event) =>
                setAdditionalArmsText((current) =>
                  current.map((value, i) => (i === index ? event.target.value : value))
                )
              }
            />
            <div className="actions" style={{ marginTop: "var(--space-2)" }}>
              <button
                className="btn ghost"
                type="button"
                onClick={() => {
                  setAdditionalArmsText((current) => current.filter((_, i) => i !== index));
                  setAnalysis(null);
                }}
              >
                {t("results.survivalResults.removeArm")}
              </button>
            </div>
          </div>
        ))}
        {additionalArmsText.length < MAX_ADDITIONAL_ARMS && testType !== "cox" ? (
          <div className="actions">
            <button
              className="btn ghost"
              type="button"
              onClick={() => setAdditionalArmsText((current) => [...current, ""])}
            >
              {t("results.survivalResults.addArm")}
            </button>
          </div>
        ) : null}
        <p className="muted">{t("results.survivalResults.dataHelp")}</p>
        <div className="field" style={{ maxWidth: "320px" }}>
          <label htmlFor="survival-test-type">{t("results.survivalResults.testTypeLabel")}</label>
          <select
            id="survival-test-type"
            value={testType}
            onChange={(event) => {
              setTestType(event.target.value as SurvivalTestType);
              setAnalysis(null);
              setError("");
            }}
          >
            <option value="log_rank">{t("results.survivalResults.testType.log_rank")}</option>
            <option value="fleming_harrington">{t("results.survivalResults.testType.fleming_harrington")}</option>
            <option value="cox">{t("results.survivalResults.testType.cox")}</option>
          </select>
        </div>
        {testType === "cox" ? <p className="muted">{t("results.survivalResults.coxHelp")}</p> : null}
        {testType === "fleming_harrington" ? (
          <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
            <div className="field" style={{ maxWidth: "160px" }}>
              <label htmlFor="survival-fh-rho">{t("results.survivalResults.rhoLabel")}</label>
              <input
                id="survival-fh-rho"
                type="number"
                min="0"
                max="4"
                step="0.5"
                value={fhRho}
                onChange={(event) => setFhRho(event.target.value)}
              />
            </div>
            <div className="field" style={{ maxWidth: "160px" }}>
              <label htmlFor="survival-fh-gamma">{t("results.survivalResults.gammaLabel")}</label>
              <input
                id="survival-fh-gamma"
                type="number"
                min="0"
                max="4"
                step="0.5"
                value={fhGamma}
                onChange={(event) => setFhGamma(event.target.value)}
              />
            </div>
            <p className="muted" style={{ alignSelf: "end" }}>{t("results.survivalResults.fhHelp")}</p>
          </div>
        ) : null}
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
            {analysis.hazard_ratio != null ? (
              <div className="card">
                <strong>{t("results.survivalResults.results.hazardRatio")}</strong>
                <div style={{ marginTop: "8px" }}>
                  {formatStat(analysis.hazard_ratio)}{" "}
                  <span className="muted">
                    [{analysis.hazard_ratio_ci_lower != null ? formatStat(analysis.hazard_ratio_ci_lower) : "-"}, {analysis.hazard_ratio_ci_upper != null ? formatStat(analysis.hazard_ratio_ci_upper) : "-"}]
                  </span>
                </div>
              </div>
            ) : null}
            <div className="card">
              <strong>
                {analysis.test_type === "cox"
                  ? t("results.survivalResults.statistic.waldChiSquare")
                  : t("results.survivalResults.statistic.chiSquare")}
              </strong>
              <div style={{ marginTop: "8px" }}>{formatStat(analysis.chi_square)}</div>
            </div>
            <div className="card">
              <strong>{t("results.survivalResults.results.degreesOfFreedom")}</strong>
              <div style={{ marginTop: "8px" }}>{analysis.degrees_of_freedom}</div>
            </div>
            <div className="card">
              <strong>{t("results.survivalResults.results.pValue")}</strong>
              <div style={{ marginTop: "8px" }}>{formatPValue(analysis.p_value)}</div>
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
          {analysis.arm_summaries && analysis.arm_summaries.length > 2 ? (
            <div className="card">
              <strong>{t("results.survivalResults.armSummaries.title")}</strong>
              <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
                <table>
                  <thead>
                    <tr>
                      <th>{t("results.survivalResults.armSummaries.arm")}</th>
                      <th>{t("results.survivalResults.armSummaries.n")}</th>
                      <th>{t("results.survivalResults.armSummaries.observedExpected")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.arm_summaries.map((summary, index) => (
                      <tr key={index}>
                        <td>
                          {index === 0
                            ? controlLabel
                            : index === 1
                              ? treatmentLabel
                              : t("results.survivalResults.additionalArmLabel", { index: index + 1 })}
                        </td>
                        <td>{summary.n}</td>
                        <td>
                          {summary.observed} / {summary.expected.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
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
            {(analysis.additional_arm_curves ?? []).map((curve, index) => (
              <CurveTable
                key={index}
                points={curve}
                caption={t("results.survivalResults.additionalArmLabel", { index: index + 3 })}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
