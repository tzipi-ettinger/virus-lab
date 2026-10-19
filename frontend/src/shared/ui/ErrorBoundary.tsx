// An error while drawing a screen shows a plain page with a reload button,
// not a blank screen (PLAN-DEV-B 3.5).
// Owner: B

import { Component, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { failed: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="app-status" role="alert">
        <h1>משהו השתבש</h1>
        <p>המסך לא הצליח להיטען. רענון בדרך כלל עוזר. מה שכבר נשמר לא נמחק.</p>
        <button type="button" onClick={() => window.location.reload()}>
          רענון
        </button>
      </div>
    );
  }
}
