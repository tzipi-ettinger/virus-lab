// Sends files to /extract one at a time and tracks each file (PLAN-DEV-B 3, upload table).
// Owner: A

import { useEffect, useReducer, useRef } from "react";
import type { components } from "../../api/schema";

export type ExtractResponse = components["schemas"]["ExtractResponse"];
type Problem = components["schemas"]["Problem"];

// Relative, so the session cookie goes with it (#15).
export const EXTRACT_URL = "/api/v1/extract";

const ACCEPTED = /\.(pdf|jpe?g|png)$/i;
// MAX_FILE_MB in backend/app/settings.py (decimal MB, like the server).
export const MAX_FILE_BYTES = 20_000_000;

export type FileStatus =
  | "queued"
  | "sending"
  | "done"
  | "partial"
  | "failed"
  | "not_sent"
  | "interrupted";

export interface UploadItem {
  key: string;
  file: File;
  status: FileStatus;
  message?: string;
  canRetry: boolean;
  result?: ExtractResponse;
  // Date.now() when the request went out. The server answers only at the end of
  // the file, so the panel shows the time that passed instead of a percentage.
  startedAt?: number;
}

// What one request for one file ended with. Sending again is offered only when
// the server said nothing was saved: a file whose pages were partly saved would
// get those records twice.
export type Outcome =
  | { kind: "done"; result: ExtractResponse }
  | { kind: "partial"; result: ExtractResponse }
  | { kind: "failed"; message: string; canRetry: boolean; result?: ExtractResponse }
  | { kind: "quota"; message: string }
  | { kind: "signed_out" }
  | { kind: "interrupted" };

export const QUOTA_MESSAGE = "המכסה היומית נגמרה";
// Nothing from these files was saved, so sending them again is safe - once the quota is back.
export const NOT_SENT_QUOTA = "המכסה היומית נגמרה. אפשר לשלוח שוב כשהמכסה מתחדשת";
export const NOT_SENT_CONNECTION = "ההעלאה נעצרה כי החיבור נקטע";
export const SIGNED_OUT = "צריך להתחבר מחדש, ואז לשלוח שוב";

// 4xx types where the server says nothing was saved and sending again may work.
const RETRYABLE_4XX = new Set(["invalid_upload"]);

export function classify(status: number, body: unknown): Outcome {
  if (status === 200) {
    const result = body as ExtractResponse;
    if (result.quota_exhausted) return { kind: "partial", result };
    const file = result.files[0];
    if (file?.status === "error") {
      return {
        kind: "failed",
        message: file.error?.message ?? "הקריאה נכשלה",
        canRetry: file.error?.code !== "INVALID_FILE",
        result,
      };
    }
    return { kind: "done", result };
  }
  const problem = (body ?? {}) as Partial<Problem>;
  if (status === 503 && problem.type === "quota_exhausted") {
    return { kind: "quota", message: NOT_SENT_QUOTA };
  }
  // Pages may already be saved when the server breaks or the connection drops.
  if (status >= 500) return { kind: "interrupted" };
  // Refused before anything was read: sending again after signing in is safe.
  if (status === 401) return { kind: "signed_out" };
  const parts = [problem.title || "הקובץ לא התקבל"];
  if (problem.detail) parts.push(problem.detail);
  if (problem.type === "too_many_pages") parts.push("אפשר לחלק את הקובץ לכמה קבצים");
  return { kind: "failed", message: parts.join(". "), canRetry: RETRYABLE_4XX.has(problem.type ?? "") };
}

export async function sendFile(file: File, fetchImpl: typeof fetch = fetch): Promise<Outcome> {
  const body = new FormData();
  body.append("files", file);
  let response: Response;
  try {
    response = await fetchImpl(EXTRACT_URL, { method: "POST", body });
  } catch {
    return { kind: "interrupted" };
  }
  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    if (response.ok) return { kind: "interrupted" };
  }
  try {
    return classify(response.status, json);
  } catch {
    // A 200 that is JSON but not an ExtractResponse (a proxy's or a login page's
    // answer). Pages may have been saved, so the same as a dropped connection.
    return { kind: "interrupted" };
  }
}

