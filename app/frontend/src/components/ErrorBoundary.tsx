import { Component, Fragment, type ErrorInfo, type ReactNode } from "react";

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
  state: ErrorBoundaryState = {
    error: null,
    retryCount: 0
  };

  static getDerivedStateFromError(error: Error): Pick<ErrorBoundaryState, "error"> {
    return { error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.props.onError?.(error, errorInfo);
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
        <div className="callout" role="alert">
          <strong>Something went wrong</strong>
          <div className="muted">This section crashed while rendering. Retry to mount it again.</div>
          <div className="actions">
            <button className="btn secondary" type="button" onClick={this.handleRetry}>
              Retry
            </button>
          </div>
        </div>
      );
    }

    return <Fragment key={this.state.retryCount}>{this.props.children}</Fragment>;
  }
}
