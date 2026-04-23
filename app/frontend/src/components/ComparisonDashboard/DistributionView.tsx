import { startTransition, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import "../../i18n";
import { compareMultipleProjectsRequest } from "../../lib/api";
import type { MultiProjectComparison } from "../../lib/experiment";

type MonteCarloSimulationResult = {
  num_simulations: number;
  percentiles: Record<string, number>;
  probability_uplift_positive: number;
  probability_uplift_above_threshold: Record<string, number>;
  simulated_uplifts: number[];
};

type ComparisonWithMonteCarlo = MultiProjectComparison & {
  monte_carlo_distribution?: Record<string, MonteCarloSimulationResult>;
};

type DistributionViewProps = {
  comparison: MultiProjectComparison;
};

type HistogramRow = {
  center: number;
  start: number;
  end: number;
  [key: string]: number;
};

const DEFAULT_SIMULATIONS = 10000;
const DEFAULT_THRESHOLD_PERCENT = 3;
const HISTOGRAM_BUCKETS = 50;
const histogramColors = [
  "var(--color-secondary)",
  "var(--color-primary)",
  "var(--color-warning)",
  "var(--color-info)",
  "var(--color-success)"
] as const;
const percentileLevels = ["5", "25", "50", "75", "95"] as const;

function formatPercent(value: number, maximumFractionDigits = 1): string {
  return new Intl.NumberFormat(undefined, {
    style: "percent",
    maximumFractionDigits,
  }).format(value);
}

function formatThresholdPercent(value: number): string {
  return `${Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1)}%`;
}

function buildHistogramData(
  distributions: Record<string, MonteCarloSimulationResult>,
  projectIds: string[],
): HistogramRow[] {
  const values = projectIds.flatMap((projectId) => distributions[projectId]?.simulated_uplifts ?? []);
  if (!values.length) {
    return [];
  }

  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const resolvedMaximum = maximum > minimum ? maximum : minimum + 0.001;
  const bucketWidth = (resolvedMaximum - minimum) / HISTOGRAM_BUCKETS;
  const rows: HistogramRow[] = Array.from({ length: HISTOGRAM_BUCKETS }, (_, index) => {
    const start = minimum + bucketWidth * index;
    const end = start + bucketWidth;
    return {
      center: start + bucketWidth / 2,
      start,
      end,
    };
  });

  for (const projectId of projectIds) {
    const projectValues = distributions[projectId]?.simulated_uplifts ?? [];
    if (!projectValues.length) {
      for (const row of rows) {
        row[projectId] = 0;
      }
      continue;
    }

    const counts = Array.from({ length: HISTOGRAM_BUCKETS }, () => 0);
    for (const value of projectValues) {
      const resolvedIndex = Math.max(
        0,
        Math.min(
          HISTOGRAM_BUCKETS - 1,
          Math.floor((value - minimum) / bucketWidth),
        ),
      );
      counts[resolvedIndex] += 1;
    }

    counts.forEach((count, index) => {
      rows[index][projectId] = count / projectValues.length;
    });
  }

  return rows;
}

function interpolateProbability(
  thresholds: Record<string, number>,
  thresholdPercent: number,
): number {
  const threshold = Math.min(0.1, Math.max(0.01, thresholdPercent / 100));
  const scaledThreshold = threshold * 100;
  if (Number.isInteger(scaledThreshold)) {
    const exactKey = threshold.toFixed(2);
    if (typeof thresholds[exactKey] === "number") {
      return thresholds[exactKey];
    }
  }

  const lower = Math.floor(scaledThreshold) / 100;
  const upper = Math.ceil(scaledThreshold) / 100;
  const lowerKey = lower.toFixed(2);
  const upperKey = upper.toFixed(2);
  const lowerProbability = thresholds[lowerKey] ?? 0;
  const upperProbability = thresholds[upperKey] ?? lowerProbability;

  if (upper <= lower) {
    return lowerProbability;
  }

  const position = (threshold - lower) / (upper - lower);
  return lowerProbability + (upperProbability - lowerProbability) * position;
}

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload?: HistogramRow }>;
}) {
  const row = payload?.[0]?.payload;
  if (!active || !row) {
    return null;
  }

  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-md)",
        background: "var(--color-bg-card)",
        boxShadow: "var(--shadow-sm)",
        padding: 12,
        display: "grid",
        gap: 8,
      }}
    >
      <strong>
        {formatPercent(row.start, 2)} to {formatPercent(row.end, 2)}
      </strong>
      {Object.entries(row)
        .filter(([key]) => !["center", "start", "end"].includes(key))
        .map(([key, value]) => (
          <div key={key} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
            <span>{key}</span>
            <span>{formatPercent(value, 1)}</span>
          </div>
        ))}
    </div>
  );
}

