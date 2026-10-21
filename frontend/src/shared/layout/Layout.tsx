// The frame of every screen: the app's name and the navigation
// (PLAN-DEV-B 3.0, "כללי").
// Owner: B

import { NavLink, Outlet } from "react-router";
import "./Layout.css";

export function Layout() {
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
      </header>
      <main className="layout-main">
        <Outlet />
      </main>
    </div>
  );
}
