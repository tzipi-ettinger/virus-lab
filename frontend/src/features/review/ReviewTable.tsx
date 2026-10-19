// Review table: one row per record, one column per field, flagged cells in orange
// with a confidence label. Read-only for now: editing in place comes next (B1.7).
// Owner: B

import type { components } from "../../api/schema";
import {
  CONFIDENCE_TEXT,
  FIELD_COLUMNS,
  FORM_TYPE_TEXT,
  fieldCell,
  listCell,
  statusText,
  type Cell,
} from "./reviewRows";
import "./ReviewTable.css";

type ApiRecord = components["schemas"]["Record"];

interface ReviewTableProps {
  records: ApiRecord[];
  selectedId: string | null;
  onSelect: (recordId: string) => void;
}

function CellView({ cell }: { cell: Cell }) {
  return (
    <td className={cell.flagged ? "review-cell is-flagged" : "review-cell"} title={cell.issues.join("\n") || undefined}>
      <span className="review-value">{cell.text ? <bdi>{cell.text}</bdi> : "—"}</span>
      <span className={`review-confidence is-${cell.confidence}`}>{CONFIDENCE_TEXT[cell.confidence]}</span>
    </td>
  );
}

export function ReviewTable({ records, selectedId, onSelect }: ReviewTableProps) {
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
                    <CellView key={c.name} cell={fieldCell(r.fields[c.name])} />
                  ))}
                  <CellView cell={listCell(r.central_numbers)} />
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
