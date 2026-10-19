// The records screen (PLAN-DEV-B 3.1): counts, search and filters, the list and
// paging, all driven by the filters in the URL.
// Owner: B

import { useCallback } from "react";
import { useSearchParams } from "react-router";
import type { components } from "../../api/schema";
import { ExportButton } from "./ExportButton";
import { NO_FILTERS, PAGE_SIZE, hasFilters, parseFilters, toParams, withChange, type RecordFilters } from "./filters";
import { RecordsFilters } from "./RecordsFilters";
import { RecordsTable } from "./RecordsTable";
import { useRecordsQuery } from "./useRecordsQuery";
import "./RecordsPage.css";

type RecordCounts = components["schemas"]["RecordCounts"];

export function RecordsPage() {
  const [params, setParams] = useSearchParams();
  const filters = parseFilters(params);
  const { query, reload } = useRecordsQuery(filters);
  // useCallback: the search box waits on it, and a new function each render would
  // restart its timer.
  const change = useCallback(
    (patch: Partial<RecordFilters>) =>
      setParams((current) => toParams(withChange(parseFilters(current), patch))),
    [setParams],
  );
  const data = query.data;

  return (
    <section className="records" aria-labelledby="records-title" aria-busy={query.status === "loading"}>
      <h1 id="records-title" className="records-title">
        רשומות
      </h1>
      {data && <Counts counts={data.counts} filters={filters} onPick={change} />}
      <RecordsFilters filters={filters} onChange={change} />
      {data && <ExportButton filters={filters} total={data.total} />}
      {query.status === "error" && (
        <div className="records-banner" role="alert">
          ⚠ {query.message}
          <button type="button" onClick={reload}>
            נסי שוב
          </button>
        </div>
      )}
      {!data && query.status === "loading" && <p className="records-empty">טוען…</p>}
      {data && data.items.length === 0 && (
        <div className="records-empty">
          {hasFilters(filters) ? (
            <>
              <p>אין רשומות לפי הסינון הנוכחי.</p>
              <button type="button" onClick={() => setParams(toParams(NO_FILTERS))}>
                ניקוי הסינון
              </button>
            </>
          ) : (
            <p>עוד אין רשומות. רשומות נוצרות כשמעלים טפסים במסך ההעלאה.</p>
          )}
        </div>
      )}
      {data && data.items.length > 0 && (
        <>
          <RecordsTable items={data.items} />
          <Pagination total={data.total} page={filters.page} onPage={(page) => change({ page })} />
        </>
      )}
    </section>
  );
}

function Counts({
  counts,
  filters,
  onPick,
}: {
  counts: RecordCounts;
  filters: RecordFilters;
  onPick: (patch: Partial<RecordFilters>) => void;
}) {
  const pending = filters.status === "pending" && !filters.needsReview;
  const review = filters.needsReview;
  const approved = filters.status === "approved";
  return (
    <div className="records-counts" role="group" aria-label="מונים">
      <button type="button" aria-pressed={pending} onClick={() => onPick({ status: "pending", needsReview: false })}>
        ממתינות <strong>{counts.pending}</strong>
      </button>
      <button type="button" aria-pressed={review} onClick={() => onPick({ status: "pending", needsReview: true })}>
        <span aria-hidden="true">⚠</span> דורשות בדיקה <strong>{counts.needs_review}</strong>
      </button>
      <button type="button" aria-pressed={approved} onClick={() => onPick({ status: "approved", needsReview: false })}>
        <span aria-hidden="true">✓</span> מאושרות <strong>{counts.approved}</strong>
      </button>
    </div>
  );
}

function Pagination({ total, page, onPage }: { total: number; page: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const first = (page - 1) * PAGE_SIZE + 1;
  const last = Math.min(page * PAGE_SIZE, total);
  return (
    <nav className="records-pages" aria-label="דפדוף">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        הקודם
      </button>
      <span>
        {first}–{last} מתוך {total}
      </span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        הבא
      </button>
    </nav>
  );
}
