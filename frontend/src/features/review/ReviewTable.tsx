// Review list: one short row per record (source, name, ID, status). The selected
// row opens in RecordPanel, where its fields are edited (PLAN-DEV-B 3.1).
// Up and down arrows move the selection.
// Owner: B

import { useState, type KeyboardEvent } from "react";
import { ApproveAllBar } from "./ApproveAllBar";
import { useRecordMutations, type ApiRecord } from "./recordMutations";
import { blockingFields, fieldTitle } from "./reviewRows";
import "./ReviewTable.css";

interface ReviewTableProps {
  records: ApiRecord[];
  selectedId: string | null;
  onSelect: (recordId: string) => void;
  /** Records the server sent back after a change: they replace the local ones. */
  onRecords: (records: ApiRecord[]) => void;
}

export function ReviewTable({ records, selectedId, onSelect, onRecords }: ReviewTableProps) {
  const { approveMany } = useRecordMutations(onRecords);
  const [skipped, setSkipped] = useState<Record<string, string>>({});
  if (records.length === 0) {
    return <p className="review-empty">עוד אין רשומות. העלי טפסים כדי להתחיל</p>;
  }
  const toFix = records.filter((r) => r.status === "pending" && blockingFields(r).length > 0).length;

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const step = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    const next = records[index + step];
    if (step === 0 || !next) return;
    event.preventDefault();
    onSelect(next.record_id);
    const buttons = event.currentTarget.closest("tbody")?.querySelectorAll<HTMLButtonElement>(".review-select");
    buttons?.[index + step]?.focus();
  }

  return (
    <section className="review" aria-labelledby="review-title">
      <div className="review-head">
        <h2 id="review-title" className="review-title">
          טבלת בדיקה
          <span className="review-count">
            {records.length} רשומות · {toFix} לתיקון
          </span>
        </h2>
        <ApproveAllBar records={records} onApproveMany={approveMany} onSkipped={setSkipped} />
      </div>
      <div className="review-scroll">
        <table className="review-table">
          <thead>
            <tr>
              <th scope="col">מקור</th>
              <th scope="col">שם</th>
              <th scope="col">ת״ז</th>
              <th scope="col">סטטוס</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r, index) => {
              const selected = r.record_id === selectedId;
              const name = [r.fields.first_name.value, r.fields.last_name.value].filter(Boolean).join(" ");
              return (
                <tr
                  key={r.record_id}
                  className={selected ? "is-selected" : undefined}
                  aria-selected={selected}
                  onClick={() => onSelect(r.record_id)}
                >
                  <th scope="row">
                    {/* The button makes the row reachable from the keyboard; the row click is for the mouse. */}
                    <button
                      type="button"
                      className="review-select"
                      aria-pressed={selected}
                      onKeyDown={(event) => onKeyDown(event, index)}
                    >
                      <bdi>{r.source_file}</bdi>
                      <span className="review-page-number">עמוד {r.page_number}</span>
                    </button>
                  </th>
                  <td className="review-name">
                    <bdi>{name || "ללא שם"}</bdi>
                  </td>
                  <td className="review-number">
                    <bdi>{r.fields.national_id.value ?? "—"}</bdi>
                  </td>
                  <td>
                    <RowStatus record={r} />
                    {skipped[r.record_id] && r.status === "pending" && (
                      <span className="review-cell-error">{skipped[r.record_id]}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Approved, ready, or how many fields still block approval, in text and not color only. */
function RowStatus({ record }: { record: ApiRecord }) {
  if (record.status === "approved") return <span className="review-approved">✓ אושר</span>;
  const blocking = blockingFields(record);
  if (blocking.length === 0) return <span className="review-badge is-ready">מוכן לאישור</span>;
  return (
    <span className="review-badge is-flagged" title={`לטפל קודם ב: ${blocking.map(fieldTitle).join(", ")}`}>
      ⚠ {blocking.length} לתיקון
    </span>
  );
}

export default ReviewTable;
