// The record picked in the review list, open for review (PLAN-DEV-B 3.1): its
// original page on top, small until asked to grow, then each field edited in place,
// then approve, delete and "next to fix". The field under the pointer or in focus is
// boxed on the page, where the model read it (field boxes).
// Owner: B

import { useState } from "react";
import { useSenders } from "../../shared/useSenders";
import { DocumentPreview } from "../preview/DocumentPreview";
import { fieldHighlight } from "../preview/previewPages";
import { useFieldFocus } from "../preview/useFieldFocus";
import { ApproveButton } from "./ApproveButton";
import { CentralNumbersCell } from "./CentralNumbersCell";
import { DeleteButton } from "./DeleteButton";
import { FieldCell } from "./FieldCell";
import { useRecordMutations, type ApiRecord } from "./recordMutations";
import { FIELD_COLUMNS, FORM_TYPE_TEXT, nextToFix, type FieldName } from "./reviewRows";
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
}

export function RecordPanel({ record, records, onSelect, onRecords, onRemoved }: RecordPanelProps) {
  const { saveField, saveCentrals, approve, remove } = useRecordMutations(onRecords);
  const senders = useSenders();
  const [expanded, setExpanded] = useState(false);
  const { focused, rowProps } = useFieldFocus<FieldName | "central_numbers">(record?.record_id ?? "");

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
  const highlight =
    focused === null
      ? null
      : focused === "central_numbers"
        ? fieldHighlight(`${record.record_id}:${focused}`, "מספרים מרכזיים", record.central_numbers)
        : fieldHighlight(
            `${record.record_id}:${focused}`,
            FIELD_COLUMNS.find((c) => c.name === focused)?.title ?? "",
            [record.fields[focused]],
          );

  return (
    <aside className="record-panel" aria-labelledby="record-panel-title">
      <div className="record-panel-head">
        <h2 id="record-panel-title" className="record-panel-title">
          <bdi>{name || "ללא שם"}</bdi>
        </h2>
        <span className="review-count">
          {FORM_TYPE_TEXT[record.form_type]} · רשומה {position} מתוך {records.length}
        </span>
      </div>

      <div className={expanded ? "record-panel-preview is-expanded" : "record-panel-preview"}>
        <DocumentPreview record={record} highlight={highlight} />
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
            <tr key={c.name} {...rowProps(c.name)}>
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
          <tr {...rowProps("central_numbers")}>
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
