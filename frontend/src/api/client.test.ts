// The API client: what each kind of answer becomes (PLAN-DEV-B 3.4, 3.5).
// Owner: B

import { afterEach, describe, expect, test, vi } from "vitest";
import { ApiError, NETWORK_ERROR, apiFetch, onUnauthorized } from "./client";

function answer(status: number, body?: unknown, contentType = "application/json") {
  const init = { status, headers: { "Content-Type": contentType } };
  const payload = body === undefined ? null : typeof body === "string" ? body : JSON.stringify(body);
  return vi.fn<typeof fetch>().mockResolvedValue(new Response(payload, init));
}

/** The ApiError a call ends with (the test fails if it succeeds). */
function failure(call: Promise<unknown>): Promise<ApiError> {
  return call.then(
    () => {
      throw new Error("expected the call to fail");
    },
    (error: ApiError) => error,
  );
}

const problem = (status: number, type: string, extra: object = {}) =>
  answer(status, { type, title: "כותרת", status, ...extra }, "application/problem+json");

describe("apiFetch", () => {
  let stop = () => {};
  afterEach(() => stop());

  test("sends JSON with the session cookie and returns the JSON answer", async () => {
    const fetchImpl = answer(200, { ok: true });

    const result = await apiFetch<{ ok: boolean }>("/api/v1/records/approve", {
      method: "POST",
      body: { items: [] },
      fetchImpl,
    });

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("/api/v1/records/approve");
    expect(init).toMatchObject({ method: "POST", credentials: "same-origin", body: '{"items":[]}' });
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
  });

  test("204 resolves to undefined", async () => {
    expect(await apiFetch("/api/v1/auth/logout", { method: "POST", fetchImpl: answer(204) })).toBeUndefined();
  });

  test("a problem answer becomes an ApiError with its type and blocking fields", async () => {
    const fetchImpl = problem(409, "review_required", { blocking_fields: ["national_id"] });

    const error = await failure(apiFetch("/api/v1/records/r1/approve", { method: "POST", fetchImpl }));

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, type: "review_required", message: "כותרת" });
    expect(error.blockingFields).toEqual(["national_id"]);
  });

  test("an answer that isn't a problem still becomes an ApiError", async () => {
    const error = await failure(apiFetch("/x", { fetchImpl: answer(502, "<html>", "text/html") }));

    expect(error).toMatchObject({ status: 502, type: "http_error" });
    expect(error.message).toContain("502");
  });

  test("no connection becomes a network_error with a Hebrew message", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("Failed to fetch"));

    const error = await failure(apiFetch("/x", { fetchImpl }));

    expect(error).toMatchObject({ status: 0, type: "network_error", message: NETWORK_ERROR });
  });

  test("a cancelled request is passed on as it is, not shown as an error", async () => {
    const controller = new AbortController();
    controller.abort();
    const aborted = new DOMException("aborted", "AbortError");
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(aborted);

    await expect(apiFetch("/x", { fetchImpl, signal: controller.signal })).rejects.toBe(aborted);
  });

  test("a 401 calls the sign-in handler", async () => {
    const handler = vi.fn();
    stop = onUnauthorized(handler);

    await apiFetch("/api/v1/records", { fetchImpl: problem(401, "unauthenticated") }).catch(() => {});

    expect(handler).toHaveBeenCalledOnce();
  });

  test("a failed login does not: the login page shows that error itself", async () => {
    const handler = vi.fn();
    stop = onUnauthorized(handler);

    await apiFetch("/api/v1/auth/login", { method: "POST", fetchImpl: problem(401, "unauthenticated") }).catch(
      () => {},
    );

    expect(handler).not.toHaveBeenCalled();
  });
});
