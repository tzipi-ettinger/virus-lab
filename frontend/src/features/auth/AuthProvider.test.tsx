// @vitest-environment jsdom
// AuthProvider: /auth/me once at start, and any 401 signs out (PLAN-DEV-B 3.3).
// Owner: B

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { apiFetch } from "../../api/client";
import { useAuth } from "./authContext";
import { AuthProvider } from "./AuthProvider";

const DANA = { id: "u1", username: "dana", display_name: "דנה" };

function json(status: number, body: unknown) {
  const type = status < 400 ? "application/json" : "application/problem+json";
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": type } });
}

function Show() {
  const { state } = useAuth();
  return <p>{state.status === "signed_in" ? `שלום ${state.user.display_name}` : state.status}</p>;
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

function renderProvider() {
  render(
    <AuthProvider>
      <Show />
    </AuthProvider>,
  );
}

describe("AuthProvider", () => {
  test("a valid session shows the user", async () => {
    fetchMock.mockResolvedValue(json(200, DANA));
    renderProvider();

    expect(await screen.findByText("שלום דנה")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/auth/me");
  });

  test("no session is signed out", async () => {
    fetchMock.mockResolvedValue(json(401, { type: "unauthenticated", title: "x", status: 401 }));
    renderProvider();

    expect(await screen.findByText("signed_out")).toBeTruthy();
  });

  test("a server that doesn't answer is an error, not signed out", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderProvider();

    expect(await screen.findByText("error")).toBeTruthy();
  });

  test("a 401 from any later call signs out", async () => {
    fetchMock.mockResolvedValueOnce(json(200, DANA));
    renderProvider();
    await screen.findByText("שלום דנה");

    fetchMock.mockResolvedValueOnce(json(401, { type: "unauthenticated", title: "x", status: 401 }));
    await act(() => apiFetch("/api/v1/records").catch(() => {}));

    expect(screen.getByText("signed_out")).toBeTruthy();
  });
});
