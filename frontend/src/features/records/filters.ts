// The records screen's filters live in the URL, not in state (PLAN-DEV-B 3.3):
// a reload, the back button or a shared link opens the same view. No React here.
// Owner: B

import type { components, operations } from "../../api/schema";
import { t } from "../../i18n";
import { FORM_TYPE_TEXT } from "../review/reviewRows";
import { formatDate } from "./format";

export type RecordStatus = components["schemas"]["RecordSummary"]["status"];
export type FormType = components["schemas"]["RecordSummary"]["form_type"];
type ListQuery = NonNullable<operations["list_records_api_v1_records_get"]["parameters"]["query"]>;
/** A column, ascending; "-" in front for descending (RecordSort in the API). */
export type RecordSort = NonNullable<ListQuery["sort"]>;
export type SortColumn = Exclude<RecordSort, `-${string}`>;

export const PAGE_SIZE = 50;

export interface RecordFilters {
  q: string;
  status: RecordStatus | null;
  needsReview: boolean; // only records with a field still flagged
  sender: string;
  formType: FormType | null;
  dateFrom: string; // YYYY-MM-DD, received_date, inclusive
  dateTo: string;
  sort: RecordSort; // not a filter, but it lives in the URL with them
  page: number; // 1-based
}

export const NO_FILTERS: RecordFilters = {
  q: "",
  status: null,
  needsReview: false,
  sender: "",
  formType: null,
  dateFrom: "",
  dateTo: "",
  sort: "-created_at",
  page: 1,
};

const SORT_COLUMNS: SortColumn[] = [
  "created_at",
  "received_date",
  "last_name",
  "first_name",
  "national_id",
  "commitment_number",
  "sender",
  "form_type",
  "status",
];

function isSort(value: string | null): value is RecordSort {
  return value !== null && SORT_COLUMNS.includes(value.replace(/^-/, "") as SortColumn);
}

/**
 * Clicking a column: ascending first (dates start with the newest), and a second
 * click on the same column turns it around.
 */
export function nextSort(current: RecordSort, column: SortColumn): RecordSort {
  if (current === column) return `-${column}`;
  if (current === `-${column}`) return column;
  return column === "received_date" || column === "created_at" ? `-${column}` : column;
}

/** How the table is sorted by this column, for aria-sort. */
export function sortDirection(current: RecordSort, column: SortColumn): "ascending" | "descending" | "none" {
  if (current === column) return "ascending";
  if (current === `-${column}`) return "descending";
  return "none";
}

const STATUSES: RecordStatus[] = ["pending", "approved"];
const FORM_TYPES = Object.keys(FORM_TYPE_TEXT) as FormType[];
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** What the URL says. Anything it can't use is left out, never an error. */
export function parseFilters(params: URLSearchParams): RecordFilters {
  const status = params.get("status");
  const formType = params.get("form_type");
  const page = Number(params.get("page"));
  const date = (name: string) => {
    const value = params.get(name) ?? "";
    return ISO_DATE.test(value) ? value : "";
  };
  return {
    q: (params.get("q") ?? "").trim(),
    status: STATUSES.includes(status as RecordStatus) ? (status as RecordStatus) : null,
    needsReview: params.get("needs_review") === "true",
    sender: (params.get("sender") ?? "").trim(),
    formType: FORM_TYPES.includes(formType as FormType) ? (formType as FormType) : null,
    dateFrom: date("date_from"),
    dateTo: date("date_to"),
    sort: isSort(params.get("sort")) ? (params.get("sort") as RecordSort) : NO_FILTERS.sort,
    page: Number.isInteger(page) && page > 1 ? page : 1,
  };
}

/** The filters as URL parameters, in the API's names. Defaults are left out. */
export function toParams(filters: RecordFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.status) params.set("status", filters.status);
  if (filters.needsReview) params.set("needs_review", "true");
  if (filters.sender) params.set("sender", filters.sender);
  if (filters.formType) params.set("form_type", filters.formType);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.sort !== NO_FILTERS.sort) params.set("sort", filters.sort);
  if (filters.page > 1) params.set("page", String(filters.page));
  return params;
}

/** A change to any filter starts again at the first page; only paging keeps it. */
export function withChange(filters: RecordFilters, change: Partial<RecordFilters>): RecordFilters {
  return { ...filters, page: 1, ...change };
}

export function hasFilters(filters: RecordFilters): boolean {
  return toParams({ ...filters, sort: NO_FILTERS.sort, page: 1 }).size > 0;
}

export interface FilterChip {
  key: string;
  label: string;
  /** The change that takes this filter off. */
  clear: Partial<RecordFilters>;
  /** A status chip wears its status color. */
  tone: "pending" | "review" | "approved" | null;
}

/** The filters in use, one chip each, in the order of the controls. */
export function filterChips(filters: RecordFilters): FilterChip[] {
  const chips: FilterChip[] = [];
  if (filters.q) chips.push({ key: "q", label: t("records.active.search", { q: filters.q }), clear: { q: "" }, tone: null });
  if (filters.needsReview) {
    const label = t("records.counts.review");
    chips.push({ key: "status", label, clear: { status: null, needsReview: false }, tone: "review" });
  } else if (filters.status === "pending") {
    chips.push({ key: "status", label: t("records.counts.pending"), clear: { status: null }, tone: "pending" });
  } else if (filters.status === "approved") {
    chips.push({ key: "status", label: t("records.counts.approved"), clear: { status: null }, tone: "approved" });
  }
  if (filters.sender) {
    const label = t("records.active.sender", { sender: filters.sender });
    chips.push({ key: "sender", label, clear: { sender: "" }, tone: null });
  }
  if (filters.formType) {
    const label = t("records.active.form", { form: FORM_TYPE_TEXT[filters.formType] });
    chips.push({ key: "form", label, clear: { formType: null }, tone: null });
  }
  if (filters.dateFrom || filters.dateTo) {
    const from = formatDate(filters.dateFrom);
    const to = formatDate(filters.dateTo);
    const range = !filters.dateTo
      ? t("records.active.from", { date: from })
      : !filters.dateFrom
        ? t("records.active.to", { date: to })
        : t("records.active.between", { from, to });
    const label = t("records.active.dates", { range });
    chips.push({ key: "dates", label, clear: { dateFrom: "", dateTo: "" }, tone: null });
  }
  return chips;
}

export type ExportFormat = "csv" | "json";

/** GET /api/v1/records/export for these filters: every record they show, not one page (D19). */
export function exportUrl(filters: RecordFilters, format: ExportFormat): string {
  const params = toParams({ ...filters, page: 1 });
  params.set("format", format);
  return `/api/v1/records/export?${params}`;
}

/** GET /api/v1/records for these filters: the same names, plus limit and offset. */
export function listUrl(filters: RecordFilters): string {
  const params = toParams({ ...filters, page: 1 });
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String((filters.page - 1) * PAGE_SIZE));
  return `/api/v1/records?${params}`;
}
