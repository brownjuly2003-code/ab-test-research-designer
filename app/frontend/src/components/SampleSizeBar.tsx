import type { CSSProperties } from "react";

type SampleSizeBarProps = {
  sampleSizePerVariant: number;
  variants: number;
  variantNames?: string[];
  trafficSplit?: number[];
};

const variantColors = [
  "var(--color-primary)",
  "var(--color-secondary)",
  "var(--color-warning)",
  "var(--color-info)",
  "var(--color-success)"
] as const;

const barShellStyle: CSSProperties = {
  display: "grid",
  gap: "12px"
};

const barStyle: CSSProperties = {
  display: "flex",
  minHeight: "18px",
  overflow: "hidden",
  borderRadius: "999px",
  background: "var(--color-surface-subtle)",
  border: "1px solid var(--color-border)"
};

const labelsStyle: CSSProperties = {
  display: "grid",
  gap: "8px",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))"
};

const labelStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  fontSize: "var(--font-size-sm)",
  fontVariantNumeric: "tabular-nums"
};

const swatchStyle: CSSProperties = {
  width: "10px",
  height: "10px",
  borderRadius: "999px",
  flexShrink: 0
};

function formatSample(value: number): string {
  return new Intl.NumberFormat().format(value);
}

export default function SampleSizeBar({
  sampleSizePerVariant,
  variants,
  variantNames,
  trafficSplit
}: SampleSizeBarProps) {
  const weights = trafficSplit && trafficSplit.length === variants ? trafficSplit : Array.from({ length: variants }, () => 1);
  const totalWeight = weights.reduce((sum, value) => sum + value, 0);

  return (
    <div style={barShellStyle}>
      <div style={{ color: "var(--color-text-secondary)", fontSize: "var(--font-size-sm)" }}>
        Total sample: {formatSample(sampleSizePerVariant * variants)} users
      </div>
      <div style={barStyle}>
        {Array.from({ length: variants }, (_, index) => {
          const name = variantNames?.[index] ?? (index === 0 ? "Control" : `Treatment ${index}`);
          const weight = weights[index] ?? 1;
          const share = totalWeight > 0 ? Math.round((weight / totalWeight) * 100) : 0;
          return (
            <div
              key={name}
              style={{
                flex: weight,
                background: variantColors[index % variantColors.length]
              }}
              title={`${name}: ${formatSample(sampleSizePerVariant)} users (${share}% traffic)`}
            />
          );
        })}
      </div>
      <div style={labelsStyle}>
        {Array.from({ length: variants }, (_, index) => {
          const name = variantNames?.[index] ?? (index === 0 ? "Control" : `Treatment ${index}`);
          const weight = weights[index] ?? 1;
          const share = totalWeight > 0 ? Math.round((weight / totalWeight) * 100) : 0;
          return (
            <div key={name} style={labelStyle}>
              <span
                style={{
                  ...swatchStyle,
                  background: variantColors[index % variantColors.length]
                }}
              />
              <span>
                {name}: {formatSample(sampleSizePerVariant)} users ({share}% traffic)
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
