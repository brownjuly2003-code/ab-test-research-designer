import type { CSSProperties } from "react";

import type { SensitivityCell } from "../lib/generated/api-contract";

type SensitivityTableProps = {
  cells: SensitivityCell[];
  currentMde: number;
  currentPower: number;
  metricType: "binary" | "continuous";
};

const wrapperStyle: CSSProperties = {
  overflowX: "auto"
};

const tableStyle: CSSProperties = {
  width: "100%",
  minWidth: "520px",
  borderCollapse: "separate",
  borderSpacing: 0,
  fontVariantNumeric: "tabular-nums"
};

const headerCellStyle: CSSProperties = {
  padding: "12px 14px",
  borderBottom: "1px solid var(--color-border)",
  background: "var(--color-surface-subtle)",
  color: "var(--color-text-secondary)",
  fontSize: "var(--font-size-xs)",
  fontWeight: 700,
  textAlign: "left",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  position: "sticky",
  top: 0
};

const rowHeaderStyle: CSSProperties = {
  padding: "12px 14px",
  borderBottom: "1px solid var(--color-border)",
  color: "var(--color-text)",
  fontWeight: 700
};

const emptyCellStyle: CSSProperties = {
  padding: "12px 14px",
  borderBottom: "1px solid var(--color-border)",
  color: "var(--color-text-secondary)"
};

function formatMde(value: number, metricType: "binary" | "continuous"): string {
  return metricType === "binary" ? `${value}%` : String(value);
}

function isSameValue(left: number, right: number): boolean {
  return Math.abs(left - right) < 0.0001;
}

function findCell(cells: SensitivityCell[], mde: number, power: number): SensitivityCell | undefined {
  return cells.find((cell) => isSameValue(cell.mde, mde) && isSameValue(cell.power, power));
}

function resolveCellStyle(
  duration: number,
  minDuration: number,
  maxDuration: number,
  isCurrent: boolean
): CSSProperties {
  if (isCurrent) {
    return {
      background: "var(--color-primary-light)",
      color: "var(--color-primary)",
      fontWeight: 700
    };
  }

  const range = Math.max(maxDuration - minDuration, 1);
  const position = (duration - minDuration) / range;
  if (position <= 0.33) {
    return {
      background: "var(--color-success-light)",
      color: "var(--color-text)"
    };
  }
  if (position <= 0.66) {
    return {
      background: "var(--color-warning-light)",
      color: "var(--color-text)"
    };
  }
  return {
    background: "var(--color-danger-light)",
    color: "var(--color-text)"
  };
}

export default function SensitivityTable({
  cells,
  currentMde,
  currentPower,
  metricType
}: SensitivityTableProps) {
  const mdeValues = Array.from(new Set(cells.map((cell) => cell.mde))).sort((left, right) => left - right);
  const powerLevels = Array.from(new Set(cells.map((cell) => cell.power))).sort((left, right) => left - right);
  const durations = cells.map((cell) => cell.duration_days);
  const minDuration = Math.min(...durations);
  const maxDuration = Math.max(...durations);

  return (
    <div style={wrapperStyle}>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th scope="col" style={headerCellStyle}>
              MDE
            </th>
            {powerLevels.map((power) => (
              <th key={power} scope="col" style={headerCellStyle}>
                {(power * 100).toFixed(0)}% power
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {mdeValues.map((mde) => (
            <tr key={mde}>
              <th scope="row" style={rowHeaderStyle}>
                {formatMde(mde, metricType)}
              </th>
              {powerLevels.map((power) => {
                const cell = findCell(cells, mde, power);
                if (!cell) {
                  return (
                    <td key={power} style={emptyCellStyle}>
                      -
                    </td>
                  );
                }

                const isCurrent = isSameValue(mde, currentMde) && isSameValue(power, currentPower);
                return (
                  <td
                    key={power}
                    style={{
                      padding: "12px 14px",
                      borderBottom: "1px solid var(--color-border)",
                      ...resolveCellStyle(cell.duration_days, minDuration, maxDuration, isCurrent)
                    }}
                  >
                    {Math.ceil(cell.duration_days)}d
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
