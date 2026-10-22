// Drag & drop, PDF + images, progress per file, failed pages (PLAN-DEV-B 3, upload table).
// Owner: A

import { useEffect, useRef, useState, type DragEvent } from "react";
import {
  hasUnsentFiles,
  progressText,
  useExtract,
  type ExtractResponse,
  type FileStatus,
  type Progress,
  type UploadItem,
} from "./useExtract";
import "./UploadPanel.css";

interface UploadPanelProps {
  // Called once per file, as soon as that file's 200 answer arrives.
  onResult: (result: ExtractResponse) => void;
  // Called when files start or stop being sent: true while any is queued or sending.
  onBusyChange?: (busy: boolean) => void;
}

const STATUS_TEXT: Record<FileStatus, string> = {
  queued: "ממתין",
  sending: "נקרא…",
  done: "נקרא",
  partial: "נקרא חלקית",
  failed: "נכשל",
  not_sent: "לא נשלח",
  interrupted: "החיבור נקטע",
};

function recordsText(n: number) {
  return n === 1 ? "רשומה אחת" : `${n} רשומות`;
}

function StatusIcon({ status }: { status: FileStatus }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  switch (status) {
    case "done":
      return <svg {...common}><path d="M5 12.5 10 17l9-10" /></svg>;
    case "sending":
      return <svg {...common} className="upload-spin"><path d="M12 3a9 9 0 1 0 9 9" /></svg>;
    case "queued":
      return <svg {...common}><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2" /></svg>;
    case "partial":
    case "not_sent":
      return <svg {...common}><path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4M12 17v.5" /></svg>;
    case "failed":
    case "interrupted":
      return <svg {...common}><circle cx="12" cy="12" r="9" /><path d="m9 9 6 6M15 9l-6 6" /></svg>;
  }
}

// The pages read so far and a bar; no clock (22.10). Hidden from screen readers:
// in the aria-live list, the page count would be read out at every change.
function Sending({ progress }: { progress?: Progress }) {
  const pages = progressText(progress);
  if (!pages || !progress) return null;
  return (
    <span className="upload-sending" aria-hidden="true">
      {pages}
      <span className="upload-progress">
        <span className="upload-progress-bar" style={{ inlineSize: `${(100 * progress.done) / progress.total}%` }} />
      </span>
    </span>
  );
}

function detail(item: UploadItem) {
  const r = item.result;
  const parts: string[] = [];
  if (r && (item.status === "done" || item.status === "partial")) {
    const pages = r.files[0]?.page_count;
    if (pages) parts.push(pages === 1 ? "עמוד אחד" : `${pages} עמודים`);
    parts.push(recordsText(r.records.length));
  }
  if (item.message) parts.push(item.message);
  return parts.join(" · ");
}

export function UploadPanel({ onResult, onBusyChange }: UploadPanelProps) {
  const { items, add, retry } = useExtract(onResult);
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const isBusy = hasUnsentFiles(items);

  useEffect(() => {
    onBusyChange?.(isBusy);
  }, [isBusy, onBusyChange]);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    add(Array.from(e.dataTransfer.files));
  };

  const finished = items.filter((i) => i.status !== "queued" && i.status !== "sending").length;
  const records = items.reduce((n, i) => n + (i.result?.records.length ?? 0), 0);
  const failedPages = items.flatMap((i) => i.result?.failed_pages ?? []);
  const interrupted = items.some((i) => i.status === "interrupted");

  return (
    <section className="upload" aria-labelledby="upload-title">
      <h2 id="upload-title" className="upload-title">העלאת טפסים</h2>

      <div
        className={dragging ? "upload-drop is-dragging" : "upload-drop"}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <svg className="upload-drop-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 16V4" />
          <path d="m6 10 6-6 6 6" />
          <path d="M4 20h16" />
        </svg>
        <p className="upload-drop-text">גררי לכאן קבצי PDF או תמונות</p>
        <p className="upload-drop-hint">JPG, PNG או PDF · קובץ אחד או כמה בבת אחת</p>
        <button type="button" className="upload-button" onClick={() => input.current?.click()}>
          בחירת קבצים
        </button>
        <input
          ref={input}
          type="file"
          multiple
          accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          className="upload-input"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            add(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
      </div>

      {interrupted && (
        <p className="upload-alert" role="alert">
          החיבור נקטע. ייתכן שחלק מהעמודים כבר נשמרו. בדקי <a href="/records">במסך הרשומות</a> לפני שמעלים שוב.
        </p>
      )}

      {items.length > 0 && (
        <>
          <p className="upload-summary">
            {finished} מתוך {items.length} קבצים · נוצרו {recordsText(records)}
          </p>
          <ul className="upload-list" aria-live="polite">
            {items.map((item) => (
              <li key={item.key} className={`upload-item is-${item.status}`}>
                <span className="upload-status">
                  <StatusIcon status={item.status} />
                  {STATUS_TEXT[item.status]}
                </span>
                <span className="upload-name"><bdi>{item.file.name}</bdi></span>
                <span className="upload-detail">
                  {item.status === "sending" ? (
                    <Sending progress={item.progress} />
                  ) : (
                    detail(item)
                  )}
                </span>
                {item.canRetry && (
                  <button type="button" className="upload-retry" onClick={() => retry(item.key)}>
                    נסי שוב
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {failedPages.length > 0 && (
        <div className="upload-failed" role="region" aria-labelledby="upload-failed-title">
          <h3 id="upload-failed-title" className="upload-failed-title">
            עמודים שלא נקראו ({failedPages.length})
          </h3>
          <ul>
            {failedPages.map((p) => (
              <li key={`${p.file_id}-${p.page_number}`}>
                <bdi>{p.source_file}</bdi>, עמוד {p.page_number}: {p.error.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export default UploadPanel;
