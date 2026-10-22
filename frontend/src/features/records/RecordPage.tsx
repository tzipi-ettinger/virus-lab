// One record in full (PLAN-DEV-B 3.1): what the model read next to the value now,
// the evidence, the confidence and every issue, with the original page beside it.
// The same edit, confirm, approve and delete as in the review table (B1.7). The row
// under the pointer or in focus is boxed on the page, where it was read (field boxes).
// Owner: B

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";
import { useSenders } from "../../shared/useSenders";
import { DocumentPreview } from "../preview/DocumentPreview";
import { fieldHighlight } from "../preview/previewPages";
import { useFieldFocus } from "../preview/useFieldFocus";
import { Skeleton } from "../../shared/ui/Skeleton";
import { ApproveButton } from "../review/ApproveButton";
import { DeleteButton } from "../review/DeleteButton";
import { DuplicateNotice } from "../review/DuplicateNotice";
import { FieldCell } from "../review/FieldCell";
import { keepCentrals, useRecordMutations, type FieldEdit, type Saved } from "../review/recordMutations";
import { FIELD_COLUMNS, FORM_TYPE_TEXT } from "../review/reviewRows";
import "../review/ReviewTable.css";
import { formatDateTime, statusView } from "./format";
import { RecordHistory } from "./RecordHistory";
import { useRecordHistory } from "./useRecordHistory";
import type { BackTo } from "./RecordsTable";
import "./RecordsPage.css";

type ApiRecord = components["schemas"]["Record"];
type FormField = components["schemas"]["FormField"];

type Loaded =
  | { id: string; record: ApiRecord }
  | { id: string; notFound: true }
  | { id: string; error: string };

