// @vitest-environment jsdom
// "8 of 26 pages read" while the server reads a file in the background, and what
// happens when the job can't be asked for.
// Owner: A

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  EXTRACT_URL,
  MAX_MISSED_POLLS,
  POLL_MS,
  addFiles,
  jobUrl,
  progressText,
  sendFile,
  uploadReducer,
  useExtract,
  type ExtractJob,
  type ExtractResponse,
  type Progress,
} from "./useExtract";

const pdf = (name = "a.pdf") => new File(["%PDF"], name, { type: "application/pdf" });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const noWait = async () => {};

const DONE: ExtractResponse = {
  files: [{ file_id: "f1", filename: "a.pdf", page_count: 5, status: "ok", error: null }],
  records: [],
  failed_pages: [],
  quota_exhausted: false,
};

const job = (over: Partial<ExtractJob> = {}): ExtractJob => ({
  job_id: "job-1",
  status: "running",
  done: 0,
  total: 0,
  result: null,
  problem: null,
  ...over,
});

// The POST answers 202, then each GET gives the next answer in `polls`.
function server(...polls: (() => Response | Promise<Response>)[]) {
  const gets: string[] = [];
  const fetchImpl = (async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") return json(job(), 202);
    gets.push(url);
    const next = polls.shift();
    if (!next) throw new Error("asked once too often");
    return next();
  }) as typeof fetch;
  return { fetchImpl, gets };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("progressText", () => {
  test("pages read of the file's pages", () => {
    expect(progressText({ done: 8, total: 26 })).toBe("נקראו 8 מתוך 26 עמודים");
  });

  test("nothing before the file is split, or for one page", () => {
    expect(progressText(undefined)).toBeNull();
    expect(progressText({ done: 0, total: 0 })).toBeNull();
    expect(progressText({ done: 0, total: 1 })).toBeNull();
  });
});

describe("following the job", () => {
  test("reports each count until the job is done", async () => {
    const { fetchImpl, gets } = server(
      () => json(job({ done: 1, total: 5 })),
      () => json(job({ done: 4, total: 5 })),
      () => json(job({ status: "done", done: 5, total: 5, result: DONE })),
    );
    const seen: Progress[] = [];

    const outcome = await sendFile(pdf(), { fetchImpl, wait: noWait, onProgress: (p) => seen.push(p) });

    expect(outcome).toEqual({ kind: "done", result: DONE });
    expect(gets).toEqual([jobUrl("job-1"), jobUrl("job-1"), jobUrl("job-1")]);
    expect(seen).toEqual([
      { done: 0, total: 0 },
      { done: 1, total: 5 },
      { done: 4, total: 5 },
    ]);
  });

  test("a job the server forgot (a restart) or a session that ended is interrupted", async () => {
    for (const status of [404, 401]) {
      const { fetchImpl } = server(() => json({ type: "x", title: "x", status }, status));
      expect((await sendFile(pdf(), { fetchImpl, wait: noWait })).kind).toBe("interrupted");
    }
  });

  test("a moment offline is asked again, not given up", async () => {
    const { fetchImpl } = server(
      () => Promise.reject(new TypeError("offline")),
      () => json({ type: "x" }, 502),
      () => json(job({ status: "done", result: DONE })),
    );
    expect((await sendFile(pdf(), { fetchImpl, wait: noWait })).kind).toBe("done");
  });

  test("offline for too long is interrupted", async () => {
    const offline = Array.from({ length: MAX_MISSED_POLLS }, () => () => Promise.reject(new TypeError("offline")));
    const { fetchImpl, gets } = server(...offline);
    expect((await sendFile(pdf(), { fetchImpl, wait: noWait })).kind).toBe("interrupted");
    expect(gets).toHaveLength(MAX_MISSED_POLLS);
  });
});

describe("uploadReducer", () => {
  test("progress shows only on the file being sent", () => {
    const [item] = uploadReducer([], addFiles([pdf()]));
    const progress = { done: 3, total: 9 };
    const sending = uploadReducer([item], { type: "start", key: item.key });
    expect(uploadReducer(sending, { type: "progress", key: item.key, progress })[0].progress).toEqual(progress);
    // A late answer, after the file finished, is dropped.
    const done = uploadReducer(sending, { type: "finish", key: item.key, outcome: { kind: "done", result: DONE } });
    expect(uploadReducer(done, { type: "progress", key: item.key, progress })[0].progress).toBeUndefined();
  });

  test("sending again starts the count over", () => {
    const [item] = uploadReducer([], addFiles([pdf()]));
    const counted = [{ ...item, status: "sending" as const, progress: { done: 4, total: 9 } }];
    expect(uploadReducer(counted, { type: "start", key: item.key })[0].progress).toBeUndefined();
  });
});

describe("useExtract", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  test("shows the count while the job runs, and the result when it is done", async () => {
    let finished = false;
    const results: ExtractResponse[] = [];
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      if (url === EXTRACT_URL && init?.method === "POST") return json(job(), 202);
      return json(finished ? job({ status: "done", done: 5, total: 5, result: DONE }) : job({ done: 2, total: 5 }));
    });
    const { result } = renderHook(() => useExtract((r) => results.push(r)));

    act(() => result.current.add([pdf()]));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });

    expect(result.current.items[0]).toMatchObject({ status: "sending", progress: { done: 2, total: 5 } });

    finished = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });

    expect(result.current.items[0].status).toBe("done");
    expect(results).toEqual([DONE]);
  });
});
