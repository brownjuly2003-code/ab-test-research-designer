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

export interface SequentialBoundaryChartProps {
  boundaries: Array<{
    look: number;
    alpha_spent: number;
    upper_boundary_z: number;
    lower_boundary_z: number;
    sample_size_cumulative: number;
  }>;
  currentLook?: number;
}

const tooltipStyle: CSSProperties = {
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  background: "var(--color-bg-card)",
  boxShadow: "var(--shadow-sm)",
  padding: "12px",
  minWidth: "220px"
};

function SequentialTooltip({
  active,
  payload,
  label
}: {
  active?: boolean;
  payload?: Array<{ payload?: SequentialBoundaryChartProps["boundaries"][number] }>;
  label?: number | string;
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
      <div style={{ fontWeight: 700 }}>Look {label}</div>
      <div style={{ marginTop: "8px" }}>Upper boundary: {row.upper_boundary_z.toFixed(2)} z</div>
      <div>Lower boundary: {row.lower_boundary_z.toFixed(2)} z</div>
      <div>Alpha spent: {row.alpha_spent.toFixed(4)}</div>
      {row.sample_size_cumulative > 0 ? <div>Cumulative sample size: {row.sample_size_cumulative.toLocaleString()}</div> : null}
    </div>
  );
}

export default function SequentialBoundaryChart({
  boundaries,
  currentLook
}: SequentialBoundaryChartProps) {
  return (
    <div
      role="img"
      aria-label={`O'Brien-Fleming sequential boundaries across ${boundaries.length} looks`}
      style={{ height: 240, width: "100%" }}
    >
      <ResponsiveContainer width="100%" height="100%" minWidth={320}>
        <LineChart data={boundaries} margin={{ top: 8, right: 20, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="look"
            type="number"
            allowDecimals={false}
            domain={[1, Math.max(1, boundaries.length)]}
            stroke="var(--color-text-secondary)"
          />
          <YAxis stroke="var(--color-text-secondary)" width={52} />
          <Tooltip content={<SequentialTooltip />} />
          <ReferenceLine y={1.96} stroke="var(--color-text-secondary)" strokeDasharray="4 4" />
          <ReferenceLine y={-1.96} stroke="var(--color-text-secondary)" strokeDasharray="4 4" />
          {typeof currentLook === "number" ? (
            <ReferenceLine x={currentLook} stroke="var(--color-warning)" strokeDasharray="4 4" />
          ) : null}
          <Line
            type="monotone"
            dataKey="upper_boundary_z"
            stroke="var(--color-danger)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="lower_boundary_z"
            stroke="var(--color-danger)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
