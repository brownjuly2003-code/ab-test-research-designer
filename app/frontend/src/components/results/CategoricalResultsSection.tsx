import { useState } from "react";
import { useTranslation } from "react-i18next";

import { apiUrl } from "../../lib/experiment";
import type { CategoricalResultsResponse } from "../../lib/generated/api-contract";
import { formatPValue, formatStat } from "../../lib/formatNumber";
import Icon from "../Icon";
import { buildApiRequestHeaders } from "./resultsShared";

/**
 * Parse a pasted contingency table: one group per line (rows), counts per outcome level separated by
 * commas / spaces / semicolons (columns). Returns ``null`` when the shape is unusable (fewer than two
 * rows or columns, ragged rows, or a non-integer / negative cell) so the caller can show a hint; the
 * server re-validates and owns the statistical degeneracy checks (empty row/column, cap).
 */
export function parseContingencyTable(raw: string): number[][] | null {
  const rows = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) =>
      line
        .split(/[\s,;]+/)
        .filter((token) => token.length > 0)
        .map((token) => Number(token))
    );
  if (rows.length < 2) {
    return null;
  }
  const cols = rows[0].length;
  if (cols < 2) {
    return null;
  }
  for (const row of rows) {
    if (row.length !== cols) {
      return null;
    }
    for (const value of row) {
      if (!Number.isInteger(value) || value < 0) {
        return null;
      }
    }
  }
  return rows;
}

/**
 * Qualitative magnitude of a Cramér's V effect size, so the raw number reads as meaning rather than an
 * opaque decimal. Uses Cohen's degrees-of-freedom-aware convention: w = V·√(min(r−1, c−1)) classified
 * against the standard w cut-offs 0.1 / 0.3 / 0.5 (Cohen, 1988). This reduces to V's own 0.1/0.3/0.5
 * cut-offs for a 2×2 table and tightens them as the table grows, matching Cohen's published V table.
 */
export function cramersVMagnitude(
  cramersV: number,
  numRows: number,
  numCols: number
): "negligible" | "small" | "medium" | "large" {
  const minDimension = Math.max(1, Math.min(numRows - 1, numCols - 1));
  const w = cramersV * Math.sqrt(minDimension);
  if (w < 0.1) {
    return "negligible";
  }
  if (w < 0.3) {
    return "small";
  }
  if (w < 0.5) {
    return "medium";
  }
  return "large";
}

type CategoricalTestType = "chi_square" | "g_test";

const CATEGORICAL_TEST_TYPES: CategoricalTestType[] = ["chi_square", "g_test"];

export default function CategoricalResultsSection() {
  const { t } = useTranslation();
  const [testType, setTestType] = useState<CategoricalTestType>("chi_square");
  const [tableText, setTableText] = useState("");
  const [alpha, setAlpha] = useState("0.05");
  const [analysis, setAnalysis] = useState<CategoricalResultsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runAnalysis() {
    if (tableText.trim().length === 0) {
      setError(t("results.categoricalResults.validation.empty"));
      setAnalysis(null);
      return;
    }
    const table = parseContingencyTable(tableText);
    if (!table) {
      setError(t("results.categoricalResults.validation.parseError"));
      setAnalysis(null);
      return;
    }
    const alphaValue = Number(alpha);
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/v1/results/categorical"), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify({ table, alpha: Number.isFinite(alphaValue) ? alphaValue : 0.05, test_type: testType })
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof body.detail === "string" ? body.detail : t("results.categoricalResults.validation.analysisUnavailable"));
      }
      setAnalysis(body as CategoricalResultsResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("results.categoricalResults.validation.analysisUnavailable"));
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <h3>{t("results.categoricalResults.title")}</h3>
      <p className="muted">{t("results.categoricalResults.description")}</p>
      <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
        <div className="field" style={{ maxWidth: "320px" }}>
          <label htmlFor="categorical-test-type">{t("results.categoricalResults.testTypeLabel")}</label>
          <select
            id="categorical-test-type"
            value={testType}
            onChange={(event) => {
              setTestType(event.target.value as CategoricalTestType);
              setAnalysis(null);
              setError("");
            }}
          >
            {CATEGORICAL_TEST_TYPES.map((value) => (
              <option key={value} value={value}>
                {t(`results.categoricalResults.testType.${value}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="categorical-table">{t("results.categoricalResults.tableLabel")}</label>
          <textarea id="categorical-table" rows={5} value={tableText} placeholder={t("results.categoricalResults.tablePlaceholder")} onChange={(event) => setTableText(event.target.value)} />
          <p className="muted" style={{ marginTop: "var(--space-2)" }}>{t("results.categoricalResults.tableHelp")}</p>
        </div>
        <div className="field" style={{ maxWidth: "220px" }}>
          <label htmlFor="categorical-alpha">{t("results.categoricalResults.alphaLabel")}</label>
          <input id="categorical-alpha" type="number" min="0.001" max="0.1" step="0.001" value={alpha} onChange={(event) => setAlpha(event.target.value)} />
        </div>
      </div>
      <div className="actions" style={{ marginTop: "var(--space-4)" }}>
        <button className="btn secondary" type="button" onClick={() => void runAnalysis()} disabled={loading}>
          {loading ? t("results.categoricalResults.analyzing") : t("results.categoricalResults.analyzeButton")}
        </button>
      </div>
      {error ? <div className="error">{error}</div> : null}
      {analysis ? (
        <div style={{ display: "grid", gap: "var(--space-4)", marginTop: "var(--space-4)" }}>
          <div className="callout" style={{ borderColor: analysis.is_significant ? "var(--color-success)" : "var(--color-warning)", background: analysis.is_significant ? "var(--color-success-light)" : "var(--color-warning-light)" }}>
            <Icon name={analysis.is_significant ? "check" : "info"} className="icon icon-inline" />
            <div style={{ display: "grid", gap: "6px" }}><strong>{analysis.verdict}</strong><span>{analysis.interpretation}</span></div>
          </div>
          {analysis.low_expected_warning ? (
            <div className="callout" style={{ borderColor: "var(--color-warning)", background: "var(--color-warning-light)" }}>
              <Icon name="info" className="icon icon-inline" />
              <span>{t("results.categoricalResults.lowExpectedWarning")}</span>
            </div>
          ) : null}
          <div style={{ display: "grid", gap: "var(--space-3)", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
            <div className="card"><strong>{t(`results.categoricalResults.statistic.${analysis.test_type}`)}</strong><div style={{ marginTop: "8px" }}>{formatStat(analysis.chi_square)}</div></div>
            <div className="card"><strong>{t("results.categoricalResults.results.degreesOfFreedom")}</strong><div style={{ marginTop: "8px" }}>{analysis.degrees_of_freedom}</div></div>
            <div className="card"><strong>{t("results.categoricalResults.results.pValue")}</strong><div style={{ marginTop: "8px" }}>{formatPValue(analysis.p_value)}</div></div>
            <div className="card"><strong>{t("results.categoricalResults.results.cramersV")}</strong><div style={{ marginTop: "8px" }}>{formatStat(analysis.cramers_v)} <span className="muted">· {t(`results.categoricalResults.magnitude.${cramersVMagnitude(analysis.cramers_v, analysis.num_rows, analysis.num_cols)}`)}</span></div></div>
            <div className="card"><strong>{t("results.categoricalResults.results.sampleSize")}</strong><div style={{ marginTop: "8px" }}>{analysis.n_total}</div></div>
            <div className="card"><strong>{t("results.categoricalResults.results.shape")}</strong><div style={{ marginTop: "8px" }}>{analysis.num_rows}×{analysis.num_cols}</div></div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
