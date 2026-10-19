// The frame of every signed-in screen: the app's name, the navigation, who is
// signed in, and sign-out (PLAN-DEV-B 3.0, "כללי").
// Owner: B

import { NavLink, Outlet, useNavigate } from "react-router";
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
        <span className="layout-title">מטפסי התחייבות לנתונים מובנים</span>
        <nav className="layout-nav" aria-label="ניווט ראשי">
          <NavLink to="/" end>
            העלאה ובדיקה
          </NavLink>
          <NavLink to="/records">רשומות</NavLink>
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
