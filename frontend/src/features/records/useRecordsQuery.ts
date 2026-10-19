// Loads the records page for the filters in the URL. A newer request cancels the
// one before it, so a fast typist never sees an older answer (PLAN-DEV-B 3.3).
// Owner: B

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";
import { listUrl, type RecordFilters } from "./filters";

export type RecordList = components["schemas"]["RecordList"];

export type RecordsQuery =
  | { status: "loading"; data: RecordList | null } // keeps the last answer on screen
  | { status: "ok"; data: RecordList }
  | { status: "error"; data: RecordList | null; message: string };

// The last answer, and which request it answers. Loading is derived: the current
// request has no answer yet.
type Answer = { request: string; data: RecordList | null; error: string | null };

export function useRecordsQuery(filters: RecordFilters): { query: RecordsQuery; reload: () => void } {
  const url = listUrl(filters);
  const [attempt, setAttempt] = useState(0);
  const request = `${url}#${attempt}`;
  const [answer, setAnswer] = useState<Answer>({ request: "", data: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<RecordList>(url, { signal: controller.signal }).then(
      (data) => setAnswer({ request, data, error: null }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof ApiError ? error.message : "משהו השתבש. נסי שוב";
        setAnswer((last) => ({ request, data: last.data, error: message }));
      },
    );
    return () => controller.abort();
  }, [url, request]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  let query: RecordsQuery;
  if (answer.request !== request) query = { status: "loading", data: answer.data };
  else if (answer.error !== null) query = { status: "error", data: answer.data, message: answer.error };
  else query = { status: "ok", data: answer.data as RecordList };
  return { query, reload };
}
