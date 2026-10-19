// App shell (PLAN-DEV-B 3.1): sign-in, the routes, and the frame around them.
// Each screen owns its own state; the review screen keeps the upload and the
// table together (#32).
// Owner: shared

import "./shared/ui/tokens.css";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { AuthProvider } from "./features/auth/AuthProvider";
import { LoginPage } from "./features/auth/LoginPage";
import { RequireAuth } from "./features/auth/RequireAuth";
import { RecordPage } from "./features/records/RecordPage";
import { RecordsPage } from "./features/records/RecordsPage";
import { ReviewPage } from "./features/review/ReviewPage";
import { Layout } from "./shared/layout/Layout";
import { ErrorBoundary } from "./shared/ui/ErrorBoundary";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
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
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

function NotFound() {
  return (
    <div className="app-status">
      <p>הדף לא נמצא.</p>
      <Link to="/">חזרה להעלאה ובדיקה</Link>
    </div>
  );
}

export default App;
