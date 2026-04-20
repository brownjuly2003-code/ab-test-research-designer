import type { ReactNode } from "react";

import ErrorBoundary from "./ErrorBoundary";

type ChartErrorBoundaryProps = {
  children: ReactNode;
  rawData?: unknown;
  data?: unknown;
  onError?: (error: Error) => void;
};

function formatChartData(data: unknown): string {
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

export default function ChartErrorBoundary({
  children,
  rawData,
  data,
  onError
}: ChartErrorBoundaryProps) {
  const fallbackData = rawData ?? data;

  return (
    <ErrorBoundary
      onError={(error) => {
        onError?.(error);
      }}
      fallback={(
        <div className="card" role="alert">
          <strong>Chart unavailable</strong>
          <div className="muted">Rendering failed. Raw data is shown below for inspection.</div>
          {fallbackData !== undefined ? <pre>{formatChartData(fallbackData)}</pre> : null}
        </div>
      )}
    >
      {children}
    </ErrorBoundary>
  );
}
