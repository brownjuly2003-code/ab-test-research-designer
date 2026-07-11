import { t } from "../../../i18n";
import type { MultipleTestingResponse } from "../../../lib/api";
import { formatPValue } from "../../../lib/formatNumber";
import Icon from "../../Icon";

export type MetricRow = { label: string; pValue: string };

type MultipleTestingViewProps = {
  metrics: MetricRow[];
  method: "bh" | "holm";
  level: string;
  onChangeMetric: (index: number, field: "label" | "pValue", value: string) => void;
  onAddMetric: () => void;
  onRemoveMetric: (index: number) => void;
  onChangeMethod: (value: "bh" | "holm") => void;
  onChangeLevel: (value: string) => void;
  onRun: () => void;
  canRun: boolean;
  loading: boolean;
  error: string;
  result: MultipleTestingResponse | null;
};

const cellStyle = { padding: "8px 12px", borderBottom: "1px solid var(--color-border-soft)", textAlign: "left" as const };

export default function MultipleTestingView({
  metrics,
  method,
  level,
  onChangeMetric,
  onAddMetric,
  onRemoveMetric,
  onChangeMethod,
  onChangeLevel,
  onRun,
  canRun,
  loading,
  error,
  result
}: MultipleTestingViewProps) {
  return (
    <div className="card">
      <h3>{t("results.multipleTesting.title")}</h3>
      <p className="muted">{t("results.multipleTesting.description")}</p>

      <div style={{ display: "grid", gap: "8px", marginTop: "var(--space-3)" }}>
        {metrics.map((metric, index) => (
          <div key={index} style={{ display: "grid", gridTemplateColumns: "1fr 140px auto", gap: "8px", alignItems: "end" }}>
            <div className="field">
              {index === 0 ? <label htmlFor={`mt-label-${index}`}>{t("results.multipleTesting.columns.metric")}</label> : null}
              <input id={`mt-label-${index}`} type="text" placeholder={t("results.multipleTesting.metricLabelPlaceholder")} value={metric.label} onChange={(event) => onChangeMetric(index, "label", event.target.value)} />
            </div>
            <div className="field">
              {index === 0 ? <label htmlFor={`mt-pvalue-${index}`}>p-value</label> : null}
              <input id={`mt-pvalue-${index}`} type="number" min="0" max="1" step="0.0001" inputMode="decimal" placeholder={t("results.multipleTesting.pValuePlaceholder")} value={metric.pValue} onChange={(event) => onChangeMetric(index, "pValue", event.target.value)} />
            </div>
            <button className="btn ghost" type="button" onClick={() => onRemoveMetric(index)} disabled={metrics.length <= 1} aria-label={t("results.multipleTesting.removeMetric")}>
              <Icon name="trash" className="icon icon-inline" />
            </button>
          </div>
        ))}
      </div>

      <div className="actions" style={{ marginTop: "var(--space-2)" }}>
        <button className="btn ghost" type="button" onClick={onAddMetric}>
          <Icon name="plus" className="icon icon-inline" />
          {t("results.multipleTesting.addMetric")}
        </button>
      </div>

      <div className="two-col" style={{ marginTop: "var(--space-3)" }}>
        <div className="field">
          <label htmlFor="mt-method">{t("results.multipleTesting.methodLabel")}</label>
          <select id="mt-method" value={method} onChange={(event) => onChangeMethod(event.target.value === "holm" ? "holm" : "bh")}>
            <option value="bh">{t("results.multipleTesting.method.bh")}</option>
            <option value="holm">{t("results.multipleTesting.method.holm")}</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="mt-level">{method === "bh" ? t("results.multipleTesting.levelLabelFdr") : t("results.multipleTesting.levelLabelFwer")}</label>
          <input id="mt-level" type="number" min="0.001" max="0.5" step="0.01" inputMode="decimal" value={level} onChange={(event) => onChangeLevel(event.target.value)} />
        </div>
      </div>

      <div className="actions" style={{ marginTop: "var(--space-3)" }}>
        <button className="btn secondary" type="button" onClick={onRun} disabled={!canRun || loading}>
          {loading ? t("results.multipleTesting.running") : t("results.multipleTesting.runButton")}
        </button>
        {!canRun ? <span className="muted">{t("results.multipleTesting.needMetrics")}</span> : null}
      </div>

      {error ? <div className="error">{error}</div> : null}

      {result ? (
        <div style={{ marginTop: "var(--space-4)" }}>
          <div className="callout" style={{ background: "var(--color-surface-muted)", borderColor: "var(--color-border-soft)" }}>
            <Icon name="info" className="icon icon-inline" />
            <div style={{ display: "grid", gap: "4px" }}>
              <strong>{t("results.multipleTesting.summary", { rejected: String(result.num_rejected), total: String(result.num_tests), level: result.level.toFixed(3) })}</strong>
              {result.num_rejected > 0 ? <span>{t("results.multipleTesting.criticalValue", { value: result.critical_value.toFixed(4) })}</span> : null}
            </div>
          </div>
          <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={cellStyle}>{t("results.multipleTesting.columns.metric")}</th>
                  <th style={cellStyle}>p-value</th>
                  <th style={cellStyle}>{t("results.multipleTesting.columns.adjusted")}</th>
                  <th style={cellStyle}>{t("results.multipleTesting.columns.decision")}</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((metric, index) => (
                  <tr key={`${metric.label}-${index}`} style={metric.rejected ? { fontWeight: 600 } : undefined}>
                    <td style={cellStyle}>{metric.label}</td>
                    <td style={cellStyle}>{formatPValue(metric.p_value)}</td>
                    <td style={cellStyle}>{formatPValue(metric.adjusted_p_value)}</td>
                    <td style={cellStyle}>
                      {metric.rejected ? (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", color: "var(--color-success)" }}>
                          <Icon name="check" className="icon icon-inline" />
                          {t("results.multipleTesting.decision.significant")}
                        </span>
                      ) : (
                        <span className="muted">{t("results.multipleTesting.decision.notSignificant")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
