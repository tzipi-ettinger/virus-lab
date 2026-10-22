// Sends files to /extract one at a time and tracks each file (PLAN-DEV-B 3, upload table).
// The server answers 202 once it has the file and reads it in the background; the
// page then asks for the job until it is over.
// Owner: A

import { useEffect, useReducer, useRef } from "react";
import type { components } from "../../api/schema";

export type ExtractResponse = components["schemas"]["ExtractResponse"];
export type ExtractJob = components["schemas"]["ExtractJob"];
type Problem = components["schemas"]["Problem"];

// Relative, so the session cookie goes with it (#15).
export const EXTRACT_URL = "/api/v1/extract";
// The job reading a file that was sent: how far it got, then its answer.
export const jobUrl = (jobId: string) => `/api/v1/extract/jobs/${jobId}`;
export const POLL_MS = 1500;
// Asks in a row with no answer (about 30 seconds offline) before the file counts as
// interrupted. The server goes on reading it either way.
export const MAX_MISSED_POLLS = 20;

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
  // Date.now() when the request went out. A file can take minutes, so the panel
  // shows the time that passed, and the pages read so far.
  startedAt?: number;
  // From the job while it runs. total is 0 until the file is split.
  progress?: Progress;
}

export interface Progress {
  done: number;
  total: number;
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

// Problem types where the server says nothing was saved and sending again may work.
// database_unavailable and too_many_uploads are 503s sent before any page is read.
const RETRYABLE = new Set(["invalid_upload", "database_unavailable", "too_many_uploads"]);

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
  if (status >= 500 && !RETRYABLE.has(problem.type ?? "")) return { kind: "interrupted" };
  // Refused before anything was read: sending again after signing in is safe.
  if (status === 401) return { kind: "signed_out" };
  const parts = [problem.title || "הקובץ לא התקבל"];
  if (problem.detail) parts.push(problem.detail);
  if (problem.type === "too_many_pages") parts.push("אפשר לחלק את הקובץ לכמה קבצים");
  return { kind: "failed", message: parts.join(". "), canRetry: RETRYABLE.has(problem.type ?? "") };
}

// "8 of 26 pages read", once the server knows how many pages the file has.
// A one-page file shows only the clock: "0 of 1" says nothing.
export function progressText(progress: Progress | undefined): string | null {
  if (!progress || progress.total < 2) return null;
  return `נקראו ${progress.done} מתוך ${progress.total} עמודים`;
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function asJob(body: unknown): ExtractJob | null {
  const job = body as Partial<ExtractJob> | null;
  return job && typeof job.job_id === "string" && typeof job.status === "string" &&
    typeof job.done === "number" && typeof job.total === "number"
    ? (job as ExtractJob)
    : null;
}

// Classifies, and turns a body of the wrong shape (a proxy's or a login page's
// answer) into interrupted: pages may have been saved.
function safeClassify(status: number, body: unknown): Outcome {
  try {
    return classify(status, body);
  } catch {
    return { kind: "interrupted" };
  }
}

export interface SendOptions {
  fetchImpl?: typeof fetch;
  // Each count the job reports while it runs.
  onProgress?: (progress: Progress) => void;
  wait?: (ms: number) => Promise<void>;
}

export async function sendFile(file: File, options: SendOptions = {}): Promise<Outcome> {
  const { fetchImpl = fetch, onProgress, wait = sleep } = options;
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
  if (response.status !== 202) return safeClassify(response.status, json);
  const job = asJob(json);
  return job ? followJob(job, fetchImpl, wait, onProgress) : { kind: "interrupted" };
}

// Asks for the job every POLL_MS until it is over. The file is on the server by
// now: whatever happens here, nothing is sent again.
async function followJob(
  first: ExtractJob,
  fetchImpl: typeof fetch,
  wait: (ms: number) => Promise<void>,
  onProgress?: (progress: Progress) => void,
): Promise<Outcome> {
  let job = first;
  let missed = 0;
  for (;;) {
    if (job.status === "done") return job.result ? safeClassify(200, job.result) : { kind: "interrupted" };
    if (job.status === "failed") {
      return job.problem ? safeClassify(job.problem.status, job.problem) : { kind: "interrupted" };
    }
    onProgress?.({ done: job.done, total: job.total });
    await wait(POLL_MS);
    let next: ExtractJob | null = null;
    try {
      const response = await fetchImpl(jobUrl(job.job_id));
      // 404: the server restarted and forgot the job. 401: the session ended. Either
      // way the answer is lost, and the forms read so far are saved.
      if (response.status === 404 || response.status === 401) return { kind: "interrupted" };
      if (response.ok) next = asJob(await response.json());
    } catch {
      // Offline for a moment: ask again.
    }
    if (next) {
      job = next;
      missed = 0;
    } else if (++missed >= MAX_MISSED_POLLS) {
      return { kind: "interrupted" };
    }
  }
}

export type Action =
  | { type: "add"; files: { key: string; file: File }[] }
  | { type: "start"; key: string; at: number }
  | { type: "progress"; key: string; progress: Progress }
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
        i.key === action.key
          ? { ...i, status: "sending", message: undefined, startedAt: action.at, progress: undefined }
          : i,
      );
    case "progress":
      // A late answer for a file already finished is dropped.
      return items.map((i) =>
        i.key === action.key && i.status === "sending" ? { ...i, progress: action.progress } : i,
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

// Files still waiting or being sent. Closing or reloading the page now would drop
// the ones waiting without a word: only the file already sent is finished by the server.
export function hasUnsentFiles(items: UploadItem[]): boolean {
  return items.some((i) => i.status === "queued" || i.status === "sending");
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
    const onProgress = (progress: Progress) => dispatch({ type: "progress", key: next.key, progress });
    void sendFile(next.file, { onProgress }).then((outcome) => {
      sending.current = false;
      dispatch({ type: "finish", key: next.key, outcome });
      if ("result" in outcome && outcome.result) onResultRef.current(outcome.result);
    });
  }, [items]);

  // The browser's own "leave this page?" dialog, only while there is something to lose.
  const busy = hasUnsentFiles(items);
  useEffect(() => {
    if (!busy) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = ""; // older browsers show the dialog only when this is set
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);

  return {
    items,
    add: (files: File[]) => dispatch(addFiles(files)),
    retry: (key: string) => dispatch({ type: "retry", key }),
  };
}
