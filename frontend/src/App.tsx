// App shell (PLAN-DEV-B 3.1): the routes and the frame around them. No sign-in:
// anyone with the link can use the site (21.10).
// Each screen owns its own state; the review screen keeps the upload and the
// table together (#32).
// Owner: shared

import "./shared/ui/tokens.css";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { RecordPage } from "./features/records/RecordPage";
import { RecordsPage } from "./features/records/RecordsPage";
import { ReviewPage } from "./features/review/ReviewPage";
import { Layout } from "./shared/layout/Layout";
import { usePageTitle } from "./shared/usePageTitle";
import { ErrorBoundary } from "./shared/ui/ErrorBoundary";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<ReviewPage />} />
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
  usePageTitle("הדף לא נמצא");
  return (
    <div className="app-status">
      <p>הדף לא נמצא.</p>
      <Link to="/">חזרה להעלאה ובדיקה</Link>
    </div>
  );
}

export default App;
