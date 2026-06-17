import { useEffect, useState } from "react";

import { t } from "../../i18n";
import type { DecisionReadoutResponse, DecisionReason } from "../../lib/api";
import { apiUrl } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import { buildApiRequestHeaders, getDisplayedAnalysis } from "./resultsShared";

type Verdict = DecisionReadoutResponse["verdict"];

// The execution surface has no shared "pill" colour modifiers, so the traffic light leans on the
// semantic colour tokens directly (colour + text label, never colour alone).
const VERDICT_COLORS: Record<Verdict, { accent: string; tint: string }> = {
  ship: { accent: "var(--color-success)", tint: "var(--color-success-light)" },
  keep_running: { accent: "var(--color-warning)", tint: "var(--color-warning-light)" },
  no_ship: { accent: "var(--color-danger)", tint: "var(--color-danger-light)" }
};

function formatNumber(value: number | null | undefined, digits = 4): string {
  if (value == null) {
    return "—";
  }
  return value.toFixed(digits);
}

function formatSignedPercent(value: number | null | undefined): string {
  // observed_effect_relative is already a percentage number (e.g. 20.0 -> "+20.00%").
  if (value == null) {
    return "—";
  }
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatProbability(fraction: number | null | undefined): string {
  // probability_treatment_beats_control / information_fraction are fractions in [0, 1].
  if (fraction == null) {
    return "—";
  }
  return `${(fraction * 100).toFixed(2)}%`;
}

export default function DecisionReadoutSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const resultsProjectId = useAnalysisStore((state) => state.resultsProjectId);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const selectedHistoryProjectId = useProjectStore((state) => state.selectedHistoryRun?.project_id ?? null);
  const activeProjectId = useProjectStore((state) => state.activeProjectId);

  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryAnalysis, analysisResult);
  const experimentId = selectedHistoryProjectId ?? resultsProjectId ?? activeProjectId;
  const variantNames = displayedAnalysis?.report?.experiment_design?.variants.map((variant) => variant.name) ?? [];

  const [decision, setDecision] = useState<DecisionReadoutResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setDecision(null);
    setError("");
    setLoading(false);
    setCopied(false);
  }, [experimentId]);

  async function refresh(): Promise<void> {
    if (!experimentId) {
      return;
    }
    setLoading(true);
    setError("");
    setCopied(false);
    try {
      const response = await fetch(apiUrl(`/api/v1/experiments/${encodeURIComponent(experimentId)}/decision`), {
        method: "GET",
        headers: buildApiRequestHeaders()
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : t("results.decision.serviceUnavailable");
        throw new Error(detail);
      }
      setDecision(body as DecisionReadoutResponse);
    } catch (requestError) {
      setDecision(null);
      setError(requestError instanceof Error ? requestError.message : t("results.decision.serviceUnavailable"));
    } finally {
      setLoading(false);
    }
  }

  function armName(arm: number): string {
    return variantNames[arm] ?? `#${arm + 1}`;
  }

  function renderReason(kind: "reason" | "blocker", item: DecisionReason): string {
    const params = item.params ?? {};
    return t(`results.decision.${kind}.${item.code}`, {
      arm: params.arm != null ? armName(Number(params.arm)) : "",
      effect: formatSignedPercent(params.effect_relative as number | undefined),
      p: formatNumber(params.p_value as number | undefined, 4),
      probability: formatProbability(params.probability as number | undefined),
      fraction: formatProbability(params.information_fraction as number | undefined)
    });
  }

  function buildMarkdown(readout: DecisionReadoutResponse): string {
    const verdictLabel = t(`results.decision.verdict.${readout.verdict}`);
    const confidenceLabel = t(`results.decision.confidence.${readout.confidence}`);
    const lines: string[] = [
      `# ${t("results.decision.exportHeading")}`,
      "",
      `**${t("results.decision.verdictLabel")}:** ${verdictLabel} · ${t("results.decision.confidence.label")}: ${confidenceLabel}`
    ];
    const blockers = readout.blockers ?? [];
    const reasons = readout.reasons ?? [];
    if (blockers.length > 0) {
      lines.push("", `## ${t("results.decision.blockersTitle")}`);
      blockers.forEach((blocker) => lines.push(`- ${renderReason("blocker", blocker)}`));
    }
    if (reasons.length > 0) {
      lines.push("", `## ${t("results.decision.reasonsTitle")}`);
      reasons.forEach((reason) => lines.push(`- ${renderReason("reason", reason)}`));
    }
    return lines.join("\n");
  }

  async function copyMarkdown(readout: DecisionReadoutResponse): Promise<void> {
    const markdown = buildMarkdown(readout);
    try {
      await navigator.clipboard?.writeText(markdown);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function downloadMarkdown(readout: DecisionReadoutResponse): void {
    const blob = new Blob([buildMarkdown(readout)], { type: "text/markdown" });
    const objectUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `decision-readout-${readout.experiment_id}.md`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(objectUrl);
  }

  if (!displayedAnalysis?.report) {
    return null;
  }

  const verdictColors = decision ? VERDICT_COLORS[decision.verdict] : null;
  const blockers = decision?.blockers ?? [];
  const reasons = decision?.reasons ?? [];

  return (
    <div className="card">
      <h3>{t("results.decision.title")}</h3>
      <p className="muted">{t("results.decision.description")}</p>

      {experimentId ? (
        <div className="actions" style={{ marginTop: "var(--space-4)" }}>
          <button className="btn secondary" type="button" onClick={() => void refresh()} disabled={loading}>
            {loading ? t("results.decision.refreshing") : t("results.decision.refresh")}
          </button>
        </div>
      ) : (
        <div className="callout" style={{ marginTop: "var(--space-4)" }}>
          <Icon name="info" className="icon icon-inline" />
          <span>{t("results.decision.saveFirst")}</span>
        </div>
      )}

      {error ? <div className="error">{error}</div> : null}

      {decision && verdictColors ? (
        <div style={{ marginTop: "var(--space-4)", display: "grid", gap: "var(--space-3)" }}>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: "12px",
              padding: "var(--space-3)",
              borderRadius: "var(--radius-md, 10px)",
              borderLeft: `4px solid ${verdictColors.accent}`,
              background: verdictColors.tint
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: "12px",
                height: "12px",
                borderRadius: "999px",
                background: verdictColors.accent,
                flex: "0 0 auto"
              }}
            />
            <strong style={{ fontSize: "1.1rem", color: verdictColors.accent }}>
              {t(`results.decision.verdict.${decision.verdict}`)}
            </strong>
            <span className="pill">
              {t("results.decision.confidence.label")}: {t(`results.decision.confidence.${decision.confidence}`)}
            </span>
          </div>

          <p className="muted">{t(`results.decision.verdictHint.${decision.verdict}`)}</p>

          {blockers.length > 0 ? (
            <div style={{ display: "grid", gap: "6px" }}>
              <strong>{t("results.decision.blockersTitle")}</strong>
              {blockers.map((blocker, index) => (
                <div className="error" key={`${blocker.code}-${index}`}>
                  {renderReason("blocker", blocker)}
                </div>
              ))}
            </div>
          ) : null}

          {reasons.length > 0 ? (
            <div style={{ display: "grid", gap: "6px" }}>
              <strong>{t("results.decision.reasonsTitle")}</strong>
              <ul style={{ margin: 0, paddingInlineStart: "1.2em", display: "grid", gap: "4px" }}>
                {reasons.map((reason, index) => (
                  <li className="muted" key={`${reason.code}-${index}`}>
                    {renderReason("reason", reason)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="actions" style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <button className="btn ghost" type="button" onClick={() => void copyMarkdown(decision)}>
              {copied ? t("results.decision.export.copied") : t("results.decision.export.copy")}
            </button>
            <button className="btn ghost" type="button" onClick={() => downloadMarkdown(decision)}>
              {t("results.decision.export.download")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
