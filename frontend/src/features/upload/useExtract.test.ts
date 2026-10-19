// Tests for the upload rules in PLAN-DEV-B 3 (upload table): what each answer
// from /extract means, and when sending a file again is offered.
// Owner: A

import { describe, expect, test } from "vitest";
import {
  EXTRACT_URL,
  QUOTA_MESSAGE,
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
  return uploadReducer([], { type: "add", files: names.map((n) => pdf(n)) });
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
      message: "נגמרה המכסה",
    });
  });

  test("any other 5xx is interrupted: pages may already be saved", () => {
    expect(classify(502, null).kind).toBe("interrupted");
    expect(classify(503, { type: "other", title: "x", status: 503 }).kind).toBe("interrupted");
  });

  test("4xx shows the server's message, without sending again", () => {
    expect(classify(413, { type: "too_many_pages", title: "יותר מדי עמודים", status: 413 })).toEqual({
      kind: "failed",
      message: "יותר מדי עמודים",
      canRetry: false,
    });
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
});

describe("uploadReducer", () => {
  test("files that are not PDF, JPG or PNG fail at once and are never sent", () => {
    const items = uploadReducer([], { type: "add", files: [pdf("a.pdf"), pdf("b.docx"), pdf("c.JPG")] });
    expect(items.map((i) => i.status)).toEqual(["queued", "failed", "queued"]);
    expect(items[1].canRetry).toBe(false);
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
    expect(items[1].message).toBe(QUOTA_MESSAGE);
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
