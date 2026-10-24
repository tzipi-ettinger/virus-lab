// The records screen (PLAN-DEV-B 3.1): counts, search and filters, the list and
// paging, all driven by the filters in the URL. On a wide screen it fits the
// window and only the list scrolls, under its own header.
// Owner: B

import { useCallback } from "react";
import { useSearchParams } from "react-router";
import type { components } from "../../api/schema";
import { t } from "../../i18n";
import { ExportButton } from "./ExportButton";
import {
  NO_FILTERS,
  PAGE_SIZE,
  filterChips,
  hasFilters,
  parseFilters,
  toParams,
  withChange,
  type RecordFilters,
} from "./filters";
import { RecordsFilters } from "./RecordsFilters";
import { RecordsTable } from "./RecordsTable";
import { useRecordsQuery } from "./useRecordsQuery";
import { Skeleton } from "../../shared/ui/Skeleton";
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
      <div className="records-head">
        <h1 id="records-title" className="records-title">
          {t("records.title")}
        </h1>
        {data && <Counts counts={data.counts} filters={filters} onPick={change} />}
      </div>
      <div className="records-toolbar">
        <RecordsFilters filters={filters} onChange={change} />
        <ActiveFilters filters={filters} onChange={change} />
        {data && <ExportButton filters={filters} total={data.total} />}
      </div>
      {query.status === "error" && (
        <div className="records-banner" role="alert">
          ⚠ {query.message}
          <button type="button" onClick={reload}>
            {t("common.retry")}
          </button>
        </div>
      )}
      {!data && query.status === "loading" && (
        <div className="records-card">
          <Skeleton rows={10} label={t("records.loading")} />
        </div>
      )}
      {data && data.items.length === 0 && (
        <div className="records-empty">
          {hasFilters(filters) ? (
            <>
              <p>{t("records.noMatch")}</p>
              <button type="button" onClick={() => setParams(toParams(NO_FILTERS))}>
                {t("records.clear")}
              </button>
            </>
          ) : (
            <p>{t("records.none")}</p>
          )}
        </div>
      )}
      {data && data.items.length > 0 && (
        <div className="records-card">
          <RecordsTable items={data.items} sort={filters.sort} onSort={(sort) => change({ sort })} />
          <Pagination total={data.total} page={filters.page} onPage={(page) => change({ page })} />
        </div>
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
  const all = filters.status === null && !filters.needsReview;
  const pending = filters.status === "pending" && !filters.needsReview;
  const review = filters.needsReview;
  const approved = filters.status === "approved";
  // One row of tabs; the pressed one fills with its status color.
  return (
    <div className="records-counts" role="group" aria-label={t("records.counts.label")}>
      <button
        type="button"
        className="records-count is-all"
        aria-pressed={all}
        onClick={() => onPick({ status: null, needsReview: false })}
      >
        {t("common.all")} <strong>{counts.pending + counts.approved}</strong>
      </button>
      <button
        type="button"
        className="records-count is-pending"
        aria-pressed={pending}
        onClick={() => onPick({ status: "pending", needsReview: false })}
      >
        <span className="records-count-dot" aria-hidden="true" /> {t("records.counts.pending")} <strong>{counts.pending}</strong>
      </button>
      <button
        type="button"
        className="records-count is-review"
        aria-pressed={review}
        onClick={() => onPick({ status: "pending", needsReview: true })}
      >
        <span aria-hidden="true">⚠</span> {t("records.counts.review")} <strong>{counts.needs_review}</strong>
      </button>
      <button
        type="button"
        className="records-count is-approved"
        aria-pressed={approved}
        onClick={() => onPick({ status: "approved", needsReview: false })}
      >
        <span aria-hidden="true">✓</span> {t("records.counts.approved")} <strong>{counts.approved}</strong>
      </button>
    </div>
  );
}

/** The filters in use as chips; each × takes one off, and one button takes them all. */
function ActiveFilters({
  filters,
  onChange,
}: {
  filters: RecordFilters;
  onChange: (patch: Partial<RecordFilters>) => void;
}) {
  const chips = filterChips(filters);
  if (chips.length === 0) return null;
  return (
    <div className="records-active" role="group" aria-label={t("records.active.label")}>
      <span className="records-active-label">{t("records.active.by")}</span>
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          className={`records-chip${chip.tone ? ` is-${chip.tone}` : ""}`}
          aria-label={t("records.active.remove", { label: chip.label })}
          onClick={() => onChange(chip.clear)}
        >
          {chip.label}
          <span aria-hidden="true">×</span>
        </button>
      ))}
      {/* The order is not a filter: it stays. */}
      <button type="button" className="records-active-clear" onClick={() => onChange({ ...NO_FILTERS, sort: filters.sort })}>
        {t("records.active.clearAll")}
      </button>
    </div>
  );
}

function Pagination({ total, page, onPage }: { total: number; page: number; onPage: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const first = (page - 1) * PAGE_SIZE + 1;
  const last = Math.min(page * PAGE_SIZE, total);
  return (
    <nav className="records-pages" aria-label={t("records.pages.label")}>
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        {t("records.pages.previous")}
      </button>
      <span>{t("records.pages.range", { first, last, total })}</span>
      <button type="button" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        {t("records.pages.next")}
      </button>
    </nav>
  );
}
