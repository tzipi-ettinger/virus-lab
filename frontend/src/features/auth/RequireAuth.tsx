// Screens behind sign-in: without a session, to /login, and from there to the
// upload (PLAN-DEV-B 3.5).
// Owner: B

import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { useAuth } from "./authContext";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { state, retry } = useAuth();

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
    case "signed_out":
      return <Navigate to="/login" replace />;
    case "signed_in":
      return children;
  }
}
