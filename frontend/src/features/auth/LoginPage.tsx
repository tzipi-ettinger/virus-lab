// Sign in with a username and password (PLAN-DEV-B 3.1). There is no sign-up:
// users are created with scripts/create_user. After signing in, back to the
// screen that asked for it.
// Owner: B

import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useAuth } from "./authContext";
import { loginError } from "./loginError";
import "./LoginPage.css";

export type LoginRedirect = { from?: string };

export function LoginPage() {
  const { state, login } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as LoginRedirect | null)?.from ?? "/";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (state.status === "signed_in") return <Navigate to={from} replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      navigate(from, { replace: true });
    } catch (failure) {
      setPassword("");
      setError(loginError(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit} noValidate>
        <h1>כניסה למערכת</h1>
        <p className="login-hint">מטפסי התחייבות לנתונים מובנים</p>
        <label>
          שם משתמש
          <input
            name="username"
            autoComplete="username"
            autoFocus
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <label>
          סיסמה
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error && (
          <p className="login-error" role="alert">
            ⚠ {error}
          </p>
        )}
        <button type="submit" disabled={busy || !username.trim() || !password}>
          {busy ? "נכנסת…" : "כניסה"}
        </button>
      </form>
    </main>
  );
}
