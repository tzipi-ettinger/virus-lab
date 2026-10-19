// One record in full (PLAN-DEV-B 3.1): what the model read next to the value now,
// the evidence, the confidence and every issue, with the original page beside it.
// Approve and edit come with the review actions (B1.7).
// Owner: B

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useParams } from "react-router";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";
import { DocumentPreview } from "../preview/DocumentPreview";
import { CONFIDENCE_TEXT, FIELD_COLUMNS, FORM_TYPE_TEXT, confidence } from "../review/reviewRows";
import { formatDate, formatDateTime, statusView } from "./format";
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
  return <RecordDetails record={loaded.record} backLink={backLink} />;
}

function RecordDetails({ record, backLink }: { record: ApiRecord; backLink: ReactNode }) {
  const status = statusView(record);
  const more = record.continuation_pages ?? [];
  const name = [record.fields.first_name.value, record.fields.last_name.value].filter(Boolean).join(" ");
  const rows: { title: string; field: FormField }[] = [
    ...FIELD_COLUMNS.map((c) => ({ title: c.title, field: record.fields[c.name] })),
    ...record.central_numbers.map((field, i) => ({ title: `מספר מרכזי ${i + 1}`, field })),
  ];

  return (
    <div className="record-page">
      <div className="record-main">
        {backLink}
        <h1 className="records-title">
          <bdi>{name || "ללא שם"}</bdi>
        </h1>
        <p className={`records-status is-${status.tone}`}>
          <span aria-hidden="true">{status.icon}</span>{" "}
          {record.status === "approved" && record.approved_by
            ? `אושר על ידי ${record.approved_by} ב־${formatDateTime(record.approved_at)}`
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
                <th scope="col">ערך</th>
                <th scope="col">מה נקרא בטופס</th>
                <th scope="col">ראיה</th>
                <th scope="col">רמת ביטחון</th>
                <th scope="col">בעיות</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ title, field }) => (
                <tr key={title} className={field.needs_review ? "is-flagged" : undefined}>
                  <th scope="row">{title}</th>
                  <td>
                    <bdi>{title === "תאריך קבלה" ? formatDate(field.value) : (field.value ?? "—")}</bdi>
                  </td>
                  <td>
                    <bdi>{field.raw ?? "—"}</bdi>
                  </td>
                  <td className="record-evidence">
                    <bdi>{field.evidence ?? "—"}</bdi>
                  </td>
                  <td>{CONFIDENCE_TEXT[confidence(field)]}</td>
                  <td>{field.issues.map((i) => i.message).join(" · ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <DocumentPreview record={record} />
    </div>
  );
}
