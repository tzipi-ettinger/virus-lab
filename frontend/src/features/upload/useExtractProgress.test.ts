// @vitest-environment jsdom
// "8 of 26 pages read" while a file is being sent.
// Owner: A

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  EXTRACT_URL,
  PROGRESS_POLL_MS,
  addFiles,
  progressText,
  progressUrl,
  readProgress,
  sendFile,
  uploadReducer,
  useExtract,
  type ExtractResponse,
} from "./useExtract";

const pdf = (name = "a.pdf") => new File(["%PDF"], name, { type: "application/pdf" });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const DONE: ExtractResponse = {
  files: [{ file_id: "f1", filename: "a.pdf", page_count: 5, status: "ok", error: null }],
  records: [],
  failed_pages: [],
  quota_exhausted: false,
};

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

describe("readProgress", () => {
  test("asks for the upload by its id", async () => {
    const fetchImpl = vi.fn(async () => json({ done: 2, total: 5 }));
    expect(await readProgress("upload-1234", fetchImpl as typeof fetch)).toEqual({ done: 2, total: 5 });
    expect(fetchImpl).toHaveBeenCalledWith(progressUrl("upload-1234"));
  });

  test("anything but a count is nothing to show, never an error", async () => {
    const answers = [
      async () => json({ type: "upload_not_found" }, 404),
      async () => json({ done: "2" }),
      async () => new Response("<html>", { status: 200 }),
      async () => {
        throw new TypeError("offline");
      },
    ];
    for (const answer of answers) {
      expect(await readProgress("upload-1234", answer as typeof fetch)).toBeNull();
    }
  });
});

describe("sendFile", () => {
  test("names the upload in X-Upload-Id when given one", async () => {
    const fetchImpl = vi.fn(async (_url: string, _init?: RequestInit) => json(DONE));
    await sendFile(pdf(), fetchImpl as unknown as typeof fetch, "upload-1234");
    expect(fetchImpl.mock.calls[0][1]?.headers).toEqual({ "X-Upload-Id": "upload-1234" });
  });
});

describe("uploadReducer", () => {
  test("progress shows only on the file being sent", () => {
    const [item] = uploadReducer([], addFiles([pdf()]));
    const progress = { done: 3, total: 9 };
    const sending = uploadReducer([item], { type: "start", key: item.key, at: 1 });
    expect(uploadReducer(sending, { type: "progress", key: item.key, progress })[0].progress).toEqual(progress);
    // A late answer, after the file finished, is dropped.
    const done = uploadReducer(sending, { type: "finish", key: item.key, outcome: { kind: "done", result: DONE } });
    expect(uploadReducer(done, { type: "progress", key: item.key, progress })[0].progress).toBeUndefined();
  });

  test("sending again starts the count over", () => {
    const [item] = uploadReducer([], addFiles([pdf()]));
    const counted = [{ ...item, status: "sending" as const, progress: { done: 4, total: 9 } }];
    expect(uploadReducer(counted, { type: "start", key: item.key, at: 2 })[0].progress).toBeUndefined();
  });
});

describe("useExtract", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  test("asks for the progress of the file being sent, and stops when it is answered", async () => {
    let answer: (response: Response) => void = () => {};
    let sentId: string | undefined;
    const progressCalls: string[] = [];
    vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
      if (url === EXTRACT_URL) {
        sentId = (init?.headers as Record<string, string> | undefined)?.["X-Upload-Id"];
        return new Promise<Response>((resolve) => (answer = resolve));
      }
      progressCalls.push(url);
      return Promise.resolve(json({ done: 2, total: 5 }));
    });
    const { result } = renderHook(() => useExtract(() => {}));

    act(() => result.current.add([pdf()]));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PROGRESS_POLL_MS);
    });

    expect(sentId).toBeTruthy();
    expect(progressCalls).toEqual([progressUrl(sentId!)]);
    expect(result.current.items[0].progress).toEqual({ done: 2, total: 5 });

    await act(async () => answer(json(DONE)));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PROGRESS_POLL_MS * 3);
    });

    expect(result.current.items[0].status).toBe("done");
    expect(progressCalls).toHaveLength(1);
  });
});
