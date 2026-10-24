// The record's history (D22): a button in the header's chips, and a window with
// every action, oldest first: who created, corrected, confirmed and approved the
// record, and when. Never the values (D13). Takes no height of its own, so the
// record page still fits the screen.
// Owner: B

import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { tRich } from "../../i18n/rich";
import { FIELD_COLUMNS } from "../review/reviewRows";
import { formatDateTime } from "./format";
import type { History, RecordEvent } from "./useRecordHistory";

const ACTION_TEXT: Record<RecordEvent["action"], string> = {
  created: t("record.history.created"),
  corrected: t("record.history.corrected"),
  confirmed: t("record.history.confirmed"),
  approved: t("record.history.approved"),
};

const CENTRAL_ITEM = /^central_numbers\[(\d+)\]$/;

/** "national_id" → ת״ז, "central_numbers[0]" → מספר מרכזי 1. */
function fieldTitle(field: string): string {
  const column = FIELD_COLUMNS.find((c) => c.name === field);
  if (column) return column.title;
  const item = CENTRAL_ITEM.exec(field);
  if (item) return t("fields.centralNumberN", { n: Number(item[1]) + 1 });
  return field === "central_numbers" ? t("fields.central_numbers") : field;
}

function eventText(event: RecordEvent): string {
  const what = ACTION_TEXT[event.action];
  return event.field ? t("record.history.onField", { what, field: fieldTitle(event.field) }) : what;
}

export function RecordHistory({ history }: { history: History }) {
  const [open, setOpen] = useState(false);
  const events = history && "events" in history ? history.events : null;
  const failed = history && "error" in history ? history.error : null;
  return (
    <>
      <button
        type="button"
        className="record-history-open"
        onClick={() => setOpen(true)}
        disabled={!events}
        title={failed ?? undefined}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
        {failed
          ? `⚠ ${t("record.history.button")}`
          : events
            ? t("record.history.buttonCount", { n: events.length })
            : t("record.history.button")}
      </button>
      {open && events && <HistoryWindow events={events} onClose={() => setOpen(false)} />}
    </>
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
      opener?.focus(); // back to the history button
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
          <h2 id="history-title">{t("record.history.title")}</h2>
          <button type="button" ref={closeRef} onClick={onClose} aria-label={t("common.close")}>
            ✕
          </button>
        </div>
        {events.length === 0 ? (
          <p className="history-note">{t("record.history.none")}</p>
        ) : (
          <ol className="history-list">
            {events.map((event, i) => (
              <li key={i}>
                <span className="history-what">{eventText(event)}</span>
                <span className="history-who">{tRich("record.history.by", { name: <bdi>{event.display_name}</bdi> })}</span>
                <time className="history-when" dateTime={event.at}>
                  {formatDateTime(event.at)}
                </time>
              </li>
            ))}
          </ol>
        )}
        <p className="history-note">{t("record.history.note")}</p>
      </div>
    </div>
  );
}
