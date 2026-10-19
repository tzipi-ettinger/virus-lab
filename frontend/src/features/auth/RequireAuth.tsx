// Screens behind sign-in: without a session, to /login and back here after it
// (PLAN-DEV-B 3.5).
// Owner: B

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { useAuth } from "./authContext";
import type { LoginRedirect } from "./LoginPage";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { state, retry } = useAuth();
  const location = useLocation();

  switch (state.status) {
    case "loading":
      return <p className="app-status">טוען…</p>;
    case "error":
      return (
        <div className="app-status" role="alert">
          <p>⚠ {state.message}</p>
          <button type="button" onClick={retry}>
            נסי שוב
          </button>
        </div>
      );
    case "signed_out": {
      const redirect: LoginRedirect = { from: location.pathname + location.search };
      return <Navigate to="/login" state={redirect} replace />;
    }
    case "signed_in":
      return children;
  }
}
