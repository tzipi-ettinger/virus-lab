// The overview numbers from GET /stats, loaded when the screen opens and on retry.
// Owner: B

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";

export type RecordStats = components["schemas"]["RecordStats"];

export type StatsState =
  | { status: "loading" }
  | { status: "ready"; stats: RecordStats }
  | { status: "error"; message: string };

export function useStats(): { state: StatsState; reload: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<StatsState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<RecordStats>("/api/v1/stats", { signal: controller.signal }).then(
      (stats) => setState({ status: "ready", stats }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof ApiError ? error.message : "הנתונים לא נטענו";
        setState({ status: "error", message });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  return { state, reload };
}
