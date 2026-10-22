// Tests for the upload rules in PLAN-DEV-B 3 (upload table): what each answer
// from /extract means, and when sending a file again is offered.
// Owner: A

import { describe, expect, test } from "vitest";
import {
  EXTRACT_URL,
  MAX_FILE_BYTES,
  NOT_SENT_CONNECTION,
  NOT_SENT_QUOTA,
  QUOTA_MESSAGE,
  SIGNED_OUT,
  addFiles,
  classify,
  sendFile,
  uploadReducer,
  type ExtractResponse,
  type UploadItem,
} from "./useExtract";

const pdf = (name = "a.pdf") => new File(["%PDF"], name, { type: "application/pdf" });

function response(over: Partial<ExtractResponse> = {}): ExtractResponse {
  return {
    files: [{ file_id: "f1", filename: "a.pdf", page_count: 2, status: "ok", error: null }],
    records: [],
    failed_pages: [],
    quota_exhausted: false,
    ...over,
  };
}

function queued(...names: string[]): UploadItem[] {
  return uploadReducer([], addFiles(names.map((n) => pdf(n))));
}

describe("classify", () => {
  test("200 is done", () => {
    expect(classify(200, response()).kind).toBe("done");
  });

  test("200 with quota_exhausted is partial: some pages were saved", () => {
    expect(classify(200, response({ quota_exhausted: true })).kind).toBe("partial");
  });

  test("a whole file that failed can be sent again", () => {
    const body = response({
      files: [{ file_id: "f1", filename: "a.pdf", page_count: 0, status: "error", error: { code: "EXTRACTION_FAILED", message: "הקריאה נכשלה" } }],
    });
    expect(classify(200, body)).toMatchObject({ kind: "failed", canRetry: true, message: "הקריאה נכשלה" });
  });

  test("INVALID_FILE is not offered again: it would fail again", () => {
    const body = response({
      files: [{ file_id: "f1", filename: "a.pdf", page_count: 0, status: "error", error: { code: "INVALID_FILE", message: "לא ניתן לקרוא את הקובץ" } }],
    });
    expect(classify(200, body)).toMatchObject({ kind: "failed", canRetry: false });
  });

  test("503 quota_exhausted: nothing was saved", () => {
    expect(classify(503, { type: "quota_exhausted", title: "נגמרה המכסה", status: 503 })).toEqual({
      kind: "quota",
      message: NOT_SENT_QUOTA,
    });
  });

  test("503 database_unavailable can be sent again: nothing was read", () => {
    expect(classify(503, { type: "database_unavailable", title: "מסד הנתונים לא זמין כרגע", status: 503 })).toEqual({
      kind: "failed",
      message: "מסד הנתונים לא זמין כרגע",
      canRetry: true,
    });
  });

  test("400 invalid_upload can be sent again: the server saved nothing", () => {
    const body = { type: "invalid_upload", title: "לא ניתן לקרוא את ההעלאה", status: 400, detail: "ייתכן שהיא פגומה. אפשר לשלוח שוב" };
    expect(classify(400, body)).toEqual({
      kind: "failed",
      message: "לא ניתן לקרוא את ההעלאה. ייתכן שהיא פגומה. אפשר לשלוח שוב",
      canRetry: true,
    });
  });

  test("413 too_many_pages suggests splitting the file", () => {
    const outcome = classify(413, { type: "too_many_pages", title: "יותר מדי עמודים", status: 413 });
    expect(outcome).toMatchObject({ kind: "failed", canRetry: false });
    expect(outcome.kind === "failed" && outcome.message).toContain("לחלק");
  });

  test("any other 5xx is interrupted: pages may already be saved", () => {
    expect(classify(502, null).kind).toBe("interrupted");
    expect(classify(503, { type: "other", title: "x", status: 503 }).kind).toBe("interrupted");
  });

  test("other 4xx show the server's message, without sending again", () => {
    expect(classify(413, { type: "request_too_large", title: "ההעלאה גדולה מ־60MB. אפשר לחלק אותה", status: 413 })).toEqual({
      kind: "failed",
      message: "ההעלאה גדולה מ־60MB. אפשר לחלק אותה",
      canRetry: false,
    });
    expect(classify(415, { type: "unsupported_media_type", title: "x", status: 415 })).toMatchObject({ canRetry: false });
  });
});

