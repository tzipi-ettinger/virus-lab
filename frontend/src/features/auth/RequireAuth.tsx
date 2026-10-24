// Screens behind sign-in: without a session, to /login first. It is told which
// screen asked, so a link to one record opens that record after it (PLAN-DEV-B 3.5).
// Owner: B

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { t } from "../../i18n";
import { useAuth } from "./authContext";
import type { LoginRedirect } from "./LoginPage";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { state, retry } = useAuth();
  const location = useLocation();

  switch (state.status) {
    case "loading":
      return <p className="app-status">{t("common.loading")}</p>;
    case "error":
      return (
        <div className="app-status" role="alert">
          <p>⚠ {state.message}</p>
          <button type="button" onClick={retry}>
            {t("common.retry")}
          </button>
        </div>
      );
    case "signed_out": {
      const redirect: LoginRedirect = { from: location.pathname };
      return <Navigate to="/login" state={redirect} replace />;
    }
    case "signed_in":
      return children;
  }
}
