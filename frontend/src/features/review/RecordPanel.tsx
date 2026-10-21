// The record picked in the review list, open for review (PLAN-DEV-B 3.1): its
// original page on top, small until asked to grow, then each field edited in place,
// then approve, delete and "next to fix".
// Owner: B

import { useEffect, useRef, useState } from "react";
import { useSenders } from "../../shared/useSenders";
import { DocumentPreview } from "../preview/DocumentPreview";
import { ApproveButton } from "./ApproveButton";
import { CentralNumbersCell } from "./CentralNumbersCell";
import { DeleteButton } from "./DeleteButton";
import { FieldCell } from "./FieldCell";
import { useRecordMutations, type ApiRecord } from "./recordMutations";
import { FIELD_COLUMNS, FORM_TYPE_TEXT, nextToFix } from "./reviewRows";
import "./RecordPanel.css";

interface RecordPanelProps {
  record: ApiRecord | null;
  /** The whole list, for "record N of M" and "next to fix". */
  records: ApiRecord[];
  onSelect: (recordId: string) => void;
  /** Records the server sent back after a change: they replace the local ones. */
  onRecords: (records: ApiRecord[]) => void;
  /** A record deleted on the server: take it off. */
  onRemoved: (recordId: string) => void;
  /** Grows each time a row is picked in the list. */
  reveal: number;
}

// Matches ReviewPage.css: below this width the panel sits under the list.
const STACKED = "(max-width: 900px)";

export function RecordPanel({ record, records, onSelect, onRecords, onRemoved, reveal }: RecordPanelProps) {
  const { saveField, saveCentrals, approve, remove } = useRecordMutations(onRecords);
  const senders = useSenders();
  const [expanded, setExpanded] = useState(false);
  const title = useRef<HTMLHeadingElement>(null);

  // Under the list, a picked row would change nothing in sight: bring the panel up,
  // and move the focus to its title so a screen reader reads the record.
  useEffect(() => {
    if (reveal === 0 || !window.matchMedia?.(STACKED).matches) return;
    title.current?.scrollIntoView?.({ block: "start" });
    title.current?.focus({ preventScroll: true });
  }, [reveal]);

  if (record === null) {
    return (
      <aside className="record-panel" aria-label="רשומה לבדיקה">
        <p className="review-empty">כאן תיפתח הרשומה שבוחרים ברשימה</p>
      </aside>
    );
  }
  const editable = record.status === "pending";
  const name = [record.fields.first_name.value, record.fields.last_name.value].filter(Boolean).join(" ");
  const position = records.findIndex((r) => r.record_id === record.record_id) + 1;
  const next = nextToFix(records, record.record_id);

  return (
    <aside className="record-panel" aria-labelledby="record-panel-title">
      <div className="record-panel-head">
        <h2 id="record-panel-title" className="record-panel-title" ref={title} tabIndex={-1}>
          <bdi>{name || "ללא שם"}</bdi>
        </h2>
        <span className="review-count">
          {FORM_TYPE_TEXT[record.form_type]} · רשומה {position} מתוך {records.length}
        </span>
      </div>

      <div className={expanded ? "record-panel-preview is-expanded" : "record-panel-preview"}>
        <DocumentPreview record={record} />
        <button
          type="button"
          className="record-panel-toggle"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? "הקטנת הטופס" : "הגדלת הטופס"}
        </button>
      </div>

      {/* Keyed by the record, so an editor left open doesn't carry over to the next one. */}
      <table key={record.record_id} className="record-panel-fields">
        <tbody>
          {FIELD_COLUMNS.map((c) => (
            <tr key={c.name}>
              <th scope="row">{c.title}</th>
              <FieldCell
                title={c.title}
                field={record.fields[c.name]}
                editable={editable}
                onSave={(edit) => saveField(record, c.name, edit)}
                options={c.name === "sender" && senders.length > 0 ? senders : undefined}
              />
            </tr>
          ))}
          <tr>
            <th scope="row">מספרים מרכזיים</th>
            <CentralNumbersCell
              items={record.central_numbers}
              editable={editable}
              onSave={(items) => saveCentrals(record, items)}
            />
          </tr>
        </tbody>
      </table>

      <div key={`actions-${record.record_id}`} className="record-panel-actions">
        <ApproveButton record={record} onApprove={approve} />
        <DeleteButton record={record} onDelete={remove} onDeleted={(gone) => onRemoved(gone.record_id)} />
        {next && (
          <button type="button" className="record-panel-next" onClick={() => onSelect(next.record_id)}>
            הבאה לתיקון ←
          </button>
        )}
      </div>
    </aside>
  );
}

export default RecordPanel;
