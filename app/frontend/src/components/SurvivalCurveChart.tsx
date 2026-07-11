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

// One row of the merged, carry-forward Kaplan–Meier step series shared by the two arms: at each
// distinct event time the last-known survival S(t) for each arm (so recharts can draw both step
// curves from a single dataset with ``type="stepAfter"``).
export type SurvivalSeriesPoint = {
  time: number;
  control: number;
  treatment: number;
};

export interface SurvivalCurveChartProps {
  series: SurvivalSeriesPoint[];
  controlLabel: string;
  treatmentLabel: string;
  ariaLabel: string;
  timeAxisLabel: string;
  survivalAxisLabel: string;
}

export default function SurvivalCurveChart({
  series,
  controlLabel,
  treatmentLabel,
  ariaLabel,
  timeAxisLabel,
  survivalAxisLabel
}: SurvivalCurveChartProps) {
  const maxTime = series.reduce((max, point) => (point.time > max ? point.time : max), 0);
  return (
    <div role="img" aria-label={ariaLabel} style={{ height: 280, width: "100%" }}>
      {/* initialDimension height silences recharts' benign first-render width(-1)/height(-1) dev
          warning; width stays -1 so it is still measured (no first-frame resize). */}
      <ResponsiveContainer width="100%" height="100%" minWidth={320} initialDimension={{ width: -1, height: 280 }}>
        <LineChart data={series} margin={{ top: 8, right: 20, bottom: 24, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="time"
            type="number"
            domain={[0, Math.max(1, maxTime)]}
            stroke="var(--color-text-secondary)"
            label={{ value: timeAxisLabel, position: "insideBottom", offset: -12, fill: "var(--color-text-secondary)" }}
          />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tickFormatter={(value: number) => value.toFixed(2)}
            stroke="var(--color-text-secondary)"
            width={52}
            label={{ value: survivalAxisLabel, angle: -90, position: "insideLeft", fill: "var(--color-text-secondary)" }}
          />
          <Tooltip formatter={(value) => (typeof value === "number" ? value.toFixed(4) : String(value))} />
          <Legend />
          <Line
            type="stepAfter"
            dataKey="control"
            name={controlLabel}
            stroke="var(--color-text-secondary)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="stepAfter"
            dataKey="treatment"
            name={treatmentLabel}
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
