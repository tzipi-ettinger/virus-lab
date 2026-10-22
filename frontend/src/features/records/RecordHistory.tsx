// The record's history (D22): who created, corrected, confirmed and approved it,
// and when, oldest first. Never the values (D13). Closed until opened, so the
// record page still fits the screen. Loaded again after each change (version).
// Owner: B

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";
import { FIELD_COLUMNS } from "../review/reviewRows";
import { formatDateTime } from "./format";

type RecordEvent = components["schemas"]["RecordEvent"];

const ACTION_TEXT: Record<RecordEvent["action"], string> = {
  created: "נקלט",
  corrected: "תוקן",
  confirmed: "סומן כנבדק",
  approved: "אושר",
};

const CENTRAL_ITEM = /^central_numbers\[(\d+)\]$/;

/** "national_id" → ת״ז, "central_numbers[0]" → מספר מרכזי 1. */
function fieldTitle(field: string): string {
  const column = FIELD_COLUMNS.find((c) => c.name === field);
  if (column) return column.title;
  const item = CENTRAL_ITEM.exec(field);
  if (item) return `מספר מרכזי ${Number(item[1]) + 1}`;
  return field === "central_numbers" ? "מספרים מרכזיים" : field;
}

function eventText(event: RecordEvent): string {
  const what = ACTION_TEXT[event.action];
  return event.field ? `${what}: ${fieldTitle(event.field)}` : what;
}

type Loaded = { key: string; events: RecordEvent[] } | { key: string; error: string };

export function RecordHistory({ recordId, version }: { recordId: string; version: number }) {
  const key = `${recordId}#${version}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<RecordEvent[]>(`/api/v1/records/${encodeURIComponent(recordId)}/history`, {
      signal: controller.signal,
    }).then(
      (events) => setLoaded({ key, events }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setLoaded({ key, error: error instanceof ApiError ? error.message : "ההיסטוריה לא נטענה" });
      },
    );
    return () => controller.abort();
  }, [recordId, key]);

  const current = loaded?.key === key ? loaded : null;
  return (
    <details className="record-card record-history">
      <summary>
        היסטוריה{current && "events" in current && ` (${current.events.length})`}
      </summary>
      {current === null ? (
        <p className="record-history-note">טוען…</p>
      ) : "error" in current ? (
        <p className="record-history-note" role="alert">
          ⚠ {current.error}
        </p>
      ) : current.events.length === 0 ? (
        <p className="record-history-note">אין פעולות רשומות.</p>
      ) : (
        <ol className="record-history-list">
          {current.events.map((event, i) => (
            <li key={i}>
              <span className="record-history-what">{eventText(event)}</span>{" "}
              <span className="record-history-who">
                על ידי <bdi>{event.display_name}</bdi>
              </span>{" "}
              <time className="record-history-when" dateTime={event.at}>
                {formatDateTime(event.at)}
              </time>
            </li>
          ))}
        </ol>
      )}
    </details>
  );
}
