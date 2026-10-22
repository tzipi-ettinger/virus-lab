// @vitest-environment jsdom
// Signed-in screens and the frame around them (PLAN-DEV-B 3.1, 3.5).
// Owner: B

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Layout } from "../../shared/layout/Layout";
import { ErrorBoundary } from "../../shared/ui/ErrorBoundary";
import { AuthContext, type Auth, type AuthState } from "./authContext";
import { RequireAuth } from "./RequireAuth";

afterEach(cleanup);

const DANA: AuthState = { status: "signed_in", user: { id: "u1", username: "dana", display_name: "דנה" } };

function LoginProbe() {
  const from = (useLocation().state as { from?: string } | null)?.from;
  return <p>כניסה, ואחר כך {from}</p>;
}

function renderAt(path: string, state: AuthState, overrides: Partial<Auth> = {}) {
  const auth: Auth = { state, login: vi.fn(), logout: vi.fn().mockResolvedValue(undefined), retry: vi.fn(), ...overrides };
  render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<LoginProbe />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route path="/records" element={<p>מסך הרשומות</p>} />
            <Route path="/records/:recordId" element={<p>מסך הרשומה</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
  return auth;
}

describe("RequireAuth", () => {
  test("a record link without a session goes to login first, which is told the record", () => {
    renderAt("/records/r1", { status: "signed_out" });

    expect(screen.getByText("כניסה, ואחר כך /records/r1")).toBeTruthy();
    expect(screen.queryByText("מסך הרשומה")).toBeNull();
  });

  test("with a session shows the screen inside the frame", () => {
    renderAt("/records", DANA);

    expect(screen.getByText("מסך הרשומות")).toBeTruthy();
    expect(screen.getByText("דנה")).toBeTruthy();
  });

  test("waits for /auth/me before deciding", () => {
    renderAt("/records", { status: "loading" });

    expect(screen.getByText("טוען…")).toBeTruthy();
    expect(screen.queryByText("מסך הרשומות")).toBeNull();
  });

  test("a server error offers to try again", async () => {
    const auth = renderAt("/records", { status: "error", message: "אין חיבור לשרת" });

    expect(screen.getByRole("alert").textContent).toContain("אין חיבור לשרת");
    await userEvent.setup().click(screen.getByRole("button", { name: "נסי שוב" }));
    expect(auth.retry).toHaveBeenCalledOnce();
  });
});

describe("Layout", () => {
  test("sign-out ends the session and goes to login", async () => {
    const auth = renderAt("/records", DANA);

    await userEvent.setup().click(screen.getByRole("button", { name: "יציאה" }));

    expect(auth.logout).toHaveBeenCalledOnce();
    expect(await screen.findByText(/^כניסה/)).toBeTruthy();
  });

  test("marks the current screen in the navigation", () => {
    renderAt("/records", DANA);

    expect(screen.getByRole("link", { name: "רשומות" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "העלאה ובדיקה" }).getAttribute("aria-current")).toBeNull();
  });
});

describe("ErrorBoundary", () => {
  test("a screen that throws shows a reload page instead of nothing", () => {
    const Broken = () => {
      throw new Error("boom");
    };
    vi.spyOn(console, "error").mockImplementation(() => {}); // React reports the error

    render(
      <ErrorBoundary>
        <Broken />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("heading", { name: "משהו השתבש" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "רענון" })).toBeTruthy();
  });
});
