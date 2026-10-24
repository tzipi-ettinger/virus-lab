// Review list: one short row per record (source, name, ID, status). The selected
// row opens in RecordPanel, where its fields are edited (PLAN-DEV-B 3.1).
// Up and down arrows move the selection.
// Owner: B

import { useState, type KeyboardEvent } from "react";
import { t } from "../../i18n";
import { FileName } from "../../shared/FileName";
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
  /** Approved on screen, waiting for its "undo" to run out: shown as approved. */
  approvingId?: string | null;
  /** Back to the upload, from the empty list. */
  onUpload?: () => void;
}

export function ReviewTable({ records, selectedId, onSelect, onRecords, approvingId = null, onUpload }: ReviewTableProps) {
  const { approveMany } = useRecordMutations(onRecords);
  const [skipped, setSkipped] = useState<Record<string, string>>({});
  if (records.length === 0) {
    return <EmptyList onUpload={onUpload} />;
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
          {t("review.table.title")}
          <span className="review-count">{t("review.table.count", { n: records.length, toFix })}</span>
        </h2>
        <ApproveAllBar records={records} onApproveMany={approveMany} onSkipped={setSkipped} />
      </div>
      <div className="review-scroll">
        <table className="review-table">
          <thead>
            <tr>
              <th scope="col">{t("review.table.source")}</th>
              <th scope="col">{t("fields.name")}</th>
              <th scope="col">{t("fields.national_id")}</th>
              <th scope="col">{t("fields.status")}</th>
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
                      <FileName name={r.source_file} />
                      <span className="review-page-number">{t("common.page", { page: r.page_number })}</span>
                    </button>
                  </th>
                  <td className="review-name">
                    <bdi>{name || t("common.noName")}</bdi>
                  </td>
                  <td className="review-number">
                    <bdi>{r.fields.national_id.value ?? "—"}</bdi>
                  </td>
                  <td>
                    <RowStatus record={r} approving={r.record_id === approvingId} />
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
function RowStatus({ record, approving }: { record: ApiRecord; approving: boolean }) {
  if (record.status === "approved" || approving) return <span className="review-approved">{t("review.approved")}</span>;
  const blocking = blockingFields(record);
  if (blocking.length === 0) return <span className="review-badge is-ready">{t("review.table.ready")}</span>;
  return (
    <span className="review-badge is-flagged" title={t("review.fixFirst", { fields: blocking.map(fieldTitle).join(", ") })}>
      ⚠ {t("review.table.toFix", { n: blocking.length })}
    </span>
  );
}

/** No records yet (or all deleted): a small picture and a way back to the upload. */
function EmptyList({ onUpload }: { onUpload?: () => void }) {
  return (
    <section className="review review-empty-state" aria-labelledby="review-empty-title">
      <svg className="review-empty-art" viewBox="0 0 96 96" width="96" height="96" aria-hidden="true">
        <rect x="22" y="12" width="52" height="68" rx="6" fill="var(--color-surface, #ffffff)" stroke="currentColor" strokeWidth="3" />
        <path d="M32 30h32M32 42h32M32 54h20" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        <circle cx="70" cy="72" r="16" fill="var(--color-accent, #1f6fb2)" />
        <path d="M70 64v16M62 72h16" stroke="#ffffff" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <h2 id="review-empty-title" className="review-empty-title">
        {t("review.table.emptyTitle")}
      </h2>
      <p className="review-empty">{t("review.table.emptyText")}</p>
      {onUpload && (
        <button type="button" className="review-empty-button" onClick={onUpload}>
          {t("review.page.stepUpload")}
        </button>
      )}
    </section>
  );
}

export default ReviewTable;
