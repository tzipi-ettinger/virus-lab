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
import { ApproveButton } from "../review/ApproveButton";
import { DeleteButton } from "../review/DeleteButton";
import { FieldCell } from "../review/FieldCell";
import { keepCentrals, useRecordMutations, type FieldEdit, type Saved } from "../review/recordMutations";
import { FIELD_COLUMNS, FORM_TYPE_TEXT } from "../review/reviewRows";
import "../review/ReviewTable.css";
import { formatDateTime, statusView } from "./format";
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

  if (loaded === null || loaded.id !== request) return <p className="records-empty">טוען…</p>;
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
  const [focused, setFocused] = useState<string | null>(null); // a row's title
  const focusedRow = rows.find((row) => row.title === focused);
  const highlight = focusedRow
    ? fieldHighlight(`${record.record_id}:${focusedRow.title}`, focusedRow.title, [focusedRow.field])
    : null;

  return (
    <div className="record-page">
      <div className="record-main">
        {backLink}
        <h1 className="records-title">
          <bdi>{name || "ללא שם"}</bdi>
        </h1>
        <div className="record-actions">
          <ApproveButton record={record} onApprove={approve} />
          <DeleteButton record={record} onDelete={remove} onDeleted={() => navigate(back, { replace: true })} />
        </div>
        <p className={`records-status is-${status.tone}`}>
          <span aria-hidden="true">{status.icon}</span>{" "}
          {record.status === "approved" && record.approved_at
            ? `אושר ב־${formatDateTime(record.approved_at)}`
            : status.text}
        </p>
        <dl className="record-meta">
          <dt>קובץ</dt>
          <dd>
            <bdi>{record.source_file}</bdi>, עמוד {record.page_number}
            {more.length > 0 && ` (ועמודים ${more.join(", ")})`}
          </dd>
          <dt>סוג טופס</dt>
          <dd>{FORM_TYPE_TEXT[record.form_type]}</dd>
          <dt>נקלט</dt>
          <dd>{formatDateTime(record.created_at)}</dd>
        </dl>

        {record.issues.length > 0 && (
          <ul className="record-issues" aria-label="בעיות ברשומה">
            {record.issues.map((issue) => (
              <li key={issue.code}>⚠ {issue.message}</li>
            ))}
          </ul>
        )}

        <div className="records-scroll">
          <table className="records-table record-fields">
            <thead>
              <tr>
                <th scope="col">שדה</th>
                <th scope="col">ערך ורמת ביטחון</th>
                <th scope="col">מה נקרא בטופס</th>
                <th scope="col">ראיה</th>
                <th scope="col">בעיות</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ title, field, onSave }) => (
                <tr
                  key={title}
                  className={field.needs_review ? "is-flagged" : undefined}
                  onMouseEnter={() => setFocused(title)}
                  onFocus={() => setFocused(title)}
                >
                  <th scope="row">{title}</th>
                  <FieldCell
                    title={title}
                    field={field}
                    editable={editable}
                    onSave={onSave}
                    options={title === "גורם שולח" && senders.length > 0 ? senders : undefined}
                  />
                  <td>
                    <bdi>{field.raw ?? "—"}</bdi>
                  </td>
                  <td className="record-evidence">
                    <bdi>{field.evidence ?? "—"}</bdi>
                  </td>
                  <td>{field.issues.map((i) => i.message).join(" · ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <DocumentPreview record={record} highlight={highlight} />
    </div>
  );
}
