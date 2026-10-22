// @vitest-environment jsdom
// The login screen: errors in Hebrew, and back to the screen that asked (PLAN-DEV-B 3.5).
// Owner: B

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "../../api/client";
import { AuthContext, type Auth, type AuthState } from "./authContext";
import { LoginPage } from "./LoginPage";
import { loginError } from "./loginError";

afterEach(cleanup);

function renderLogin(login: Auth["login"], state: AuthState = { status: "signed_out" }) {
  const auth: Auth = { state, login, logout: vi.fn(), retry: vi.fn() };
  render(
    <AuthContext.Provider value={auth}>
      <MemoryRouter initialEntries={[{ pathname: "/login", state: { from: "/records?status=pending" } }]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/records" element={<p>מסך הרשומות</p>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

async function signIn(password = "correct horse battery") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("שם משתמש"), "dana");
  await user.type(screen.getByLabelText("סיסמה"), password);
  await user.click(screen.getByRole("button", { name: "כניסה" }));
}

describe("LoginPage", () => {
  test("the username field has the focus", () => {
    renderLogin(vi.fn());

    expect(document.activeElement).toBe(screen.getByLabelText("שם משתמש"));
  });

  test("signs in and goes back to the screen that asked", async () => {
    const login = vi.fn<Auth["login"]>().mockResolvedValue();
    renderLogin(login);

    await signIn();

    expect(login).toHaveBeenCalledWith("dana", "correct horse battery");
    expect(await screen.findByText("מסך הרשומות")).toBeTruthy();
  });

  test("a wrong password shows one message and clears the password", async () => {
    const login = vi
      .fn<Auth["login"]>()
      .mockRejectedValue(new ApiError(401, { type: "invalid_credentials", title: "x" }));
    renderLogin(login);

    await signIn("wrong password");

    expect((await screen.findByRole("alert")).textContent).toContain("שם המשתמש או הסיסמה שגויים");
    expect((screen.getByLabelText("סיסמה") as HTMLInputElement).value).toBe("");
  });

  test("the eye shows the password, and hides it again", async () => {
    renderLogin(vi.fn<Auth["login"]>());
    const user = userEvent.setup();
    const password = screen.getByLabelText("סיסמה") as HTMLInputElement;
    await user.type(password, "secret");
    expect(password.type).toBe("password");

    await user.click(screen.getByRole("button", { name: "הצגת הסיסמה" }));
    expect(password.type).toBe("text");
    expect(password.value).toBe("secret");

    const hide = screen.getByRole("button", { name: "הסתרת הסיסמה" });
    expect(hide.getAttribute("aria-pressed")).toBe("true");
    await user.click(hide);
    expect(password.type).toBe("password");
  });

  test("a locked account says when to try again", async () => {
    const login = vi
      .fn<Auth["login"]>()
      .mockRejectedValue(new ApiError(429, { type: "too_many_attempts", title: "x" }));
    renderLogin(login);

    await signIn();

    expect((await screen.findByRole("alert")).textContent).toContain("נסי שוב בעוד 15 דקות");
  });

  test("an already signed-in user goes straight on", () => {
    renderLogin(vi.fn(), { status: "signed_in", user: { id: "u1", username: "dana", display_name: "דנה" } });

    expect(screen.getByText("מסך הרשומות")).toBeTruthy();
  });
});

describe("loginError", () => {
  test("uses the server's title for anything else", () => {
    expect(loginError(new ApiError(403, { type: "origin_not_allowed", title: "כותרת מהשרת" }))).toBe(
      "כותרת מהשרת",
    );
  });

  test("says the server is down when the database is", () => {
    expect(loginError(new ApiError(503, { type: "database_unavailable", title: "x" }))).toContain("לא זמין");
  });
});
