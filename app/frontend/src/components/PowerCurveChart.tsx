import type { CSSProperties } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import type { SensitivityCell } from "../lib/generated/api-contract";

type PowerCurveChartProps = {
  cells: SensitivityCell[];
  currentMde: number;
  currentPower: number;
  metricType: "binary" | "continuous";
};

type ChartRow = {
  mde: number;
  [key: string]: number;
};

const powerColors = [
  "var(--color-secondary)",
  "var(--color-primary)",
  "var(--color-warning)",
  "var(--color-info)"
] as const;

const tooltipStyle: CSSProperties = {
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  background: "var(--color-bg-card)",
  boxShadow: "var(--shadow-sm)",
  padding: "12px",
  minWidth: "220px"
};

const tooltipListStyle: CSSProperties = {
  display: "grid",
  gap: "6px",
  marginTop: "10px"
};

const tooltipRowStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  fontSize: "var(--font-size-sm)"
};

function buildPowerKey(power: number): string {
  return `power_${power.toFixed(2).replace(".", "_")}`;
}

function buildSampleKey(power: number): string {
  return `sample_${power.toFixed(2).replace(".", "_")}`;
}

function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: value >= 100 ? 0 : 2
  }).format(value);
}

function formatMde(value: number, metricType: "binary" | "continuous"): string {
  const suffix = metricType === "binary" ? "%" : "";
  return `${formatCompactNumber(value)}${suffix}`;
}

function buildChartData(cells: SensitivityCell[]): { data: ChartRow[]; powerLevels: number[] } {
  const rows = new Map<number, ChartRow>();
  const powerLevels = Array.from(new Set(cells.map((cell) => cell.power))).sort((left, right) => left - right);

  for (const cell of cells) {
    const existing = rows.get(cell.mde) ?? { mde: cell.mde };
    existing[buildPowerKey(cell.power)] = cell.power;
    existing[buildSampleKey(cell.power)] = cell.sample_size_per_variant;
    rows.set(cell.mde, existing);
  }

  return {
    data: Array.from(rows.values()).sort((left, right) => left.mde - right.mde),
    powerLevels
  };
}

function CustomTooltip({
  active,
  payload,
  label,
  powerLevels,
  metricType
}: {
  active?: boolean;
  payload?: Array<{ payload?: ChartRow }>;
  label?: number | string;
  powerLevels: number[];
  metricType: "binary" | "continuous";
}) {
  if (!active || !payload?.length || typeof label !== "number") {
    return null;
  }

  const row = payload[0]?.payload;
  if (!row) {
    return null;
  }

  return (
    <div style={tooltipStyle}>
      <div style={{ fontWeight: 700 }}>MDE: {formatMde(label, metricType)}</div>
      <div style={tooltipListStyle}>
        {powerLevels.map((power, index) => {
          const sampleSize = row[buildSampleKey(power)];
          if (typeof sampleSize !== "number") {
            return null;
          }

          return (
            <div key={power} style={tooltipRowStyle}>
              <span style={{ color: powerColors[index % powerColors.length] }}>
                {(power * 100).toFixed(0)}% power
              </span>
              <span>{formatCompactNumber(sampleSize)} users / variant</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function PowerCurveChart({
  cells,
  currentMde,
  currentPower,
  metricType
}: PowerCurveChartProps) {
  const { data, powerLevels } = buildChartData(cells);

  return (
    <div style={{ height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="mde"
            tickFormatter={(value: number) => formatMde(value, metricType)}
            stroke="var(--color-text-secondary)"
          />
          <YAxis
            tickFormatter={(value: number) => `${(value * 100).toFixed(0)}%`}
            domain={[0.5, 1]}
            stroke="var(--color-text-secondary)"
          />
          <Tooltip
            content={
              <CustomTooltip
                powerLevels={powerLevels}
                metricType={metricType}
              />
            }
          />
          <ReferenceLine
            y={0.8}
            strokeDasharray="4 4"
            stroke="var(--color-warning)"
            label={{ value: "80% target", fill: "var(--color-text-secondary)", fontSize: 12 }}
          />
          <ReferenceLine x={currentMde} stroke="var(--color-primary)" strokeDasharray="4 4" />
          <ReferenceLine y={currentPower} stroke="var(--color-border-strong)" strokeDasharray="2 6" />
          {powerLevels.map((power, index) => (
            <Line
              key={power}
              type="monotone"
              dataKey={buildPowerKey(power)}
              stroke={powerColors[index % powerColors.length]}
              dot={false}
              strokeWidth={2}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
