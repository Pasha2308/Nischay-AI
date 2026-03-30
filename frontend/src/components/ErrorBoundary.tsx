import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode; title?: string };

type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error boundary:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="page">
          <h2>{this.props.title ?? "Something went wrong"}</h2>
          <div className="card">
            <p className="muted">
              The dashboard hit an error while loading data. Check that the API is running and the URL in{" "}
              <code>VITE_API_BASE</code> is correct.
            </p>
            <pre className="run-json-pre" style={{ marginTop: 12 }}>
              {this.state.error.message}
            </pre>
            <button type="button" className="btn-primary" style={{ marginTop: 12 }} onClick={() => this.setState({ error: null })}>
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
