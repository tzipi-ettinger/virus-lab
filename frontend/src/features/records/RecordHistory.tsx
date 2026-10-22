// The record's history (D22), in the record's header: one line with who received
// it and who last changed it, and a window with every action, oldest first: who
// created, corrected, confirmed and approved it, and when. Never the values (D13).
// Loaded again after each change (version).
// Owner: B

import { useEffect, useRef, useState } from "react";
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

/** Who received the record and who last changed a field. The approval is in the status. */
function summary(events: RecordEvent[]): { label: string; name: string }[] {
  const created = events.find((e) => e.action === "created");
  const changed = events.findLast((e) => e.action === "corrected" || e.action === "confirmed");
  return [
    ...(created ? [{ label: "נקלט על ידי", name: created.display_name }] : []),
    ...(changed ? [{ label: "שונה לאחרונה על ידי", name: changed.display_name }] : []),
  ];
}

type Loaded = { key: string; events: RecordEvent[] } | { key: string; error: string };

export function RecordHistory({ recordId, version }: { recordId: string; version: number }) {
  const key = `${recordId}#${version}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [open, setOpen] = useState(false);

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
  const events = current && "events" in current ? current.events : null;
  return (
    <div className="record-who">
      {events && summary(events).map(({ label, name }) => (
        <span key={label}>
          {label} <bdi className="record-who-name">{name}</bdi>
        </span>
      ))}
      {current && "error" in current && <span role="alert">⚠ {current.error}</span>}
      <button type="button" className="record-who-open" onClick={() => setOpen(true)} disabled={!events}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
        היסטוריה מלאה{events && ` (${events.length})`}
      </button>
      {open && events && <HistoryWindow events={events} onClose={() => setOpen(false)} />}
    </div>
  );
}

function HistoryWindow({ events, onClose }: { events: RecordEvent[]; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus(); // back to "היסטוריה מלאה"
    };
  }, [onClose]);

  return (
    <div className="history-backdrop" onClick={onClose}>
      <div
        className="history-window"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="history-window-head">
          <h2 id="history-title">היסטוריית הרשומה</h2>
          <button type="button" ref={closeRef} onClick={onClose} aria-label="סגירה">
            ✕
          </button>
        </div>
        {events.length === 0 ? (
          <p className="history-note">אין פעולות רשומות.</p>
        ) : (
          <ol className="history-list">
            {events.map((event, i) => (
              <li key={i}>
                <span className="history-what">{eventText(event)}</span>
                <span className="history-who">
                  על ידי <bdi>{event.display_name}</bdi>
                </span>
                <time className="history-when" dateTime={event.at}>
                  {formatDateTime(event.at)}
                </time>
              </li>
            ))}
          </ol>
        )}
        <p className="history-note">רק מה נעשה ומתי, בלי הערכים עצמם.</p>
      </div>
    </div>
  );
}
