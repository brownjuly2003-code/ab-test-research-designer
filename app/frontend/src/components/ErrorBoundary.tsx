import { Component, Fragment, createRef, type ErrorInfo, type ReactNode } from "react";

import { t } from "../i18n";

type ErrorBoundaryProps = {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
};

type ErrorBoundaryState = {
  error: Error | null;
  retryCount: number;
};

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  private fallbackRef = createRef<HTMLDivElement>();

  state: ErrorBoundaryState = {
    error: null,
    retryCount: 0
  };

  static getDerivedStateFromError(error: Error): Pick<ErrorBoundaryState, "error"> {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.props.onError?.(error, errorInfo);
    queueMicrotask(() => this.fallbackRef.current?.focus());
  }

  private handleRetry = () => {
    this.setState((current) => ({
      error: null,
      retryCount: current.retryCount + 1
    }));
  };

  render() {
    if (this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div ref={this.fallbackRef} className="callout" role="alert" tabIndex={-1}>
          <strong>{t("errorBoundary.title")}</strong>
          <div className="muted">{t("errorBoundary.description")}</div>
          <div className="actions">
            <button className="btn secondary" type="button" onClick={this.handleRetry}>
              {t("errorBoundary.retry")}
            </button>
          </div>
        </div>
      );
    }

    return <Fragment key={this.state.retryCount}>{this.props.children}</Fragment>;
  }
}
