// @vitest-environment jsdom
// The routes: every screen but /login is behind sign-in, and an unknown path
// gets the 404 page inside the frame.
// Owner: shared

import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { AppRoutes } from "./App";
import { AuthProvider } from "./features/auth/AuthProvider";

const DANA = { id: "u1", username: "dana", display_name: "דנה" };

function json(status: number, body: unknown) {
  const type = status < 400 ? "application/json" : "application/problem+json";
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": type } });
}

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function signedIn() {
  fetchMock.mockImplementation(async (url) =>
    String(url) === "/api/v1/auth/me" ? json(200, DANA) : json(200, []),
  );
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("AppRoutes", () => {
  test.each(["/", "/upload", "/records", "/records/r1"])("%s without a session goes to sign-in", async (path) => {
    fetchMock.mockResolvedValue(json(401, { type: "unauthenticated", title: "צריך להתחבר", status: 401 }));
    renderAt(path);

    expect(await screen.findByRole("button", { name: /כניסה/ })).toBeTruthy();
  });

  test("an unknown path shows the 404 page with ways back", async () => {
    signedIn();
    renderAt("/no-such-page");

    expect(await screen.findByRole("heading", { name: "הדף לא נמצא." })).toBeTruthy();
    expect(screen.getByRole("link", { name: "חזרה להעלאה ובדיקה" }).getAttribute("href")).toBe("/upload");
    expect(screen.getByRole("link", { name: "לכל הרשומות" }).getAttribute("href")).toBe("/records");
    expect(screen.getByRole("link", { name: "לדף הבית" }).getAttribute("href")).toBe("/");
  });

  test("the home page opens once signed in", async () => {
    signedIn();
    renderAt("/");

    expect(await screen.findByRole("heading", { level: 1 })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /כניסה/ })).toBeNull();
  });
});
