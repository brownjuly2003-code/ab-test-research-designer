import type { CSSProperties } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

export interface PosteriorPlotProps {
  posteriorMean: number;
  posteriorStd: number;
  credibilityInterval: { lower: number; upper: number; level: number };
  priorMean?: number;
  priorStd?: number;
  metricType: "binary" | "continuous";
}

type PosteriorPoint = {
  x: number;
  posterior: number;
  interval: number | null;
  prior: number | null;
};

const tooltipStyle: CSSProperties = {
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  background: "var(--color-bg-card)",
  boxShadow: "var(--shadow-sm)",
  padding: "12px",
  minWidth: "220px"
};

function formatChartValue(value: number, metricType: "binary" | "continuous"): string {
  const digits = metricType === "binary" ? 4 : Math.abs(value) >= 100 ? 0 : 2;
  return value.toFixed(digits).replace(/\.?0+$/, "");
}

function formatDensity(value: number): string {
  if (!Number.isFinite(value)) {
    return "0";
  }

  if (value >= 1) {
    return value.toFixed(2);
  }

  return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function formatLevel(level: number): string {
  return `${Number((level * 100).toFixed(2)).toString()}%`;
}

function normalPdf(x: number, mean: number, std: number): number {
  const variance = std ** 2;
  return (1 / Math.sqrt(2 * Math.PI * variance)) * Math.exp(-((x - mean) ** 2) / (2 * variance));
}

function erf(value: number): number {
  const sign = value < 0 ? -1 : 1;
  const absolute = Math.abs(value);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const t = 1 / (1 + p * absolute);
  const polynomial = (((((a5 * t) + a4) * t) + a3) * t + a2) * t + a1;
  return sign * (1 - polynomial * t * Math.exp(-(absolute ** 2)));
}

function normalCdf(x: number, mean: number, std: number): number {
  return 0.5 * (1 + erf((x - mean) / (std * Math.SQRT2)));
}

function buildPosteriorData({
  posteriorMean,
  posteriorStd,
  credibilityInterval,
  priorMean,
  priorStd
}: PosteriorPlotProps): PosteriorPoint[] {
  const minX = posteriorMean - 4 * posteriorStd;
  const maxX = posteriorMean + 4 * posteriorStd;
  const step = (maxX - minX) / 199;
  const hasPrior = typeof priorMean === "number" && typeof priorStd === "number" && priorStd > 0;

  return Array.from({ length: 200 }, (_, index) => {
    const x = minX + step * index;
    const posterior = normalPdf(x, posteriorMean, posteriorStd);
    return {
      x,
      posterior,
      interval: x >= credibilityInterval.lower && x <= credibilityInterval.upper ? posterior : null,
      prior: hasPrior ? normalPdf(x, priorMean, priorStd) : null
    };
  });
}

function PosteriorTooltip({
  active,
  payload,
  label,
  posteriorMean,
  posteriorStd,
  metricType
}: {
  active?: boolean;
  payload?: Array<{ payload?: PosteriorPoint }>;
  label?: number | string;
  posteriorMean: number;
  posteriorStd: number;
  metricType: "binary" | "continuous";
}) {
  if (!active || !payload?.length || typeof label !== "number") {
    return null;
  }

  const density = payload[0]?.payload?.posterior ?? normalPdf(label, posteriorMean, posteriorStd);
  const cumulativeProbability = normalCdf(label, posteriorMean, posteriorStd);

  return (
    <div style={tooltipStyle}>
      <div style={{ fontWeight: 700 }}>
        x={formatChartValue(label, metricType)}
      </div>
      <div style={{ marginTop: "8px" }}>
        P(theta &le; {formatChartValue(label, metricType)} | data) = {cumulativeProbability.toFixed(2)}
      </div>
      <div className="muted" style={{ marginTop: "6px" }}>
        density = {formatDensity(density)}
      </div>
    </div>
  );
}

export default function PosteriorPlot({
  posteriorMean,
  posteriorStd,
  credibilityInterval,
  priorMean,
  priorStd,
  metricType
}: PosteriorPlotProps) {
  const sanitizedStd = Number.isFinite(posteriorStd) && posteriorStd > 0 ? posteriorStd : Number.EPSILON;
  const data = buildPosteriorData({
    posteriorMean,
    posteriorStd: sanitizedStd,
    credibilityInterval,
    priorMean,
    priorStd,
    metricType
  });
  const ariaLabel =
    `Bayesian posterior distribution with ${formatLevel(credibilityInterval.level)} credibility interval ` +
    `from ${formatChartValue(credibilityInterval.lower, metricType)} to ${formatChartValue(credibilityInterval.upper, metricType)}`;

  return (
    <div role="img" aria-label={ariaLabel} style={{ height: 260, width: "100%" }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={320}>
        <ComposedChart data={data} margin={{ top: 8, right: 20, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="x"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(value: number) => formatChartValue(value, metricType)}
            stroke="var(--color-text-secondary)"
          />
          <YAxis
            tickFormatter={(value: number) => formatDensity(value)}
            stroke="var(--color-text-secondary)"
            width={56}
          />
          <Tooltip
            content={(
              <PosteriorTooltip
                posteriorMean={posteriorMean}
                posteriorStd={sanitizedStd}
                metricType={metricType}
              />
            )}
          />
          <Area
            type="monotone"
            dataKey="posterior"
            stroke="var(--color-secondary)"
            fill="var(--color-secondary)"
            fillOpacity={0.18}
            strokeWidth={2}
            isAnimationActive={false}
            dot={false}
          />
          <Area
            type="monotone"
            dataKey="interval"
            stroke="var(--color-primary)"
            fill="var(--color-primary)"
            fillOpacity={0.38}
            strokeWidth={0}
            isAnimationActive={false}
            dot={false}
            connectNulls={false}
          />
          {typeof priorMean === "number" && typeof priorStd === "number" && priorStd > 0 ? (
            <Line
              type="monotone"
              dataKey="prior"
              stroke="var(--color-text-secondary)"
              strokeDasharray="6 4"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          ) : null}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
