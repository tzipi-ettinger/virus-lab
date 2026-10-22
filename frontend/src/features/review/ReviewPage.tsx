// Upload and review screen: the one place that holds the records and the selected
// row. UploadPanel (A) sends records up; the list picks one and RecordPanel opens it,
// with A's DocumentPreview inside (#32). The selection is kept as an id, so a newer
// copy of the record shows.
// Two steps on one screen: the upload first, then, once every file is read, the list
// and the open record, sized to the window. Both stay mounted, so files keep being
// read while the list is shown, and the list keeps its state while uploading more.
// Approve and delete wait a few seconds with "undo" (useUndo), and the next record
// to fix opens at once.
// Owner: B

import { useCallback, useState } from "react";
import { useRecordMutations, type ApiRecord } from "./recordMutations";
import { UploadPanel } from "../upload/UploadPanel";
import { RecordPanel } from "./RecordPanel";
import { ReviewTable } from "./ReviewTable";
import { findRecord, mergeRecords, nextAfter, replaceRecords } from "./reviewRows";
import { UndoToast } from "./UndoToast";
import { useUndo } from "./useUndo";
import "./ReviewPage.css";

// "auto": the list once there are records and nothing is being read; the others
// are the user's own pick, until new files are added.
type View = "auto" | "upload" | "review";

export function ReviewPage() {
  const [allRecords, setRecords] = useState<ApiRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<View>("auto");
  // What waits for its "undo": an approve shows as approved, a delete is hidden.
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const records = deletingId ? allRecords.filter((r) => r.record_id !== deletingId) : allRecords;
  // Nothing picked (yet, or the picked one was deleted): the first record is open,
  // so the panel isn't empty while there is something to review.
  const selected = findRecord(records, selectedId) ?? records[0] ?? null;
  // Stable, so the save functions keep their identity between renders.
  const onRecords = useCallback(
    (changed: ApiRecord[]) => setRecords((current) => replaceRecords(current, changed)),
    [],
  );
  const { approve, remove } = useRecordMutations(onRecords);
  const undo = useUndo();
  const onRemoved = useCallback((recordId: string) => {
    setRecords((current) => current.filter((r) => r.record_id !== recordId));
    setSelectedId((picked) => (picked === recordId ? null : picked));
  }, []);
  const onBusyChange = useCallback((sending: boolean) => {
    setBusy(sending);
    // New files: when they are all read, move on to the list.
    if (sending) setView("auto");
  }, []);
  const showReview = view === "review" || (view === "auto" && !busy && records.length > 0);
  const approved = records.filter((r) => r.status === "approved" || r.record_id === approvingId).length;

  /** Approved on screen now, sent once its "undo" runs out; the next one to fix opens. */
  function approveLater(record: ApiRecord) {
    const next = nextAfter(records, record.record_id);
    setApprovingId(record.record_id);
    if (next) setSelectedId(next.record_id);
    undo.schedule({
      text: `${recordName(record)} אושרה`,
      run: async () => {
        const message = await approve(record);
        setApprovingId((id) => (id === record.record_id ? null : id));
        return message;
      },
      onUndo: () => {
        setApprovingId(null);
        setSelectedId(record.record_id);
      },
      onFail: () => setSelectedId(record.record_id),
    });
  }

  /** Off the list now, deleted once its "undo" runs out; the next one opens. */
  function deleteLater(record: ApiRecord) {
    const next = nextAfter(records, record.record_id);
    setDeletingId(record.record_id);
    setSelectedId(next?.record_id ?? null);
    undo.schedule({
      text: `${recordName(record)} נמחקה`,
      run: async () => {
        const message = await remove(record);
        if (message === null) onRemoved(record.record_id);
        setDeletingId((id) => (id === record.record_id ? null : id));
        return message;
      },
      onUndo: () => {
        setDeletingId(null);
        setSelectedId(record.record_id);
      },
    });
  }

  return (
    <div className={showReview ? "review-page is-review" : "review-page is-upload"}>
      <div className="review-page-head">
        <ol className="review-steps" aria-label="שלבים">
          <li className={showReview ? "is-done" : "is-current"} aria-current={showReview ? undefined : "step"}>
            <span className="review-step-dot" aria-hidden="true">{showReview ? "✓" : "1"}</span>
            העלאת טפסים
          </li>
          <li className={showReview ? "is-current" : undefined} aria-current={showReview ? "step" : undefined}>
            <span className="review-step-dot" aria-hidden="true">2</span>
            בדיקה ואישור
          </li>
        </ol>
        {showReview && records.length > 0 && (
          <div className="review-progress">
            <span className="review-progress-text">
              {approved} מתוך {records.length} אושרו
            </span>
            <span
              className="review-progress-bar"
              role="progressbar"
              aria-label="רשומות שאושרו"
              aria-valuemin={0}
              aria-valuemax={records.length}
              aria-valuenow={approved}
            >
              <span style={{ inlineSize: `${(approved / records.length) * 100}%` }} />
            </span>
          </div>
        )}
        {busy && showReview && (
          <span className="review-page-busy" role="status">
            <span className="review-page-pulse" aria-hidden="true" />
            ממשיכה לקרוא קבצים…
          </span>
        )}
        {showReview ? (
          <button type="button" className="review-page-switch" onClick={() => setView("upload")}>
            {busy ? "להתקדמות ההעלאה" : "+ העלאת קבצים נוספים"}
          </button>
        ) : (
          records.length > 0 && (
            <button type="button" className="review-page-switch is-primary" onClick={() => setView("review")}>
              {busy ? `לרשומות שכבר נקראו (${records.length})` : `לרשימת הרשומות (${records.length})`} ←
            </button>
          )
        )}
      </div>

      <div className="review-page-upload" hidden={showReview}>
        <UploadPanel
          onResult={(result) => setRecords((current) => mergeRecords(current, result.records))}
          onBusyChange={onBusyChange}
        />
      </div>

      <div className="review-page-work" hidden={!showReview}>
        <ReviewTable
          records={records}
          selectedId={selected?.record_id ?? null}
          onSelect={setSelectedId}
          onRecords={onRecords}
          approvingId={approvingId}
          onUpload={() => setView("upload")}
        />
        <RecordPanel
          record={selected}
          records={records}
          onSelect={setSelectedId}
          onRecords={onRecords}
          onRemoved={onRemoved}
          onApproveLater={approveLater}
          onDeleteLater={deleteLater}
          approvingId={approvingId}
        />
      </div>

      <UndoToast waiting={undo.waiting} error={undo.error} onUndo={undo.undo} onDismiss={undo.dismissError} />
    </div>
  );
}

/** "הרשומה של דנה לוי", or "הרשומה" when no name was read: the toast's subject. */
function recordName(record: ApiRecord): string {
  const name = [record.fields.first_name.value, record.fields.last_name.value].filter(Boolean).join(" ");
  return name ? `הרשומה של ${name}` : "הרשומה";
}

export default ReviewPage;
