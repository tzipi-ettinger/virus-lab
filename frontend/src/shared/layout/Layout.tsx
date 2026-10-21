// The frame of every screen: the app's name and the navigation
// (PLAN-DEV-B 3.0, "כללי").
// Owner: B

import { useEffect, useRef } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import "./Layout.css";

export function Layout() {
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const shown = useRef(pathname);
  // A new screen moves the focus to its content, so a screen reader hears that the
  // screen changed and Tab starts there. Not on first load, and not when only the
  // filters in the URL change.
  useEffect(() => {
    if (shown.current === pathname) return;
    shown.current = pathname;
    main.current?.focus();
  }, [pathname]);

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
      <main className="layout-main" ref={main} tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