export type Action =
  | { type: "add"; files: { key: string; file: File }[] }
  | { type: "start"; key: string; at: number }
  | { type: "finish"; key: string; outcome: Outcome }
  | { type: "retry"; key: string };

let nextKey = 0;

// Makes the keys here, not in the reducer: React may run a reducer twice
// (StrictMode), and a reducer must give the same result both times.
export function addFiles(files: File[]): Action {
  return { type: "add", files: files.map((file) => ({ key: `f${++nextKey}`, file })) };
}

export function uploadReducer(items: UploadItem[], action: Action): UploadItem[] {
  switch (action.type) {
    case "add":
      return [
        ...items,
        ...action.files.map(({ key, file }): UploadItem => {
          if (!ACCEPTED.test(file.name)) {
            return { key, file, status: "failed", canRetry: false, message: "סוג קובץ לא נתמך. אפשר להעלות PDF, JPG או PNG" };
          }
          if (file.size > MAX_FILE_BYTES) {
            return { key, file, status: "failed", canRetry: false, message: "הקובץ גדול מ־20MB. אפשר לחלק אותו" };
          }
          return { key, file, status: "queued", canRetry: false };
        }),
      ];
    case "start":
      return items.map((i) =>
        i.key === action.key ? { ...i, status: "sending", message: undefined, startedAt: action.at } : i,
      );
    case "retry":
      return items.map((i) =>
        i.key === action.key && i.canRetry ? { ...i, status: "queued", canRetry: false, message: undefined } : i,
      );
    case "finish":
      return finish(items, action.key, action.outcome);
  }
}

function finish(items: UploadItem[], key: string, outcome: Outcome): UploadItem[] {
  const update = (i: UploadItem): UploadItem => {
    switch (outcome.kind) {
      case "done":
        return { ...i, status: "done", canRetry: false, result: outcome.result };
      case "partial":
        return { ...i, status: "partial", canRetry: false, result: outcome.result, message: QUOTA_MESSAGE };
      case "failed":
        return { ...i, status: "failed", canRetry: outcome.canRetry, result: outcome.result, message: outcome.message };
      case "quota":
        return { ...i, status: "not_sent", canRetry: true, message: outcome.message };
      case "signed_out":
        return { ...i, status: "not_sent", canRetry: true, message: SIGNED_OUT };
      case "interrupted":
        return { ...i, status: "interrupted", canRetry: false };
    }
  };
  // The quota is daily, and a dropped connection or an ended session will most
  // likely fail the next file too: the files still waiting are not sent. Nothing
  // of theirs was saved, so they can be sent again.
  const stopMessage =
    outcome.kind === "partial" || outcome.kind === "quota"
      ? NOT_SENT_QUOTA
      : outcome.kind === "interrupted"
        ? NOT_SENT_CONNECTION
        : outcome.kind === "signed_out"
          ? SIGNED_OUT
          : null;
  return items.map((i) => {
    if (i.key === key) return update(i);
    if (stopMessage && i.status === "queued") return { ...i, status: "not_sent", canRetry: true, message: stopMessage };
    return i;
  });
}

// Every 200 answer goes to onResult as soon as it arrives, so the review table
// fills in while the other files are still being read.
export function useExtract(onResult: (result: ExtractResponse) => void) {
  const [items, dispatch] = useReducer(uploadReducer, []);
  const sending = useRef(false);
  const onResultRef = useRef(onResult);

  useEffect(() => {
    onResultRef.current = onResult;
  });

  useEffect(() => {
    if (sending.current) return;
    const next = items.find((i) => i.status === "queued");
    if (!next) return;
    sending.current = true;
    dispatch({ type: "start", key: next.key, at: Date.now() });
    void sendFile(next.file).then((outcome) => {
      sending.current = false;
      dispatch({ type: "finish", key: next.key, outcome });
      if ("result" in outcome && outcome.result) onResultRef.current(outcome.result);
    });
  }, [items]);

  return {
    items,
    add: (files: File[]) => dispatch(addFiles(files)),
    retry: (key: string) => dispatch({ type: "retry", key }),
  };
}
