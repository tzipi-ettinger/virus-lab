// @vitest-environment jsdom
// The "leave this page?" warning while files are still waiting or being sent.
// Owner: A

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { POLL_MS, hasUnsentFiles, uploadReducer, addFiles, useExtract, type ExtractResponse } from "./useExtract";

const pdf = (name = "a.pdf") => new File(["%PDF"], name, { type: "application/pdf" });

function leave(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented; // true: the browser asks before leaving
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("hasUnsentFiles", () => {
  test("waiting or sending files are unsent; finished ones are not", () => {
    const items = uploadReducer([], addFiles([pdf("a.pdf"), pdf("b.pdf")]));
    expect(hasUnsentFiles(items)).toBe(true);
    const done = items.map((i) => ({ ...i, status: "done" as const }));
    expect(hasUnsentFiles(done)).toBe(false);
    expect(hasUnsentFiles([])).toBe(false);
  });
});

describe("useExtract", () => {
  test("asks before leaving while a file is being sent, and not after", async () => {
    vi.useFakeTimers();
    let answer: (response: Response) => void = () => {};
    const posted = new Promise<Response>((resolve) => (answer = resolve));
    const running = { job_id: "job-1", status: "running", done: 0, total: 1, result: null, problem: null };
    let body: ExtractResponse | null = null;
    vi.stubGlobal("fetch", async (_url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? posted
        : new Response(JSON.stringify({ ...running, status: "done", done: 1, result: body }), { status: 200 }),
    );
    const { result } = renderHook(() => useExtract(() => {}));

    expect(leave()).toBe(false); // nothing added yet

    act(() => result.current.add([pdf()]));
    expect(leave()).toBe(true);

    body = {
      files: [{ file_id: "f1", filename: "a.pdf", page_count: 1, status: "ok", error: null }],
      records: [],
      failed_pages: [],
      quota_exhausted: false,
    };
    await act(async () => answer(new Response(JSON.stringify(running), { status: 202 })));
    expect(leave()).toBe(true); // still being read

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });

    expect(result.current.items[0].status).toBe("done");
    expect(leave()).toBe(false);
  });
});
