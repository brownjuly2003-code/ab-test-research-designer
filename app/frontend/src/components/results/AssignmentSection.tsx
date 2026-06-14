import { useEffect, useState } from "react";

import { t } from "../../i18n";
import type { ExperimentAssignmentResponse } from "../../lib/api";
import { apiUrl } from "../../lib/experiment";
import { useAnalysisStore } from "../../stores/analysisStore";
import { useProjectStore } from "../../stores/projectStore";
import Icon from "../Icon";
import { buildApiRequestHeaders, getDisplayedAnalysis } from "./resultsShared";

export default function AssignmentSection() {
  const analysisResult = useAnalysisStore((state) => state.analysisResult);
  const resultsProjectId = useAnalysisStore((state) => state.resultsProjectId);
  const selectedHistoryAnalysis = useProjectStore((state) => state.selectedHistoryRun?.analysis ?? null);
  const selectedHistoryProjectId = useProjectStore((state) => state.selectedHistoryRun?.project_id ?? null);
  const activeProjectId = useProjectStore((state) => state.activeProjectId);

  const displayedAnalysis = getDisplayedAnalysis(selectedHistoryAnalysis, analysisResult);
  const experimentId = selectedHistoryProjectId ?? resultsProjectId ?? activeProjectId;
  const variantNames = displayedAnalysis?.report?.experiment_design?.variants.map((variant) => variant.name) ?? [];

  const [userId, setUserId] = useState("");
  const [result, setResult] = useState<ExperimentAssignmentResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setResult(null);
    setError("");
    setLoading(false);
  }, [experimentId]);

  const canAssign = Boolean(experimentId) && userId.trim() !== "" && !loading;

  async function assignUser(): Promise<void> {
    if (!experimentId || userId.trim() === "") {
      return;
    }
    setLoading(true);
    setResult(null);
    setError("");
    try {
      const response = await fetch(apiUrl(`/api/v1/experiments/${encodeURIComponent(experimentId)}/assign`), {
        method: "POST",
        headers: buildApiRequestHeaders(),
        body: JSON.stringify({ user_id: userId.trim() })
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : t("results.assignment.serviceUnavailable");
        throw new Error(detail);
      }
      setResult(body);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : t("results.assignment.serviceUnavailable"));
    } finally {
      setLoading(false);
    }
  }

  if (!displayedAnalysis?.report) {
    return null;
  }

  const assignedVariantName =
    result && result.in_experiment
      ? variantNames[result.variation_index] ?? `#${result.variation_index + 1}`
      : "";

  return (
    <div className="card">
      <h3>{t("results.assignment.title")}</h3>
      <p className="muted">{t("results.assignment.description")}</p>

      {experimentId ? (
        <>
          <div className="field" style={{ marginTop: "var(--space-4)" }}>
            <label htmlFor="assignment-user-id">{t("results.assignment.userIdLabel")}</label>
            <input
              id="assignment-user-id"
              type="text"
              autoComplete="off"
              placeholder={t("results.assignment.userIdPlaceholder")}
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && canAssign) {
                  void assignUser();
                }
              }}
            />
          </div>
          <div className="actions">
            <button className="btn secondary" type="button" onClick={() => void assignUser()} disabled={!canAssign}>
              {loading ? t("results.assignment.assigning") : t("results.assignment.assignButton")}
            </button>
          </div>
        </>
      ) : (
        <div className="callout" style={{ marginTop: "var(--space-4)" }}>
          <Icon name="info" className="icon icon-inline" />
          <span>{t("results.assignment.saveFirst")}</span>
        </div>
      )}

      {error ? <div className="error">{error}</div> : null}

      {result ? (
        <div
          className="callout"
          style={{
            marginTop: "var(--space-4)",
            borderColor: "var(--color-border-soft)",
            background: "var(--color-surface-muted)"
          }}
        >
          <Icon name={result.in_experiment ? "check" : "info"} className="icon icon-inline" />
          <div style={{ display: "grid", gap: "6px" }}>
            {result.in_experiment ? (
              <strong>{t("results.assignment.assignedTo", { variant: assignedVariantName })}</strong>
            ) : (
              <strong>{t("results.assignment.holdout")}</strong>
            )}
            <span className="muted">
              {t("results.assignment.bucketLine", {
                user: result.user_id,
                bucket: result.hash != null ? result.hash.toFixed(4) : "—"
              })}
            </span>
            {result.sticky ? <span className="muted">{t("results.assignment.stickyNote")}</span> : null}
            <span className="muted">{t("results.assignment.growthbookNote")}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
