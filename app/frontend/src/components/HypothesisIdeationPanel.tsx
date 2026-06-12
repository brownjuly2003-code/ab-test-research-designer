import { useState } from "react";

import { t } from "../i18n";
import { requestHypotheses, type HypothesisCandidate } from "../lib/api";
import type { FullPayload } from "../lib/experiment";
import Spinner from "./Spinner";

type HypothesisIdeationPanelProps = {
  form: FullPayload;
  onApply: (candidate: HypothesisCandidate) => void;
  disabled?: boolean;
};

export default function HypothesisIdeationPanel({ form, onApply, disabled = false }: HypothesisIdeationPanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<HypothesisCandidate[]>([]);
  const [unavailable, setUnavailable] = useState(false);

  async function generate() {
    setLoading(true);
    setError(null);
    setUnavailable(false);
    try {
      const result = await requestHypotheses({
        project_context: form.project,
        business_problem: form.hypothesis.business_problem || form.project.project_description || "",
        metrics: {
          metric_type: form.metrics.metric_type,
          baseline_value: form.metrics.baseline_value,
          primary_metric_name: form.metrics.primary_metric_name
        },
        setup: {
          expected_daily_traffic: form.setup.expected_daily_traffic,
          audience_share_in_test: form.setup.audience_share_in_test
        },
        count: 3
      });
      if (!result.available) {
        setUnavailable(true);
        setCandidates([]);
        return;
      }
      setCandidates(result.hypotheses);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("hypothesisIdeation.error"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="field" style={{ gridColumn: "1 / -1" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px" }}>
        <div>
          <strong>{t("hypothesisIdeation.title")}</strong>
          <p className="muted" style={{ margin: "4px 0 0" }}>{t("hypothesisIdeation.description")}</p>
        </div>
        <button type="button" className="btn secondary" onClick={() => void generate()} disabled={disabled || loading}>
          {loading ? <Spinner /> : null}
          {loading ? t("hypothesisIdeation.generating") : t("hypothesisIdeation.generate")}
        </button>
      </div>

      {error ? <span className="live-preview-message live-preview-error">{error}</span> : null}
      {unavailable ? <span className="muted">{t("hypothesisIdeation.unavailable")}</span> : null}

      {candidates.length > 0 ? (
        <ul className="list" style={{ display: "grid", gap: "10px", marginTop: "8px" }} aria-live="polite">
          {candidates.map((candidate, index) => (
            <li
              key={`${candidate.change}-${index}`}
              style={{
                display: "grid",
                gap: "6px",
                padding: "12px",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border-soft)",
                background: "var(--color-surface-elevated)"
              }}
            >
              <strong>{candidate.change}</strong>
              {candidate.rationale ? <span className="muted">{candidate.rationale}</span> : null}
              <span className="muted">
                {t("hypothesisIdeation.metricLine", {
                  metric: candidate.primary_metric || "-",
                  direction: t(`hypothesisIdeation.direction.${candidate.expected_direction}`)
                })}
              </span>
              <button
                type="button"
                className="btn ghost"
                style={{ justifySelf: "start" }}
                onClick={() => onApply(candidate)}
                disabled={disabled}
              >
                {t("hypothesisIdeation.apply")}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