export default function DistributionView({ comparison }: DistributionViewProps) {
  const { t } = useTranslation();
  const panelId = useId();
  const sliderId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [thresholdPercent, setThresholdPercent] = useState(DEFAULT_THRESHOLD_PERCENT);
  const [distribution, setDistribution] = useState<Record<string, MonteCarloSimulationResult> | null>(null);

  const projectIds = comparison.projects.map((project) => project.id);
  const histogramData = distribution ? buildHistogramData(distribution, projectIds) : [];

  async function handleToggle() {
    const nextOpen = !isOpen;
    setIsOpen(nextOpen);
    if (!nextOpen || distribution || isLoading) {
      return;
    }

    setIsLoading(true);
    setLoadError("");
    try {
      const response = await compareMultipleProjectsRequest(projectIds, {
        includeMonteCarlo: true,
        monteCarloSimulations: DEFAULT_SIMULATIONS,
      });
      setDistribution((response as ComparisonWithMonteCarlo).monte_carlo_distribution ?? {});
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t("results.comparison.monteCarlo.loadFailed"));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section
      role="region"
      aria-labelledby="comparison-distribution-heading"
      className="card"
      style={{ display: "grid", gap: 12 }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <div>
          <h3 id="comparison-distribution-heading">{t("results.comparison.monteCarlo.title")}</h3>
          <p className="muted">{t("results.comparison.monteCarlo.subtitle")}</p>
        </div>
        <button
          className="btn secondary"
          type="button"
          aria-controls={panelId}
          aria-expanded={isOpen}
          data-testid="comparison-distribution-toggle"
          onClick={() => void handleToggle()}
        >
          {isOpen ? t("results.comparison.monteCarlo.hideToggle") : t("results.comparison.monteCarlo.showToggle")}
        </button>
      </div>

      {isOpen ? (
        <div id={panelId} style={{ display: "grid", gap: 16 }}>
          {isLoading ? (
            <div role="status" className="muted">
              {t("results.comparison.monteCarlo.loading")}
            </div>
          ) : null}
          {loadError ? <div className="error">{loadError}</div> : null}
          {!isLoading && !loadError && distribution && !Object.keys(distribution).length ? (
            <div className="callout">{t("results.comparison.monteCarlo.empty")}</div>
          ) : null}
          {!isLoading && !loadError && distribution && Object.keys(distribution).length ? (
            <>
              <div className="card" style={{ display: "grid", gap: 12 }}>
                <div style={{ display: "grid", gap: 8 }}>
                  <label htmlFor={sliderId} style={{ fontWeight: 600 }}>
                    {t("results.comparison.monteCarlo.sliderLabel", {
                      threshold: formatThresholdPercent(thresholdPercent),
                    })}
                  </label>
                  <input
                    id={sliderId}
                    type="range"
                    min="1"
                    max="10"
                    step="0.5"
                    value={String(thresholdPercent)}
                    data-testid="comparison-distribution-threshold"
                    onChange={(event) => {
                      const nextValue = Number(event.currentTarget.value);
                      startTransition(() => {
                        setThresholdPercent(nextValue);
                      });
                    }}
                  />
                  <span className="muted">
                    {t("results.comparison.monteCarlo.thresholdHint", {
                      threshold: formatThresholdPercent(thresholdPercent),
                    })}
                  </span>
                </div>
                <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                  {comparison.projects.map((project, index) => {
                    const result = distribution[project.id];
                    if (!result) {
                      return null;
                    }

                    const probability = interpolateProbability(
                      result.probability_uplift_above_threshold,
                      thresholdPercent,
                    );

                    return (
                      <article
                        key={project.id}
                        className="card"
                        data-testid={`comparison-distribution-probability-${project.id}`}
                        style={{ display: "grid", gap: 6 }}
                      >
                        <strong>{project.project_name}</strong>
                        <span
                          className="pill"
                          data-testid={`comparison-distribution-probability-value-${project.id}`}
                          style={{ borderColor: histogramColors[index % histogramColors.length] }}
                        >
                          {t("results.comparison.monteCarlo.probabilityValue", {
                            probability: formatPercent(probability),
                          })}
                        </span>
                        <span className="muted">
                          {t("results.comparison.monteCarlo.positiveProbability", {
                            probability: formatPercent(result.probability_uplift_positive),
                          })}
                        </span>
                      </article>
                    );
                  })}
                </div>
              </div>

              <div className="card" style={{ display: "grid", gap: 12 }}>
                <div style={{ height: 320 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={histogramData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                      <XAxis
                        dataKey="center"
                        tickFormatter={(value: number) => formatPercent(value, 0)}
                        stroke="var(--color-text-secondary)"
                      />
                      <YAxis
                        tickFormatter={(value: number) => formatPercent(value, 0)}
                        stroke="var(--color-text-secondary)"
                      />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend />
                      <ReferenceLine
                        x={thresholdPercent / 100}
                        stroke="var(--color-warning)"
                        strokeDasharray="4 4"
                      />
                      {comparison.projects.map((project, index) => (
                        <Bar
                          key={project.id}
                          dataKey={project.id}
                          name={project.project_name}
                          fill={histogramColors[index % histogramColors.length]}
                          fillOpacity={0.65}
                          isAnimationActive={false}
                        />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div style={{ display: "grid", gap: 12 }}>
                  <strong>{t("results.comparison.monteCarlo.percentileLegend")}</strong>
                  <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
                    {comparison.projects.map((project, index) => {
                      const result = distribution[project.id];
                      if (!result) {
                        return null;
                      }

                      return (
                        <article key={project.id} className="card" style={{ display: "grid", gap: 8 }}>
                          <strong style={{ color: histogramColors[index % histogramColors.length] }}>
                            {project.project_name}
                          </strong>
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            {percentileLevels.map((level) => (
                              <span key={level} className="pill">
                                {t("results.comparison.monteCarlo.percentileValue", {
                                  label: `P${level}`,
                                  value: formatPercent(result.percentiles[level] ?? 0),
                                })}
                              </span>
                            ))}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
