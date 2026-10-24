// A record's history (D22) from GET /records/{id}/history, loaded again after each
// change (version). Never the values (D13).
// Owner: B

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";
import { t } from "../../i18n";

export type RecordEvent = components["schemas"]["RecordEvent"];

export type History = { events: RecordEvent[] } | { error: string } | null; // null: loading

export function useRecordHistory(recordId: string, version: number): History {
  const key = `${recordId}#${version}`;
  const [loaded, setLoaded] = useState<{ key: string; history: History }>({ key: "", history: null });

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<RecordEvent[]>(`/api/v1/records/${encodeURIComponent(recordId)}/history`, {
      signal: controller.signal,
    }).then(
      (events) => setLoaded({ key, history: { events } }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof ApiError ? error.message : t("record.history.loadFailed");
        setLoaded({ key, history: { error: message } });
      },
    );
    return () => controller.abort();
  }, [recordId, key]);

  return loaded.key === key ? loaded.history : null;
}

