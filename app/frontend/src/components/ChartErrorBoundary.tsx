import { useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
  const fallbackData = rawData ?? data;
  const fallbackRef = useRef<HTMLDivElement | null>(null);

  return (
    <ErrorBoundary
      onError={(error) => {
        onError?.(error);
        queueMicrotask(() => fallbackRef.current?.focus());
      }}
      fallback={(
        <div ref={fallbackRef} className="card" role="alert" tabIndex={-1}>
          <strong>{t("chartErrorBoundary.title")}</strong>
          <div className="muted">{t("chartErrorBoundary.description")}</div>
          {fallbackData !== undefined ? <pre>{formatChartData(fallbackData)}</pre> : null}
        </div>
      )}
    >
      {children}
    </ErrorBoundary>
  );
}
