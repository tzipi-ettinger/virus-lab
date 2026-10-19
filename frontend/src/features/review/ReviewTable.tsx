// Review table: one row per record, one column per field, flagged cells in orange
// with a confidence label, each field edited in place (PLAN-DEV-B 3.1).
// Owner: B

import { useSenders } from "../../shared/useSenders";
import { CentralNumbersCell } from "./CentralNumbersCell";
import { FieldCell } from "./FieldCell";
import { useRecordMutations, type ApiRecord } from "./recordMutations";
import { FIELD_COLUMNS, FORM_TYPE_TEXT, statusText } from "./reviewRows";
import "./ReviewTable.css";

interface ReviewTableProps {
  records: ApiRecord[];
  selectedId: string | null;
  onSelect: (recordId: string) => void;
  /** Records the server sent back after a change: they replace the local ones. */
  onRecords: (records: ApiRecord[]) => void;
}

export function ReviewTable({ records, selectedId, onSelect, onRecords }: ReviewTableProps) {
  const { saveField, saveCentrals } = useRecordMutations(onRecords);
  const senders = useSenders();
  if (records.length === 0) {
    return <p className="review-empty">עוד אין רשומות. העלי טפסים כדי להתחיל</p>;
  }
  const flagged = records.filter((r) => r.needs_review).length;

  return (
    <section className="review" aria-labelledby="review-title">
      <h2 id="review-title" className="review-title">
        טבלת בדיקה
        <span className="review-count">
          {records.length} רשומות · {flagged} דורשות בדיקה
        </span>
      </h2>
      <div className="review-scroll">
        <table className="review-table">
          <thead>
            <tr>
              <th scope="col">טופס</th>
              <th scope="col">סוג</th>
              {FIELD_COLUMNS.map((c) => (
                <th key={c.name} scope="col">{c.title}</th>
              ))}
              <th scope="col">מספרים מרכזיים</th>
              <th scope="col">סטטוס</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => {
              const selected = r.record_id === selectedId;
              return (
                <tr
                  key={r.record_id}
                  className={selected ? "is-selected" : undefined}
                  aria-selected={selected}
                  onClick={() => onSelect(r.record_id)}
                >
                  <th scope="row">
                    {/* The button makes the row reachable from the keyboard; the row click is for the mouse. */}
                    <button type="button" className="review-select" aria-pressed={selected}>
                      <bdi>{r.source_file}</bdi>, עמוד {r.page_number}
                    </button>
                  </th>
                  <td>{FORM_TYPE_TEXT[r.form_type]}</td>
                  {FIELD_COLUMNS.map((c) => (
                    <FieldCell
                      key={c.name}
                      title={c.title}
                      field={r.fields[c.name]}
                      editable={r.status === "pending"}
                      onSave={(edit) => saveField(r, c.name, edit)}
                      options={c.name === "sender" && senders.length > 0 ? senders : undefined}
                    />
                  ))}
                  <CentralNumbersCell
                    items={r.central_numbers}
                    editable={r.status === "pending"}
                    onSave={(items) => saveCentrals(r, items)}
                  />
                  <td className={r.needs_review ? "review-status is-flagged" : "review-status"}>{statusText(r)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default ReviewTable;
