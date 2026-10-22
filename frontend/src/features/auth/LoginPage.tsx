// Sign in with a username and password (PLAN-DEV-B 3.1). There is no sign-up:
// users are created with scripts/create_user. After signing in, to the upload;
// only a link to one record goes back to that record (22.10).
// It is the first screen anyone sees, so it opens the site: the ministry's
// logo, what the system does, and the sign-in card beside them.
// Owner: B

import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useAuth } from "./authContext";
import { greeting } from "./greeting";
import { loginError } from "./loginError";
import "./LoginPage.css";

export type LoginRedirect = { from?: string };

const RECORD_LINK = /^\/records\/[^/?#]+$/;

/** Where to go after signing in: the record a link pointed to, or else the upload. */
function afterLogin(from: string | undefined): string {
  return from && RECORD_LINK.test(from) ? from : "/upload";
}

const POINTS = [
  "קורא שבעה שדות מכל טופס, גם בכתב יד",
  "מסמן לבדיקה כל ערך שאינו ודאי",
  "שומר מי אישר, מי תיקן ומתי",
];

export function LoginPage() {
  const { state, login } = useAuth();
  const navigate = useNavigate();
  const next = afterLogin((useLocation().state as LoginRedirect | null)?.from);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hello] = useState(() => greeting(new Date().getHours()));

  if (state.status === "signed_in") return <Navigate to={next} replace />;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      navigate(next, { replace: true });
    } catch (failure) {
      setPassword("");
      setError(loginError(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-glow" aria-hidden="true" />
      <main className="login-main">
        <section className="login-brand">
          <img className="login-logo" src="/moh-logo.png" alt="משרד הבריאות" />
          <p className="login-kicker">המעבדה המרכזית לנגיפים</p>
          <h1 className="login-title">
            מטופס סרוק{" "}
            <br />
            <span className="login-title-accent">לרשומה מאושרת</span>
          </h1>
          <ul className="login-points">
            {POINTS.map((point) => (
              <li key={point}>
                <span className="login-point-icon" aria-hidden="true">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 12.5 10 17l9-10" />
                  </svg>
                </span>
                {point}
              </li>
            ))}
          </ul>
        </section>

        <form className="login-card" onSubmit={submit} noValidate>
          <h2>כניסה למערכת</h2>
          <p className="login-hint">{hello}, טוב לראות אותך.</p>
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
            {/* The eye shows the password as text, and hides it again. */}
            <span className="login-password">
              <input
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <button
                type="button"
                className="login-eye"
                aria-label={showPassword ? "הסתרת הסיסמה" : "הצגת הסיסמה"}
                aria-pressed={showPassword}
                title={showPassword ? "הסתרת הסיסמה" : "הצגת הסיסמה"}
                onClick={() => setShowPassword((shown) => !shown)}
              >
                <EyeIcon open={!showPassword} />
              </button>
            </span>
          </label>
          {error && (
            <p className="login-error" role="alert">
              ⚠ {error}
            </p>
          )}
          <button type="submit" className="login-submit" disabled={busy || !username.trim() || !password}>
            {busy ? "נכנסת…" : "כניסה"}
            {!busy && <span aria-hidden="true">←</span>}
          </button>
        </form>
      </main>
      <footer className="login-footer">משרד הבריאות · המעבדה המרכזית לנגיפים</footer>
    </div>
  );
}

/** An open eye ("show"), or a crossed one ("hide"). */
function EyeIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
      {!open && <path d="M3 3l18 18" />}
    </svg>
  );
}
