// Sends files to /extract one at a time and tracks each file (PLAN-DEV-B 3, upload table).
// Owner: A

import { useEffect, useReducer, useRef } from "react";
import type { components } from "../../api/schema";

export type ExtractResponse = components["schemas"]["ExtractResponse"];
type Problem = components["schemas"]["Problem"];

// Relative, so the session cookie goes with it (#15).
export const EXTRACT_URL = "/api/v1/extract";

const ACCEPTED = /\.(pdf|jpe?g|png)$/i;

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
}

// What one request for one file ended with. Sending again is offered only when
// the server said nothing was saved: a file whose pages were partly saved would
// get those records twice.
export type Outcome =
  | { kind: "done"; result: ExtractResponse }
  | { kind: "partial"; result: ExtractResponse }
  | { kind: "failed"; message: string; canRetry: boolean; result?: ExtractResponse }
  | { kind: "quota"; message: string }
  | { kind: "interrupted" };

export const QUOTA_MESSAGE = "המכסה היומית נגמרה";

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
    return { kind: "quota", message: problem.title || QUOTA_MESSAGE };
  }
  // Pages may already be saved when the server breaks or the connection drops.
  if (status >= 500) return { kind: "interrupted" };
  return { kind: "failed", message: problem.title || "הקובץ לא התקבל", canRetry: false };
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
  return classify(response.status, json);
}

export type Action =
  | { type: "add"; files: File[] }
  | { type: "start"; key: string }
  | { type: "finish"; key: string; outcome: Outcome }
  | { type: "retry"; key: string };

let nextKey = 0;

export function uploadReducer(items: UploadItem[], action: Action): UploadItem[] {
  switch (action.type) {
    case "add":
      return [
        ...items,
        ...action.files.map((file): UploadItem => {
          const key = `f${++nextKey}`;
          return ACCEPTED.test(file.name)
            ? { key, file, status: "queued", canRetry: false }
            : { key, file, status: "failed", canRetry: false, message: "סוג קובץ לא נתמך. אפשר להעלות PDF, JPG או PNG" };
        }),
      ];
    case "start":
      return items.map((i) => (i.key === action.key ? { ...i, status: "sending", message: undefined } : i));
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
      case "interrupted":
        return { ...i, status: "interrupted", canRetry: false };
    }
  };
  // The quota is daily: once it runs out, the files still waiting are not sent.
  const stop = outcome.kind === "partial" || outcome.kind === "quota";
  return items.map((i) => {
    if (i.key === key) return update(i);
    if (stop && i.status === "queued") return { ...i, status: "not_sent", canRetry: true, message: QUOTA_MESSAGE };
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
    dispatch({ type: "start", key: next.key });
    void sendFile(next.file).then((outcome) => {
      sending.current = false;
      dispatch({ type: "finish", key: next.key, outcome });
      if ("result" in outcome && outcome.result) onResultRef.current(outcome.result);
    });
  }, [items]);

  return {
    items,
    add: (files: File[]) => dispatch({ type: "add", files }),
    retry: (key: string) => dispatch({ type: "retry", key }),
  };
}
