type ForestPlotProps = {
  effect: number;
  ciLower: number;
  ciUpper: number;
  metricType: "binary" | "continuous";
};

function formatValue(value: number, metricType: "binary" | "continuous"): string {
  const suffix = metricType === "binary" ? " pp" : "";
  const precision = metricType === "binary" ? 2 : 3;
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(precision)}${suffix}`;
}

function position(value: number, range: number): number {
  return ((value + range) / (range * 2)) * 100;
}

export default function ForestPlot({
  effect,
  ciLower,
  ciUpper,
  metricType
}: ForestPlotProps) {
  const maxMagnitude = Math.max(Math.abs(ciLower), Math.abs(ciUpper), Math.abs(effect), 0.01);
  const range = maxMagnitude * 1.25;
  const ciStart = Math.min(position(ciLower, range), position(ciUpper, range));
  const ciEnd = Math.max(position(ciLower, range), position(ciUpper, range));
  const markerPosition = position(effect, range);
  const label = metricType === "binary" ? "Effect in percentage points" : "Effect in metric units";

  return (
    <div style={{ display: "grid", gap: "10px" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
        <strong>{label}</strong>
        <span className="muted">
          {formatValue(effect, metricType)} [{formatValue(ciLower, metricType)}, {formatValue(ciUpper, metricType)}]
        </span>
      </div>

      <div
        role="img"
        aria-label={`Forest plot with effect ${formatValue(effect, metricType)} and confidence interval from ${formatValue(ciLower, metricType)} to ${formatValue(ciUpper, metricType)}`}
        style={{
          position: "relative",
          minHeight: "80px",
          borderRadius: "20px",
          border: "1px solid var(--color-border)",
          background:
            "linear-gradient(135deg, color-mix(in srgb, var(--color-secondary) 8%, transparent), color-mix(in srgb, var(--color-info) 10%, transparent))",
          overflow: "hidden"
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: "0",
            backgroundImage:
              "linear-gradient(to right, transparent 0, transparent calc(50% - 1px), color-mix(in srgb, var(--color-text) 22%, transparent) calc(50% - 1px), color-mix(in srgb, var(--color-text) 22%, transparent) calc(50% + 1px), transparent calc(50% + 1px), transparent 100%)",
            opacity: 0.8
          }}
        />
        <div
          style={{
            position: "absolute",
            left: "7%",
            right: "7%",
            top: "50%",
            height: "2px",
            transform: "translateY(-50%)",
            background: "linear-gradient(90deg, var(--color-border), color-mix(in srgb, var(--color-text) 28%, transparent), var(--color-border))"
          }}
        />
        <div
          style={{
            position: "absolute",
            left: `${ciStart}%`,
            width: `${Math.max(ciEnd - ciStart, 1)}%`,
            top: "50%",
            height: "14px",
            transform: "translateY(-50%)",
            borderRadius: "999px",
            background: "linear-gradient(90deg, var(--color-info), var(--color-secondary))",
            boxShadow: "0 0 0 1px color-mix(in srgb, var(--color-bg) 35%, transparent)"
          }}
        />
        <div
          style={{
            position: "absolute",
            left: `${markerPosition}%`,
            top: "50%",
            width: "16px",
            height: "16px",
            transform: "translate(-50%, -50%) rotate(45deg)",
            borderRadius: "3px",
            background: "var(--color-bg-card)",
            border: "2px solid var(--color-text)",
            boxShadow: "0 8px 20px color-mix(in srgb, var(--color-text) 16%, transparent)"
          }}
        />
        <div
          style={{
            position: "absolute",
            left: `${markerPosition}%`,
            top: "calc(50% - 18px)",
            transform: "translateX(-50%)",
            padding: "3px 8px",
            borderRadius: "999px",
            background: "var(--color-bg-card)",
            border: "1px solid var(--color-border)",
            fontSize: "11px",
            fontWeight: 700,
            whiteSpace: "nowrap"
          }}
        >
          {formatValue(effect, metricType)}
        </div>
      </div>

      <div style={{ display: "grid", gap: "8px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", alignItems: "center", fontSize: "12px" }}>
          <span className="muted">{formatValue(-range, metricType)}</span>
          <strong style={{ justifySelf: "center" }}>0</strong>
          <span className="muted" style={{ justifySelf: "end" }}>{formatValue(range, metricType)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", flexWrap: "wrap", fontSize: "12px" }}>
          <span className="muted">Lower CI: {formatValue(ciLower, metricType)}</span>
          <span className="muted">Upper CI: {formatValue(ciUpper, metricType)}</span>
        </div>
      </div>
    </div>
  );
}