describe("sendFile", () => {
  test("posts one file as multipart 'files' to the relative URL", async () => {
    let url = "";
    let body: FormData | undefined;
    const fake = (async (u: string, init?: RequestInit) => {
      url = u;
      body = init?.body as FormData;
      return new Response(JSON.stringify(response()), { status: 200 });
    }) as typeof fetch;
    const outcome = await sendFile(pdf(), fake);
    expect(url).toBe(EXTRACT_URL);
    expect(body?.getAll("files")).toHaveLength(1);
    expect(outcome.kind).toBe("done");
  });

  test("a network error is interrupted", async () => {
    const fake = (async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;
    expect((await sendFile(pdf(), fake)).kind).toBe("interrupted");
  });

  test("a 200 that is not JSON is interrupted", async () => {
    const fake = (async () => new Response("<html>", { status: 200 })) as typeof fetch;
    expect((await sendFile(pdf(), fake)).kind).toBe("interrupted");
  });

  test("a 200 that is JSON of another shape is interrupted, not a stuck queue", async () => {
    // Before: classify threw, the promise rejected, and the queue never moved on.
    const fake = (async () => new Response('{"ok": true}', { status: 200 })) as typeof fetch;
    expect((await sendFile(pdf(), fake)).kind).toBe("interrupted");
  });

  test("401 is signed_out", async () => {
    const fake = (async () =>
      new Response('{"type": "unauthorized", "title": "x", "status": 401}', { status: 401 })) as typeof fetch;
    expect((await sendFile(pdf(), fake)).kind).toBe("signed_out");
  });
});

describe("uploadReducer", () => {
  test("files that are not PDF, JPG or PNG fail at once and are never sent", () => {
    const items = uploadReducer([], addFiles([pdf("a.pdf"), pdf("b.docx"), pdf("c.JPG")]));
    expect(items.map((i) => i.status)).toEqual(["queued", "failed", "queued"]);
    expect(items[1].canRetry).toBe(false);
  });

  test("files over 20MB fail at once and are never sent", () => {
    const big = new File([new Uint8Array(MAX_FILE_BYTES + 1)], "big.pdf");
    const [item] = uploadReducer([], addFiles([big]));
    expect(item).toMatchObject({ status: "failed", canRetry: false });
  });

  test("start marks the file as being sent", () => {
    let items = queued("a.pdf");
    items = uploadReducer(items, { type: "start", key: items[0].key });
    expect(items[0]).toMatchObject({ status: "sending" });
  });

  test("interrupted stops the queue: the waiting files are not sent and can be sent again", () => {
    let items = queued("a.pdf", "b.pdf");
    items = uploadReducer(items, { type: "finish", key: items[0].key, outcome: { kind: "interrupted" } });
    expect(items.map((i) => [i.status, i.canRetry])).toEqual([
      ["interrupted", false],
      ["not_sent", true],
    ]);
    expect(items[1].message).toBe(NOT_SENT_CONNECTION);
  });

  test("partial: the file is not offered again, and the files still waiting are not sent", () => {
    let items = queued("a.pdf", "b.pdf", "c.pdf");
    items = uploadReducer(items, { type: "start", key: items[0].key });
    items = uploadReducer(items, { type: "finish", key: items[0].key, outcome: { kind: "partial", result: response({ quota_exhausted: true }) } });
    expect(items.map((i) => [i.status, i.canRetry])).toEqual([
      ["partial", false],
      ["not_sent", true],
      ["not_sent", true],
    ]);
    expect(items[0].message).toBe(QUOTA_MESSAGE);
    expect(items[1].message).toBe(NOT_SENT_QUOTA);
  });

  test("503 quota: this file and the waiting ones can be sent again", () => {
    let items = queued("a.pdf", "b.pdf");
    items = uploadReducer(items, { type: "start", key: items[0].key });
    items = uploadReducer(items, { type: "finish", key: items[0].key, outcome: { kind: "quota", message: "נגמרה המכסה" } });
    expect(items.map((i) => [i.status, i.canRetry])).toEqual([
      ["not_sent", true],
      ["not_sent", true],
    ]);
  });

  test("files already read are left as they are when the quota runs out", () => {
    let items = queued("a.pdf", "b.pdf");
    items = uploadReducer(items, { type: "finish", key: items[0].key, outcome: { kind: "done", result: response() } });
    items = uploadReducer(items, { type: "finish", key: items[1].key, outcome: { kind: "quota", message: "x" } });
    expect(items[0].status).toBe("done");
  });

  test("an ended session stops the queue: this file and the waiting ones can be sent again", () => {
    let items = queued("a.pdf", "b.pdf");
    items = uploadReducer(items, { type: "start", key: items[0].key });
    items = uploadReducer(items, { type: "finish", key: items[0].key, outcome: { kind: "signed_out" } });
    expect(items.map((i) => [i.status, i.canRetry, i.message])).toEqual([
      ["not_sent", true, SIGNED_OUT],
      ["not_sent", true, SIGNED_OUT],
    ]);
  });

  test("the reducer gives the same result when React runs it twice", () => {
    // StrictMode runs reducers twice; the keys come from addFiles, outside.
    const action = addFiles([pdf("a.pdf"), pdf("b.pdf")]);
    expect(uploadReducer([], action)).toEqual(uploadReducer([], action));
  });

  test("interrupted is never offered again", () => {
    let items = queued("a.pdf");
    items = uploadReducer(items, { type: "finish", key: items[0].key, outcome: { kind: "interrupted" } });
    items = uploadReducer(items, { type: "retry", key: items[0].key });
    expect(items[0]).toMatchObject({ status: "interrupted", canRetry: false });
  });

  test("retry puts a file that can be sent again back in the queue", () => {
    let items = queued("a.pdf");
    items = uploadReducer(items, { type: "finish", key: items[0].key, outcome: { kind: "quota", message: "x" } });
    items = uploadReducer(items, { type: "retry", key: items[0].key });
    expect(items[0]).toMatchObject({ status: "queued", canRetry: false, message: undefined });
  });
});
