// Loads /auth/me once when the app starts, and holds the signed-in user
// (PLAN-DEV-B 3.3). Any 401 from the API signs the user out here.
// Owner: B

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, apiFetch, onUnauthorized } from "../../api/client";
import { t } from "../../i18n";
import { AuthContext, type Auth, type AuthState, type User } from "./authContext";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => onUnauthorized(() => setState({ status: "signed_out" })), []);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<User>("/api/v1/auth/me", { signal: controller.signal }).then(
      (user) => setState({ status: "signed_in", user }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 401) setState({ status: "signed_out" });
        else setState({ status: "error", message: errorMessage(error) });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const login = useCallback(async (username: string, password: string) => {
    const user = await apiFetch<User>("/api/v1/auth/login", {
      method: "POST",
      body: { username, password },
    });
    setState({ status: "signed_in", user });
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST" });
    } finally {
      // Signed out on this screen even if the server didn't answer.
      setState({ status: "signed_out" });
    }
  }, []);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  const auth = useMemo<Auth>(() => ({ state, login, logout, retry }), [state, login, logout, retry]);
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : t("common.failed");
}
