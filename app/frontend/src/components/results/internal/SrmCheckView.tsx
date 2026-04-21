import { t } from "../../../i18n";
import type { SrmCheckResponse } from "../../../lib/api";
import Icon from "../../Icon";

type SrmCheckViewProps = {
  variantNames: string[];
  srmCounts: string[];
  onChangeCount: (index: number, value: string) => void;
  onRun: () => void;
  canRunSrm: boolean;
  srmLoading: boolean;
  srmError: string;
  srmResult: SrmCheckResponse | null;
};

export default function SrmCheckView({
  variantNames,
  srmCounts,
  onChangeCount,
  onRun,
  canRunSrm,
  srmLoading,
  srmError,
  srmResult
}: SrmCheckViewProps) {
  return (
    <div className="card">
      <h3>{t("results.srmCheck.title")}</h3>
      <p className="muted">{t("results.srmCheck.description")}</p>
      <div className="two-col">
        {variantNames.map((name, index) => (
          <div key={name} className="field">
            <label htmlFor={`srm-count-${index}`}>{name}</label>
            <input id={`srm-count-${index}`} type="number" min="0" step="1" inputMode="numeric" placeholder={t("results.srmCheck.actualUsersPlaceholder")} value={srmCounts[index] ?? ""} onChange={(event) => onChangeCount(index, event.target.value)} />
          </div>
        ))}
      </div>
      <div className="actions"><button className="btn secondary" type="button" onClick={onRun} disabled={!canRunSrm || srmLoading}>{srmLoading ? t("results.srmCheck.checking") : t("results.srmCheck.checkButton")}</button></div>
      {srmError ? <div className="error">{srmError}</div> : null}
      {srmResult ? (
        <div className="callout" style={{ marginTop: "var(--space-4)", borderColor: srmResult.is_srm ? "var(--color-danger-ring)" : "var(--color-border-soft)", background: srmResult.is_srm ? "var(--color-danger-light)" : "var(--color-surface-muted)" }}>
          <Icon name={srmResult.is_srm ? "warning" : "check"} className="icon icon-inline" />
          <div style={{ display: "grid", gap: "6px" }}>
            <strong>{srmResult.is_srm ? t("results.srmCheck.detected") : t("results.srmCheck.notDetected")}</strong>
            <span>{srmResult.verdict}</span>
            <span>{t("results.srmCheck.chiSquare", { chiSquare: String(srmResult.chi_square), pValue: srmResult.p_value.toFixed(6) })}</span>
            {srmResult.is_srm ? <span>{t("results.srmCheck.expectedObserved", { expected: srmResult.expected_counts.map((count) => Math.round(count)).join(", "), observed: srmResult.observed_counts.join(", ") })}</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
