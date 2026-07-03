import { useState } from "react";
import { useTranslation } from "react-i18next";

import { apiUrl } from "../../lib/experiment";
import type { PairedResultsResponse } from "../../lib/generated/api-contract";
import Icon from "../Icon";
import { parseSampleValues } from "./observedResultsShared";
import { buildApiRequestHeaders } from "./resultsShared";

type PairedTestType = "paired_t" | "wilcoxon" | "mcnemar";

const TEST_TYPES: PairedTestType[] = ["paired_t", "wilcoxon", "mcnemar"];

export default function PairedResultsSection() {
  const { t } = useTranslation();
  const [testType, setTestType] = useState<PairedTestType>("paired_t");
  const [controlText, setControlText] = useState("");
  const [treatmentText, setTreatmentText] = useState("");
  const [alpha, setAlpha] = useState("0.05");
  const [analysis, setAnalysis] = useState<PairedResultsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runAnalysis() {
    const control = parseSampleValues(controlText);
    const treatment = parseSampleValues(treatmentText);
    if (control === null || treatment === null) {
      setError(t("results.pairedResults.validation.parseError"));
      setAnalysis(null);
      return;
    }
    if (control.length !== treatment.length) {
      setError(t("results.pairedResults.validation.lengthMismatch"));
      setAnalysis(null);
      return;
    }
    const alphaValue = Number(alpha);
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/v1/results/paired"), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify({
          test_type: testType,
          control_values: control,
          treatment_values: treatment,
          alpha: Number.isFinite(alphaValue) ? alphaValue : 0.05
        })
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : t("results.pairedResults.validation.analysisUnavailable")
        );
      }
      setAnalysis(body as PairedResultsResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("results.pairedResults.validation.analysisUnavailable"));
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }

  const isMcNemar = testType === "mcnemar";

  return (
    <div className="card">
      <h3>{t("results.pairedResults.title")}</h3>
      <p className="muted">{t("results.pairedResults.description")}</p>
      <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
        <div className="field" style={{ maxWidth: "320px" }}>
          <label htmlFor="paired-test-type">{t("results.pairedResults.testTypeLabel")}</label>
          <select
            id="paired-test-type"
            value={testType}
            onChange={(event) => {
              setTestType(event.target.value as PairedTestType);
              setAnalysis(null);
              setError("");
            }}
          >
            {TEST_TYPES.map((value) => (
              <option key={value} value={value}>
                {t(`results.pairedResults.testType.${value}`)}
              </option>
            ))}
          </select>
        </div>
        <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
          <div className="field">
            <label htmlFor="paired-control">{t("results.pairedResults.controlLabel")}</label>
            <textarea id="paired-control" rows={5} value={controlText} placeholder={t("results.pairedResults.valuesPlaceholder")} onChange={(event) => setControlText(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="paired-treatment">{t("results.pairedResults.treatmentLabel")}</label>
            <textarea id="paired-treatment" rows={5} value={treatmentText} placeholder={t("results.pairedResults.valuesPlaceholder")} onChange={(event) => setTreatmentText(event.target.value)} />
          </div>
        </div>
        <p className="muted">{isMcNemar ? t("results.pairedResults.mcnemarHelp") : t("results.pairedResults.valuesHelp")}</p>
        <div className="field" style={{ maxWidth: "220px" }}>
          <label htmlFor="paired-alpha">{t("results.pairedResults.alphaLabel")}</label>
          <input id="paired-alpha" type="number" min="0.001" max="0.1" step="0.001" value={alpha} onChange={(event) => setAlpha(event.target.value)} />
        </div>
      </div>
      <div className="actions" style={{ marginTop: "var(--space-4)" }}>
        <button className="btn secondary" type="button" onClick={() => void runAnalysis()} disabled={loading}>
          {loading ? t("results.pairedResults.analyzing") : t("results.pairedResults.analyzeButton")}
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
            <div className="card"><strong>{analysis.effect_label}</strong><div style={{ marginTop: "8px" }}>{analysis.effect} <span className="muted">[{analysis.ci_lower}, {analysis.ci_upper}]</span></div></div>
            <div className="card"><strong>{t("results.pairedResults.results.pValue")}</strong><div style={{ marginTop: "8px" }}>{analysis.p_value.toFixed(6)}</div></div>
            <div className="card"><strong>{t("results.pairedResults.results.testStatistic")}</strong><div style={{ marginTop: "8px" }}>{analysis.test_statistic}</div></div>
            {analysis.effect_size != null ? (
              <div className="card"><strong>{analysis.effect_size_label}</strong><div style={{ marginTop: "8px" }}>{analysis.effect_size}</div></div>
            ) : null}
            <div className="card"><strong>{t("results.pairedResults.results.pairs")}</strong><div style={{ marginTop: "8px" }}>{analysis.n_pairs}</div></div>
            {analysis.n_zero_differences != null ? (
              <div className="card"><strong>{t("results.pairedResults.results.zeroDifferences")}</strong><div style={{ marginTop: "8px" }}>{analysis.n_zero_differences}</div></div>
            ) : null}
            {analysis.n_discordant != null ? (
              <div className="card"><strong>{t("results.pairedResults.results.discordant")}</strong><div style={{ marginTop: "8px" }}>{analysis.discordant_positive} / {analysis.discordant_negative} <span className="muted">({analysis.n_discordant})</span></div></div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
