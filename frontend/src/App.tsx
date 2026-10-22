// App shell (PLAN-DEV-B 3.1): the routes and the frame around them. No sign-in:
// anyone with the link can use the site (21.10).
// The landing page opens the site; from it, upload and review, then the records.
// Each screen owns its own state; the review screen keeps the upload and the
// table together (#32).
// Owner: shared

import "./shared/ui/tokens.css";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { LandingPage } from "./features/landing/LandingPage";
import { RecordPage } from "./features/records/RecordPage";
import { RecordsPage } from "./features/records/RecordsPage";
import { ReviewPage } from "./features/review/ReviewPage";
import { Layout } from "./shared/layout/Layout";
import { ErrorBoundary } from "./shared/ui/ErrorBoundary";

export function AppRoutes() {
  return (
    <Routes>
      <Route index element={<LandingPage />} />
      <Route element={<Layout />}>
        <Route path="upload" element={<ReviewPage />} />
        <Route path="records" element={<RecordsPage />} />
        <Route path="records/:recordId" element={<RecordPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ErrorBoundary>
  );
}

function NotFound() {
  return (
    <div className="app-status">
      <p>הדף לא נמצא.</p>
      <Link to="/upload">חזרה להעלאה ובדיקה</Link>
    </div>
  );
}

export default App;
