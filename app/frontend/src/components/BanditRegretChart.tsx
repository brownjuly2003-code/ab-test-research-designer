import type { CSSProperties } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import type { BanditRegretPoint } from "../lib/api";

export interface BanditRegretChartProps {
  curve: BanditRegretPoint[];
  banditLabel: string;
  uniformLabel: string;
  ariaLabel: string;
}

const tooltipStyle: CSSProperties = {
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  background: "var(--color-bg-card)",
  boxShadow: "var(--shadow-sm)",
  padding: "12px",
  minWidth: "220px"
};

function formatRegret(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, "");
}

function RegretTooltip({
  active,
  payload,
  label,
  banditLabel,
  uniformLabel
}: {
  active?: boolean;
  payload?: Array<{ payload?: BanditRegretPoint }>;
  label?: number | string;
  banditLabel: string;
  uniformLabel: string;
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
      <div style={{ fontWeight: 700 }}>Step {label}</div>
      <div style={{ marginTop: "8px" }}>{banditLabel}: {formatRegret(row.bandit_cumulative_regret)}</div>
      <div>{uniformLabel}: {formatRegret(row.uniform_cumulative_regret)}</div>
    </div>
  );
}

export default function BanditRegretChart({
  curve,
  banditLabel,
  uniformLabel,
  ariaLabel
}: BanditRegretChartProps) {
  const maxStep = curve.length > 0 ? curve[curve.length - 1]?.step ?? 1 : 1;

  return (
    <div role="img" aria-label={ariaLabel} style={{ height: 260, width: "100%" }}>
      {/* initialDimension height silences recharts' benign first-render width(-1)/height(-1) dev
          warning; width stays -1 so it is still measured (no first-frame resize). */}
      <ResponsiveContainer width="100%" height="100%" minWidth={320} initialDimension={{ width: -1, height: 260 }}>
        <LineChart data={curve} margin={{ top: 8, right: 20, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="step"
            type="number"
            allowDecimals={false}
            domain={[1, Math.max(1, maxStep)]}
            stroke="var(--color-text-secondary)"
          />
          <YAxis
            tickFormatter={(value: number) => formatRegret(value)}
            stroke="var(--color-text-secondary)"
            width={56}
          />
          <Tooltip content={<RegretTooltip banditLabel={banditLabel} uniformLabel={uniformLabel} />} />
          <Legend />
          <Line
            type="monotone"
            dataKey="uniform_cumulative_regret"
            name={uniformLabel}
            stroke="var(--color-text-secondary)"
            strokeDasharray="6 4"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="bandit_cumulative_regret"
            name={banditLabel}
            stroke="var(--color-primary)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
