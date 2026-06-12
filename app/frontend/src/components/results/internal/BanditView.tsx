import { Suspense, lazy } from "react";

import { t } from "../../../i18n";
import type { BanditSimulationResponse } from "../../../lib/api";
import Icon from "../../Icon";
import Skeleton from "../../Skeleton";

const BanditRegretChart = lazy(() => import("../../BanditRegretChart"));

type BanditViewProps = {
  variantNames: string[];
  armRates: string[];
  onChangeRate: (index: number, value: string) => void;
  horizon: string;
  onChangeHorizon: (value: string) => void;
  onRun: () => void;
  canRun: boolean;
  loading: boolean;
  error: string;
  result: BanditSimulationResponse | null;
  unavailable: boolean;
};

function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

export default function BanditView({
  variantNames,
  armRates,
  onChangeRate,
  horizon,
  onChangeHorizon,
  onRun,
  canRun,
  loading,
  error,
  result,
  unavailable
}: BanditViewProps) {
  if (unavailable) {
    return (
      <div className="card">
        <h3>{t("results.bandit.title")}</h3>
        <p className="muted">{t("results.bandit.description")}</p>
        <div className="callout" style={{ marginTop: "var(--space-4)" }}>
          <Icon name="info" className="icon icon-inline" />
          <span>{t("results.bandit.binaryOnly")}</span>
        </div>
      </div>
    );
  }

  const regretReduction =
    result && result.final_uniform_regret > 0
      ? (result.final_uniform_regret - result.final_bandit_regret) / result.final_uniform_regret
      : null;
  const bestVariant = result ? variantNames[result.best_arm_index] ?? `#${result.best_arm_index + 1}` : "";

  return (
    <div className="card">
      <h3>{t("results.bandit.title")}</h3>
      <p className="muted">{t("results.bandit.description")}</p>
      <div className="two-col">
        {variantNames.map((name, index) => (
          <div key={name} className="field">
            <label htmlFor={`bandit-rate-${index}`}>{t("results.bandit.rateLabel", { variant: name })}</label>
            <input
              id={`bandit-rate-${index}`}
              type="number"
              min="0"
              max="100"
              step="0.1"
              inputMode="decimal"
              placeholder={t("results.bandit.ratePlaceholder")}
              value={armRates[index] ?? ""}
              onChange={(event) => onChangeRate(index, event.target.value)}
            />
          </div>
        ))}
        <div className="field">
          <label htmlFor="bandit-horizon">{t("results.bandit.horizonLabel")}</label>
          <input
            id="bandit-horizon"
            type="number"
            min="10"
            max="5000"
            step="50"
            inputMode="numeric"
            value={horizon}
            onChange={(event) => onChangeHorizon(event.target.value)}
          />
        </div>
      </div>
      <div className="actions">
        <button className="btn secondary" type="button" onClick={onRun} disabled={!canRun || loading}>
          {loading ? t("results.bandit.simulating") : t("results.bandit.simulateButton")}
        </button>
      </div>
      {error ? <div className="error">{error}</div> : null}
      {result ? (
        <div style={{ display: "grid", gap: "var(--space-4)", marginTop: "var(--space-4)" }}>
          <div
            className="callout"
            style={{ borderColor: "var(--color-border-soft)", background: "var(--color-surface-muted)" }}
          >
            <Icon name="check" className="icon icon-inline" />
            <div style={{ display: "grid", gap: "6px" }}>
              <strong>{t("results.bandit.convergesOn", { variant: bestVariant })}</strong>
              <span>{t("results.bandit.probabilityBest", { percent: formatPercent(result.probability_best_arm) })}</span>
              {regretReduction !== null ? (
                <span>{t("results.bandit.regretReduction", { percent: formatPercent(regretReduction) })}</span>
              ) : null}
            </div>
          </div>
          <div>
            <strong>{t("results.bandit.allocationTitle")}</strong>
            <ul style={{ listStyle: "none", padding: 0, margin: "var(--space-2) 0 0", display: "grid", gap: "6px" }}>
              {variantNames.map((name, index) => (
                <li key={name} style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-4)" }}>
                  <span style={{ fontWeight: index === result.best_arm_index ? 700 : 400 }}>{name}</span>
                  <span>{formatPercent(result.arm_allocation[index] ?? 0)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <strong>{t("results.bandit.regretTitle")}</strong>
            <Suspense fallback={<Skeleton height="260px" />}>
              <BanditRegretChart
                curve={result.regret_curve}
                banditLabel={t("results.bandit.banditLabel")}
                uniformLabel={t("results.bandit.uniformLabel")}
                ariaLabel={t("results.bandit.chartAria", { steps: String(result.horizon) })}
              />
            </Suspense>
          </div>
        </div>
      ) : null}
    </div>
  );
}
