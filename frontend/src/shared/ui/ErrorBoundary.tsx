// An error while drawing a screen shows a plain page with a reload button,
// not a blank screen (PLAN-DEV-B 3.5).
// Owner: B

import { Component, type ReactNode } from "react";
import { t } from "../../i18n";

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
        <h1>{t("errorBoundary.title")}</h1>
        <p>{t("errorBoundary.text")}</p>
        <button type="button" onClick={() => window.location.reload()}>
          {t("errorBoundary.reload")}
        </button>
      </div>
    );
  }
}
