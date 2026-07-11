import { useState } from "react";
import { useTranslation } from "react-i18next";

import { apiUrl } from "../../lib/experiment";
import type { ResultsAnalysisResponse } from "../../lib/experiment";
import { formatPValue } from "../../lib/formatNumber";
import Icon from "../Icon";
import { parseSampleValues } from "./observedResultsShared";
import { buildApiRequestHeaders } from "./resultsShared";

type RatioResultsSectionProps = {
  onResultsAnalysisChange?: (analysis: ResultsAnalysisResponse | null) => void;
};

export default function RatioResultsSection({ onResultsAnalysisChange }: RatioResultsSectionProps) {
  const { t } = useTranslation();
  const [controlNumeratorsText, setControlNumeratorsText] = useState("");
  const [controlDenominatorsText, setControlDenominatorsText] = useState("");
  const [treatmentNumeratorsText, setTreatmentNumeratorsText] = useState("");
  const [treatmentDenominatorsText, setTreatmentDenominatorsText] = useState("");
  const [alpha, setAlpha] = useState("0.05");
  const [analysis, setAnalysis] = useState<ResultsAnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runAnalysis() {
    const controlNumerators = parseSampleValues(controlNumeratorsText);
    const controlDenominators = parseSampleValues(controlDenominatorsText);
    const treatmentNumerators = parseSampleValues(treatmentNumeratorsText);
    const treatmentDenominators = parseSampleValues(treatmentDenominatorsText);
    if (
      controlNumerators === null ||
      controlDenominators === null ||
      treatmentNumerators === null ||
      treatmentDenominators === null
    ) {
      setError(t("results.ratioResults.validation.parseError"));
      setAnalysis(null);
      onResultsAnalysisChange?.(null);
      return;
    }
    if (
      controlNumerators.length !== controlDenominators.length ||
      treatmentNumerators.length !== treatmentDenominators.length
    ) {
      setError(t("results.ratioResults.validation.lengthMismatch"));
      setAnalysis(null);
      onResultsAnalysisChange?.(null);
      return;
    }
    const alphaValue = Number(alpha);
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/v1/results/ratio"), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify({
          control_arm: { numerators: controlNumerators, denominators: controlDenominators },
          treatment_arm: { numerators: treatmentNumerators, denominators: treatmentDenominators },
          alpha: Number.isFinite(alphaValue) ? alphaValue : 0.05
        })
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : t("results.ratioResults.validation.analysisUnavailable")
        );
      }
      const nextAnalysis = body as ResultsAnalysisResponse;
      setAnalysis(nextAnalysis);
      onResultsAnalysisChange?.(nextAnalysis);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("results.ratioResults.validation.analysisUnavailable"));
      setAnalysis(null);
      onResultsAnalysisChange?.(null);
    } finally {
      setLoading(false);
    }
  }

  const armFields: Array<{
    id: string;
    labelKey: string;
    value: string;
    onChange: (value: string) => void;
  }> = [
    { id: "ratio-control-numerators", labelKey: "results.ratioResults.controlNumeratorsLabel", value: controlNumeratorsText, onChange: setControlNumeratorsText },
    { id: "ratio-control-denominators", labelKey: "results.ratioResults.controlDenominatorsLabel", value: controlDenominatorsText, onChange: setControlDenominatorsText },
    { id: "ratio-treatment-numerators", labelKey: "results.ratioResults.treatmentNumeratorsLabel", value: treatmentNumeratorsText, onChange: setTreatmentNumeratorsText },
    { id: "ratio-treatment-denominators", labelKey: "results.ratioResults.treatmentDenominatorsLabel", value: treatmentDenominatorsText, onChange: setTreatmentDenominatorsText }
  ];

  return (
    <div className="card">
      <h3>{t("results.ratioResults.title")}</h3>
      <p className="muted">{t("results.ratioResults.description")}</p>
      <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
        <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          {armFields.map((field) => (
            <div className="field" key={field.id}>
              <label htmlFor={field.id}>{t(field.labelKey)}</label>
              <textarea
                id={field.id}
                rows={5}
                value={field.value}
                placeholder={t("results.ratioResults.valuesPlaceholder")}
                onChange={(event) => field.onChange(event.target.value)}
              />
            </div>
          ))}
        </div>
        <p className="muted">{t("results.ratioResults.valuesHelp")}</p>
        <div className="field" style={{ maxWidth: "220px" }}>
          <label htmlFor="ratio-alpha">{t("results.ratioResults.alphaLabel")}</label>
          <input id="ratio-alpha" type="number" min="0.001" max="0.1" step="0.001" value={alpha} onChange={(event) => setAlpha(event.target.value)} />
        </div>
      </div>
      <div className="actions" style={{ marginTop: "var(--space-4)" }}>
        <button className="btn secondary" type="button" onClick={() => void runAnalysis()} disabled={loading}>
          {loading ? t("results.ratioResults.analyzing") : t("results.ratioResults.analyzeButton")}
        </button>
      </div>
      {error ? <div className="error">{error}</div> : null}
      {analysis ? (
        <div style={{ display: "grid", gap: "var(--space-4)", marginTop: "var(--space-4)" }}>
          <div className="callout" style={{ borderColor: analysis.is_significant ? "var(--color-success)" : "var(--color-warning)", background: analysis.is_significant ? "var(--color-success-light)" : "var(--color-warning-light)" }}>
            <Icon name={analysis.is_significant ? "check" : "info"} className="icon icon-inline" />
            <div style={{ display: "grid", gap: "6px" }}><strong>{analysis.verdict}</strong><span>{analysis.interpretation}</span></div>
          </div>
          <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
            <div className="card"><strong>{t("results.ratioResults.results.effect")}</strong><div style={{ marginTop: "8px" }}>{analysis.observed_effect} <span className="muted">[{analysis.ci_lower}, {analysis.ci_upper}]</span></div></div>
            <div className="card"><strong>{t("results.ratioResults.results.relativeEffect")}</strong><div style={{ marginTop: "8px" }}>{analysis.observed_effect_relative}%</div></div>
            <div className="card"><strong>{t("results.ratioResults.results.pValue")}</strong><div style={{ marginTop: "8px" }}>{formatPValue(analysis.p_value)}</div></div>
            <div className="card"><strong>{t("results.ratioResults.results.testStatistic")}</strong><div style={{ marginTop: "8px" }}>{analysis.test_statistic}</div></div>
            <div className="card"><strong>{t("results.ratioResults.results.power")}</strong><div style={{ marginTop: "8px" }}>{analysis.power_achieved}</div></div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