export function RecordPage() {
  const { recordId = "" } = useParams();
  const back = (useLocation().state as BackTo | null)?.back ?? "/records";
  const [attempt, setAttempt] = useState(0);
  const request = `${recordId}#${attempt}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<ApiRecord>(`/api/v1/records/${encodeURIComponent(recordId)}`, { signal: controller.signal }).then(
      (record) => setLoaded({ id: request, record }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) setLoaded({ id: request, notFound: true });
        else setLoaded({ id: request, error: error instanceof ApiError ? error.message : "משהו השתבש. נסי שוב" });
      },
    );
    return () => controller.abort();
  }, [recordId, request]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  // The server's answer to a change replaces the record on screen.
  const update = useCallback(
    (record: ApiRecord) => setLoaded((current) => (current && "record" in current ? { ...current, record } : current)),
    [],
  );
  const backLink = (
    <Link className="record-back" to={back}>
      → חזרה לרשומות
    </Link>
  );

  if (loaded === null || loaded.id !== request) {
    return (
      <div className="record-page is-loading">
        <div className="record-main">
          <div className="record-card">
            <Skeleton rows={9} label="טוען את הרשומה…" />
          </div>
        </div>
        <div className="record-loading-page" aria-hidden="true" />
      </div>
    );
  }
  if ("notFound" in loaded) {
    return (
      <div className="records-empty">
        <p>הרשומה לא נמצאה. ייתכן שנמחקה.</p>
        {backLink}
      </div>
    );
  }
  if ("error" in loaded) {
    return (
      <div className="records-banner" role="alert">
        ⚠ {loaded.error}
        <button type="button" onClick={retry}>
          נסי שוב
        </button>
      </div>
    );
  }
  return <RecordDetails record={loaded.record} backLink={backLink} back={back} onRecord={update} />;
}

interface DetailsProps {
  record: ApiRecord;
  backLink: ReactNode;
  back: string;
  onRecord: (record: ApiRecord) => void;
}

function RecordDetails({ record, backLink, back, onRecord }: DetailsProps) {
  const navigate = useNavigate();
  const senders = useSenders();
  // Siblings from a shared-field change are other pages: only this record matters here.
  const onRecords = useCallback(
    (changed: ApiRecord[]) => {
      const mine = changed.find((r) => r.record_id === record.record_id);
      if (mine) onRecord(mine);
    },
    [record.record_id, onRecord],
  );
  const { saveField, saveCentrals, approve, remove } = useRecordMutations(onRecords);
  const status = statusView(record);
  const history = useRecordHistory(record.record_id, record.version);
  const more = record.continuation_pages ?? [];
  const editable = record.status === "pending";
  const name = [record.fields.first_name.value, record.fields.last_name.value].filter(Boolean).join(" ");
  const rows: { title: string; field: FormField; onSave: (edit: FieldEdit) => Promise<Saved> }[] = [
    ...FIELD_COLUMNS.map((c) => ({
      title: c.title,
      field: record.fields[c.name],
      onSave: (edit: FieldEdit) => saveField(record, c.name, edit),
    })),
    ...record.central_numbers.map((field, i) => ({
      title: `מספר מרכזי ${i + 1}`,
      field,
      // One item changes; the others are kept by their position.
      onSave: (edit: FieldEdit) => saveCentrals(record, keepCentrals(record.central_numbers, { [i]: edit })),
    })),
  ];
  const { focused, rowProps, areaProps } = useFieldFocus<string>(record.record_id); // a row's title
  const focusedRow = rows.find((row) => row.title === focused);
  const highlight = focusedRow
    ? fieldHighlight(`${record.record_id}:${focusedRow.title}`, focusedRow.title, [focusedRow.field])
    : null;

  return (
    <div className="record-page">
      <div className="record-main">
        {backLink}
        <header className="record-summary">
          <div className="record-head">
            <span className="record-avatar" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="8" r="4" />
                <path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
              </svg>
            </span>
            <h1 className="records-title">
              <bdi>{name || "ללא שם"}</bdi>
            </h1>
            <p className={`records-status is-${status.tone}`}>
              <span aria-hidden="true">{status.icon}</span>{" "}
              {record.status === "approved" && record.approved_by
                ? `אושר על ידי ${record.approved_by} ב־${formatDateTime(record.approved_at)}`
                : status.text}
            </p>
            <div className="record-actions">
              <ApproveButton record={record} onApprove={approve} />
              <DeleteButton record={record} onDelete={remove} onDeleted={() => navigate(back, { replace: true })} />
              <RecordHistory history={history} />
            </div>
          </div>
          <dl className="record-meta">
            <div>
              <dt>קובץ</dt>
              <dd title={record.source_file}>
                <bdi>{record.source_file}</bdi>, עמוד {record.page_number}
                {more.length > 0 && ` (ועמודים ${more.join(", ")})`}
              </dd>
            </div>
            <div>
              <dt>סוג טופס</dt>
              <dd>{FORM_TYPE_TEXT[record.form_type]}</dd>
            </div>
            <div>
              <dt>נקלט</dt>
              <dd>{formatDateTime(record.created_at)}</dd>
            </div>
          </dl>
        </header>

        {record.issues.length > 0 && (
          <ul className="record-issues" aria-label="בעיות ברשומה">
            {record.issues.map((issue) => (
              <li key={issue.code}>⚠ {issue.message}</li>
            ))}
          </ul>
        )}

        <DuplicateNotice record={record} />

        <div className="record-card">
          <table className="records-table record-fields" {...areaProps}>
            <thead>
              <tr>
                <th scope="col">שדה</th>
                <th scope="col">ערך ורמת ביטחון</th>
                <th scope="col">מה נקרא בטופס</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ title, field, onSave }) => (
                <tr
                  key={title}
                  className={field.needs_review ? "is-flagged" : undefined}
                  {...rowProps(title)}
                >
                  <th scope="row">{title}</th>
                  <FieldCell
                    title={title}
                    field={field}
                    editable={editable}
                    onSave={onSave}
                    options={title === "גורם שולח" && senders.length > 0 ? senders : undefined}
                  />
                  {/* What was read and how on one line (the evidence whole in the
                      tooltip), then the issues, never cut. */}
                  <td className="record-read">
                    <span className="record-read-line" title={field.evidence ?? undefined}>
                      <span className="record-raw">
                        <bdi>{field.raw ?? "—"}</bdi>
                      </span>
                      {/* dir="auto": English evidence is cut at its end, not its start. */}
                      {field.evidence && (
                        <span className="record-evidence" dir="auto">
                          {field.evidence}
                        </span>
                      )}
                    </span>
                    {field.issues.length > 0 && (
                      <span className="record-field-issues">{field.issues.map((i) => i.message).join(" · ")}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <DocumentPreview record={record} highlight={highlight} pointerArea={areaProps} fit="page" />
    </div>
  );
}
