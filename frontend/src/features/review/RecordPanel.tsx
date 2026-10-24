// The record picked in the review list, open for review (PLAN-DEV-B 3.1): its
// original page, whole, then each field edited in place, then approve, delete and
// "next to fix". Side by side when the panel is wide, one under the other when not. The field under the pointer or in focus is
// boxed on the page, where the model read it (field boxes).
// Owner: B

import { useRef, useState } from "react";
import { t } from "../../i18n";
import { useSenders } from "../../shared/useSenders";
import { DocumentPreview } from "../preview/DocumentPreview";
import { fieldHighlight } from "../preview/previewPages";
import { useFieldFocus } from "../preview/useFieldFocus";
import { ApproveButton } from "./ApproveButton";
import { CentralNumbersCell } from "./CentralNumbersCell";
import { DeleteButton } from "./DeleteButton";
import { DuplicateNotice } from "./DuplicateNotice";
import { FieldCell } from "./FieldCell";
import { idProblem } from "./nationalId";
import { useRecordMutations, type ApiRecord } from "./recordMutations";
import { blockingFields, FIELD_COLUMNS, fieldTitle, FORM_TYPE_TEXT, nextToFix, type FieldName } from "./reviewRows";
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
  /** Approve and delete with "undo" (useUndo): the page sends them later. Without
   *  these, approve and delete go to the server at once, delete after asking. */
  onApproveLater?: (record: ApiRecord) => void;
  onDeleteLater?: (record: ApiRecord) => void;
  /** Approved on screen, waiting for its "undo" to run out. */
  approvingId?: string | null;
}

export function RecordPanel({
  record,
  records,
  onSelect,
  onRecords,
  onRemoved,
  onApproveLater,
  onDeleteLater,
  approvingId = null,
}: RecordPanelProps) {
  const { saveField, saveCentrals, approve, remove } = useRecordMutations(onRecords);
  const senders = useSenders();
  const [expanded, setExpanded] = useState(false);
  const { focused, rowProps, areaProps } = useFieldFocus<FieldName | "central_numbers">(record?.record_id ?? "");
  const fields = useRef<HTMLTableElement>(null);

  if (record === null) {
    return (
      <aside className="record-panel" aria-label={t("review.panel.label")}>
        <p className="review-empty">{t("review.panel.empty")}</p>
      </aside>
    );
  }
  const queued = record.record_id === approvingId;
  const editable = record.status === "pending" && !queued;
  const blocking = blockingFields(record);
  const name = [record.fields.first_name.value, record.fields.last_name.value].filter(Boolean).join(" ");
  const position = records.findIndex((r) => r.record_id === record.record_id) + 1;
  const next = nextToFix(records, record.record_id);
  const highlight =
    focused === null
      ? null
      : focused === "central_numbers"
        ? fieldHighlight(`${record.record_id}:${focused}`, t("fields.central_numbers"), record.central_numbers)
        : fieldHighlight(
            `${record.record_id}:${focused}`,
            FIELD_COLUMNS.find((c) => c.name === focused)?.title ?? "",
            [record.fields[focused]],
          );

  return (
    <aside className="record-panel" aria-labelledby="record-panel-title">
      <div className="record-panel-head">
        <h2 id="record-panel-title" className="record-panel-title">
          <bdi>{name || t("common.noName")}</bdi>
        </h2>
        <span className="review-count">
          {t("review.panel.position", { form: FORM_TYPE_TEXT[record.form_type], position, total: records.length })}
        </span>
      </div>

      <div className="record-panel-body">
        <div className={expanded ? "record-panel-preview is-expanded" : "record-panel-preview"} {...areaProps}>
          <DocumentPreview record={record} highlight={highlight} fit="page" />
          <button
            type="button"
            className="record-panel-toggle"
            aria-expanded={expanded}
            onClick={() => setExpanded((open) => !open)}
          >
            {expanded ? t("review.panel.shrink") : t("review.panel.grow")}
          </button>
        </div>

        <div className="record-panel-side">
          {/* Keyed by the record, so an editor left open doesn't carry over to the next one. */}
          {editable && (
            <FixSummary
              blocking={blocking}
              onPick={(name) => {
                // Open the field's editor (the list's first button for a central number).
                const row = fields.current?.querySelector(`tr[data-field="${name.replace(/\[\d+\]$/, "")}"]`);
                const target = row?.querySelector<HTMLButtonElement>(".review-cell-value") ?? row?.querySelector("button");
                if (target?.classList.contains("review-cell-value")) target.click();
                else target?.focus();
              }}
            />
          )}

          <table key={record.record_id} ref={fields} className="record-panel-fields" {...areaProps}>
            <tbody>
              {FIELD_COLUMNS.map((c) => (
                <tr key={c.name} data-field={c.name} {...rowProps(c.name)}>
                  <th scope="row">{c.title}</th>
                  <FieldCell
                    title={c.title}
                    field={record.fields[c.name]}
                    editable={editable}
                    onSave={(edit) => saveField(record, c.name, edit)}
                    options={c.name === "sender" && senders.length > 0 ? senders : undefined}
                    check={c.name === "national_id" ? idProblem : undefined}
                  />
                </tr>
              ))}
              <tr data-field="central_numbers" {...rowProps("central_numbers")}>
                <th scope="row">{t("fields.central_numbers")}</th>
                <CentralNumbersCell
                  items={record.central_numbers}
                  editable={editable}
                  onSave={(items) => saveCentrals(record, items)}
                />
              </tr>
            </tbody>
          </table>

          <DuplicateNotice record={record} newTab />

          <div key={`actions-${record.record_id}`} className="record-panel-actions">
            <ApproveButton
              record={record}
              queued={queued}
              onApprove={
                onApproveLater
                  ? (r) => {
                      onApproveLater(r);
                      return Promise.resolve(null);
                    }
                  : approve
              }
            />
            {!queued && (
              <DeleteButton
                record={record}
                confirm={onDeleteLater ? () => true : undefined}
                onDelete={
                  onDeleteLater
                    ? (r) => {
                        onDeleteLater(r);
                        return Promise.resolve(null);
                      }
                    : remove
                }
                onDeleted={(gone) => {
                  if (!onDeleteLater) onRemoved(gone.record_id);
                }}
              />
            )}
            {next && (
              <button type="button" className="record-panel-next" onClick={() => onSelect(next.record_id)}>
                {t("review.panel.next")}
              </button>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}

/** Above the fields: how many are left to fix, each a button to it, or that all is good. */
function FixSummary({ blocking, onPick }: { blocking: string[]; onPick: (name: string) => void }) {
  if (blocking.length === 0) {
    return (
      <p className="record-panel-summary is-ready">
        <span aria-hidden="true">✓</span> {t("review.panel.allGood")}
      </p>
    );
  }
  return (
    <div className="record-panel-summary is-flagged">
      <p className="record-panel-summary-title">
        <span aria-hidden="true">⚠</span>{" "}
        {blocking.length === 1 ? t("review.panel.leftOne") : t("review.panel.leftMany", { n: blocking.length })}
      </p>
      <ul className="record-panel-summary-list">
        {blocking.map((name) => (
          <li key={name}>
            <button type="button" className="record-panel-summary-chip" onClick={() => onPick(name)}>
              {fieldTitle(name)}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default RecordPanel;
