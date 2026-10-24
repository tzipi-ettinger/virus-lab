// Drag & drop, PDF + images, progress per file, failed pages (PLAN-DEV-B 3, upload table).
// Owner: A

import { useEffect, useRef, useState, type DragEvent } from "react";
import { t } from "../../i18n";
import { tRich } from "../../i18n/rich";
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
  // Called once per file, as soon as the server has finished reading it.
  onResult: (result: ExtractResponse) => void;
  // Called when files start or stop being sent: true while any is queued or sending.
  onBusyChange?: (busy: boolean) => void;
}

const STATUS_TEXT: Record<FileStatus, string> = {
  queued: t("upload.status.queued"),
  sending: t("upload.status.sending"),
  done: t("upload.status.done"),
  partial: t("upload.status.partial"),
  failed: t("upload.status.failed"),
  not_sent: t("upload.status.not_sent"),
  interrupted: t("upload.status.interrupted"),
};

function recordsText(n: number) {
  return n === 1 ? t("upload.recordsOne") : t("upload.recordsMany", { n });
}

// The file's kind, for the small colored badge beside its name.
function fileKind(name: string): "pdf" | "jpg" | "png" | "file" {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "pdf";
  if (ext === "jpg" || ext === "jpeg") return "jpg";
  if (ext === "png") return "png";
  return "file";
}

function FileKind({ name }: { name: string }) {
  const kind = fileKind(name);
  return (
    <span className={`upload-name-kind is-${kind}`} aria-hidden="true">
      {kind === "file" ? "" : kind.toUpperCase()}
    </span>
  );
}

const TIPS = [
  { kind: "blue", title: t("upload.tips.manyTitle"), text: t("upload.tips.manyText"), icon: <><rect x="7" y="3" width="13" height="15" rx="2" /><path d="M4 7v12a2 2 0 0 0 2 2h10" /></> },
  { kind: "teal", title: t("upload.tips.handTitle"), text: t("upload.tips.handText"), icon: <><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="m13 7 4 4" /></> },
  { kind: "green", title: t("upload.tips.reviewTitle"), text: t("upload.tips.reviewText"), icon: <path d="M5 12.5 10 17l9-10" /> },
];

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
    if (pages) parts.push(pages === 1 ? t("upload.pagesOne") : t("upload.pagesMany", { n: pages }));
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
    <section className={items.length > 0 ? "upload has-files" : "upload"} aria-labelledby="upload-title">
      <div className="upload-hero">
        <h2 id="upload-title" className="upload-title">
          {tRich("upload.title", { forms: <span className="upload-title-accent">{t("upload.titleAccent")}</span> })}
        </h2>
        <p className="upload-lead">{t("upload.lead")}</p>
      </div>

      <div className="upload-card">
        <div
          className={dragging ? "upload-drop is-dragging" : "upload-drop"}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <span className="upload-drop-ring" aria-hidden="true">
            <svg className="upload-drop-icon" width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 16V4" />
              <path d="m6 10 6-6 6 6" />
              <path d="M4 20h16" />
            </svg>
          </span>
          <p className="upload-drop-text">{t("upload.dropText")}</p>
          <p className="upload-drop-hint">{t("upload.dropHint")}</p>
          <ul className="upload-kinds" aria-label={t("upload.kinds")}>
            <li className="upload-kind is-pdf">PDF</li>
            <li className="upload-kind is-jpg">JPG</li>
            <li className="upload-kind is-png">PNG</li>
          </ul>
          <button type="button" className="upload-button" onClick={() => input.current?.click()}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
              <path d="M14 3v5h5" />
              <path d="M12 12v6M9 15h6" />
            </svg>
            {t("upload.choose")}
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
      </div>

      {items.length === 0 && (
        <ul className="upload-tips">
          {TIPS.map((tip) => (
            <li key={tip.title} className="upload-tip">
              <span className={`upload-tip-icon is-${tip.kind}`}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  {tip.icon}
                </svg>
              </span>
              <span className="upload-tip-text">
                <strong>{tip.title}</strong>
                <span>{tip.text}</span>
              </span>
            </li>
          ))}
        </ul>
      )}

      {interrupted && (
        <p className="upload-alert" role="alert">
          {tRich("upload.interrupted", { link: <a href="/records">{t("upload.interruptedLink")}</a> })}
        </p>
      )}

      {items.length > 0 && (
        <div className="upload-files">
          <div className="upload-files-head">
            <h3 className="upload-files-title">{t("upload.filesTitle")}</h3>
            <p className="upload-summary">
              {t("upload.summary", { finished, total: items.length, records: recordsText(records) })}
            </p>
          </div>
          <ul className="upload-list" aria-live="polite">
            {items.map((item) => (
              <li key={item.key} className={`upload-item is-${item.status}`}>
                <span className="upload-status">
                  <StatusIcon status={item.status} />
                  {STATUS_TEXT[item.status]}
                </span>
                <span className="upload-name">
                  <FileKind name={item.file.name} />
                  <bdi>{item.file.name}</bdi>
                </span>
                <span className="upload-detail">
                  {item.status === "sending" ? (
                    <Sending progress={item.progress} />
                  ) : (
                    detail(item)
                  )}
                </span>
                {item.canRetry && (
                  <button type="button" className="upload-retry" onClick={() => retry(item.key)}>
                    {t("common.retry")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {failedPages.length > 0 && (
        <div className="upload-failed" role="region" aria-labelledby="upload-failed-title">
          <h3 id="upload-failed-title" className="upload-failed-title">
            {t("upload.failedPages", { n: failedPages.length })}
          </h3>
          <ul>
            {failedPages.map((p) => (
              <li key={`${p.file_id}-${p.page_number}`}>
                {tRich("upload.failedPage", {
                  file: <bdi>{p.source_file}</bdi>,
                  page: p.page_number,
                  message: p.error.message,
                })}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export default UploadPanel;
