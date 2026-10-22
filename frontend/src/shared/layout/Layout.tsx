// The frame of every signed-in screen: the ministry's logo, the app's name, the
// navigation, who is signed in, and sign-out (PLAN-DEV-B 3.0, "כללי").
// Owner: B

import { Link, NavLink, Outlet, useNavigate } from "react-router";
import { useAuth } from "../../features/auth/authContext";
import "./Layout.css";

export function Layout() {
  const { state, logout } = useAuth();
  const navigate = useNavigate();
  const name = state.status === "signed_in" ? state.user.display_name : "";

  async function signOut() {
    await logout().catch(() => {}); // signed out on this screen either way
    navigate("/login", { replace: true });
  }

  return (
    <div className="layout">
      <header className="layout-bar">
        <Link to="/" className="layout-brand" aria-label="דף הבית">
          <img className="layout-logo" src="/moh-logo.png" alt="משרד הבריאות" />
          <span className="layout-names">
            <span className="layout-title">המעבדה המרכזית לנגיפים</span>
            <span className="layout-subtitle">מטפסי התחייבות לנתונים מובנים</span>
          </span>
        </Link>
        <nav className="layout-nav" aria-label="ניווט ראשי">
          <NavLink to="/upload">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 16V4" />
              <path d="m6 10 6-6 6 6" />
              <path d="M4 20h16" />
            </svg>
            העלאה ובדיקה
          </NavLink>
          <NavLink to="/records">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
            רשומות
          </NavLink>
          <NavLink to="/stats">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M6 20v-7M12 20V5M18 20v-9" />
            </svg>
            תמונת מצב
          </NavLink>
        </nav>
        <span className="layout-user">
          {name}
          <button type="button" onClick={signOut}>
            יציאה
          </button>
        </span>
      </header>
      <main className="layout-main">
        <Outlet />
      </main>
    </div>
  );
}
