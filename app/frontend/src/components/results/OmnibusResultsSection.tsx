import { useState } from "react";
import { useTranslation } from "react-i18next";

import { apiUrl } from "../../lib/experiment";
import type { OmnibusResultsResponse } from "../../lib/generated/api-contract";
import Icon from "../Icon";
import { buildApiRequestHeaders } from "./resultsShared";

type OmnibusTestType = "welch_anova" | "kruskal_wallis";

const TEST_TYPES: OmnibusTestType[] = ["welch_anova", "kruskal_wallis"];

/**
 * Parse pasted group data for an omnibus test: one group per line (rows), numeric values per line
 * separated by commas / spaces / semicolons. Returns ``null`` when the shape is unusable (fewer than
 * two groups, or a group with fewer than two numeric values) so the caller can show a hint; the
 * server re-validates and owns the statistical degeneracy checks (zero within-group variance, no rank
 * variation, caps).
 */
export function parseGroups(raw: string): number[][] | null {
  const groups = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) =>
      line
        .split(/[\s,;]+/)
        .filter((token) => token.length > 0)
        .map((token) => Number(token))
    );
  if (groups.length < 2) {
    return null;
  }
  for (const group of groups) {
    if (group.length < 2) {
      return null;
    }
    for (const value of group) {
      if (!Number.isFinite(value)) {
        return null;
      }
    }
  }
  return groups;
}

export default function OmnibusResultsSection() {
  const { t } = useTranslation();
  const [testType, setTestType] = useState<OmnibusTestType>("welch_anova");
  const [groupsText, setGroupsText] = useState("");
  const [alpha, setAlpha] = useState("0.05");
  const [analysis, setAnalysis] = useState<OmnibusResultsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runAnalysis() {
    const groups = parseGroups(groupsText);
    if (!groups) {
      setError(t("results.omnibusResults.validation.parseError"));
      setAnalysis(null);
      return;
    }
    const alphaValue = Number(alpha);
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl("/api/v1/results/omnibus"), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify({
          test_type: testType,
          groups,
          alpha: Number.isFinite(alphaValue) ? alphaValue : 0.05
        })
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : t("results.omnibusResults.validation.analysisUnavailable")
        );
      }
      setAnalysis(body as OmnibusResultsResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("results.omnibusResults.validation.analysisUnavailable"));
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  }

  const isWelch = analysis?.test_type === "welch_anova";
  const degreesOfFreedom = analysis
    ? isWelch && analysis.df_denominator != null
      ? `${analysis.df_numerator} · ${analysis.df_denominator}`
      : String(analysis.df_numerator)
    : "";

  return (
    <div className="card">
      <h3>{t("results.omnibusResults.title")}</h3>
      <p className="muted">{t("results.omnibusResults.description")}</p>
      <div style={{ display: "grid", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
        <div className="field" style={{ maxWidth: "320px" }}>
          <label htmlFor="omnibus-test-type">{t("results.omnibusResults.testTypeLabel")}</label>
          <select
            id="omnibus-test-type"
            value={testType}
            onChange={(event) => {
              setTestType(event.target.value as OmnibusTestType);
              setAnalysis(null);
              setError("");
            }}
          >
            {TEST_TYPES.map((value) => (
              <option key={value} value={value}>
                {t(`results.omnibusResults.testType.${value}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="omnibus-groups">{t("results.omnibusResults.groupsLabel")}</label>
          <textarea id="omnibus-groups" rows={5} value={groupsText} placeholder={t("results.omnibusResults.groupsPlaceholder")} onChange={(event) => setGroupsText(event.target.value)} />
          <p className="muted" style={{ marginTop: "var(--space-2)" }}>{t("results.omnibusResults.groupsHelp")}</p>
        </div>
        <div className="field" style={{ maxWidth: "220px" }}>
          <label htmlFor="omnibus-alpha">{t("results.omnibusResults.alphaLabel")}</label>
          <input id="omnibus-alpha" type="number" min="0.001" max="0.1" step="0.001" value={alpha} onChange={(event) => setAlpha(event.target.value)} />
        </div>
      </div>
      <div className="actions" style={{ marginTop: "var(--space-4)" }}>
        <button className="btn secondary" type="button" onClick={() => void runAnalysis()} disabled={loading}>
          {loading ? t("results.omnibusResults.analyzing") : t("results.omnibusResults.analyzeButton")}
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
            <div className="card"><strong>{t(`results.omnibusResults.statistic.${analysis.test_type}`)}</strong><div style={{ marginTop: "8px" }}>{analysis.test_statistic.toFixed(4)}</div></div>
            <div className="card"><strong>{t("results.omnibusResults.results.degreesOfFreedom")}</strong><div style={{ marginTop: "8px" }}>{degreesOfFreedom}</div></div>
            <div className="card"><strong>{t("results.omnibusResults.results.pValue")}</strong><div style={{ marginTop: "8px" }}>{analysis.p_value.toFixed(6)}</div></div>
            <div className="card"><strong>{analysis.effect_size_label}</strong><div style={{ marginTop: "8px" }}>{analysis.effect_size.toFixed(4)}</div></div>
            <div className="card"><strong>{t("results.omnibusResults.results.groups")}</strong><div style={{ marginTop: "8px" }}>{analysis.num_groups}</div></div>
            <div className="card"><strong>{t("results.omnibusResults.results.sampleSize")}</strong><div style={{ marginTop: "8px" }}>{analysis.n_total}</div></div>
          </div>
          <div className="card">
            <strong>{t("results.omnibusResults.groupSummary.header")}</strong>
            <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
              <table>
                <thead>
                  <tr>
                    <th>{t("results.omnibusResults.groupSummary.group")}</th>
                    <th>{t("results.omnibusResults.groupSummary.n")}</th>
                    <th>{isWelch ? t("results.omnibusResults.groupSummary.mean") : t("results.omnibusResults.groupSummary.median")}</th>
                    <th>{isWelch ? t("results.omnibusResults.groupSummary.std") : t("results.omnibusResults.groupSummary.meanRank")}</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.group_summaries.map((summary, index) => (
                    <tr key={index}>
                      <td>{index + 1}</td>
                      <td>{summary.n}</td>
                      <td>{isWelch ? summary.mean : summary.median}</td>
                      <td>{isWelch ? summary.std : summary.mean_rank}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
