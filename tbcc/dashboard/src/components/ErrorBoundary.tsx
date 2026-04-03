import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode; name?: string };

type State = { error: Error | null };

/**
 * Catches render errors so a single broken panel doesn't leave a blank screen with no feedback.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[TBCC dashboard${this.props.name ? `: ${this.props.name}` : ""}]`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded-lg border border-red-700 bg-red-900/30 p-6 text-red-100 max-w-2xl">
          <h2 className="text-lg font-semibold mb-2">Something went wrong</h2>
          <p className="text-sm text-red-200/90 mb-3">
            This tab crashed while rendering. Check the browser console (F12) for details.
          </p>
          <pre className="text-xs bg-black/30 p-3 rounded overflow-auto whitespace-pre-wrap mb-4">
            {this.state.error.message}
          </pre>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="px-4 py-2 rounded bg-slate-600 text-slate-100 hover:bg-slate-500"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
