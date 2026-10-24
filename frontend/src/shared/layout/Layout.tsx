// The frame of every signed-in screen: the ministry's logo, the app's name, the
// navigation, who is signed in, and sign-out (PLAN-DEV-B 3.0, "כללי").
// Owner: B

import { Link, NavLink, Outlet, useNavigate } from "react-router";
import { useAuth } from "../../features/auth/authContext";
import { t } from "../../i18n";
import { LanguageSwitch } from "../ui/LanguageSwitch";
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
        <Link to="/" className="layout-brand" aria-label={t("layout.home")}>
          <img className="layout-logo" src="/moh-logo.png" alt={t("common.ministry")} />
          <span className="layout-names">
            <span className="layout-title">{t("common.lab")}</span>
            <span className="layout-subtitle">{t("layout.subtitle")}</span>
          </span>
        </Link>
        <nav className="layout-nav" aria-label={t("layout.nav")}>
          <NavLink to="/upload">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 16V4" />
              <path d="m6 10 6-6 6 6" />
              <path d="M4 20h16" />
            </svg>
            {t("layout.upload")}
          </NavLink>
          <NavLink to="/records">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
            {t("layout.records")}
          </NavLink>
          <NavLink to="/stats">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M6 20v-7M12 20V5M18 20v-9" />
            </svg>
            {t("layout.stats")}
          </NavLink>
        </nav>
        <span className="layout-user">
          <LanguageSwitch />
          {name}
          <button type="button" onClick={signOut}>
            {t("layout.signOut")}
          </button>
        </span>
      </header>
      <main className="layout-main">
        <Outlet />
      </main>
    </div>
  );
}
