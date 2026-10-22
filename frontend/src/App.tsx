// App shell (PLAN-DEV-B 3.1): sign-in, the routes, and the frame around them.
// Every screen but /login is behind sign-in (22.10).
// The landing page opens the site; from it, upload and review, then the records.
// Each screen owns its own state; the review screen keeps the upload and the
// table together (#32).
// Owner: shared

import "./shared/ui/tokens.css";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { AuthProvider } from "./features/auth/AuthProvider";
import { LoginPage } from "./features/auth/LoginPage";
import { RequireAuth } from "./features/auth/RequireAuth";
import { LandingPage } from "./features/landing/LandingPage";
import { RecordPage } from "./features/records/RecordPage";
import { RecordsPage } from "./features/records/RecordsPage";
import { ReviewPage } from "./features/review/ReviewPage";
import { StatsPage } from "./features/stats/StatsPage";
import { Layout } from "./shared/layout/Layout";
import { ErrorBoundary } from "./shared/ui/ErrorBoundary";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        index
        element={
          <RequireAuth>
            <LandingPage />
          </RequireAuth>
        }
      />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="upload" element={<ReviewPage />} />
        <Route path="records" element={<RecordsPage />} />
        <Route path="records/:recordId" element={<RecordPage />} />
        <Route path="stats" element={<StatsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

function NotFound() {
  return (
    <div className="not-found">
      <p className="not-found-code" aria-hidden="true">
        404
      </p>
      <h1 className="not-found-title">הדף לא נמצא.</h1>
      <p className="not-found-text">ייתכן שהכתובת שגויה, או שהדף הועבר. אפשר להמשיך מכאן:</p>
      <div className="not-found-actions">
        <Link to="/upload" className="not-found-primary">
          חזרה להעלאה ובדיקה
        </Link>
        <Link to="/records" className="not-found-secondary">
          לכל הרשומות
        </Link>
        <Link to="/" className="not-found-secondary">
          לדף הבית
        </Link>
      </div>
    </div>
  );
}

export default App;
