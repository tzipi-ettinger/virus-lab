// The records screen's filters live in the URL, not in state (PLAN-DEV-B 3.3):
// a reload, the back button or a shared link opens the same view. No React here.
// Owner: B

import type { components } from "../../api/schema";
import { FORM_TYPE_TEXT } from "../review/reviewRows";

export type RecordStatus = components["schemas"]["RecordSummary"]["status"];
export type FormType = components["schemas"]["RecordSummary"]["form_type"];

export const PAGE_SIZE = 50;

export interface RecordFilters {
  q: string;
  status: RecordStatus | null;
  needsReview: boolean; // only records with a field still flagged
  sender: string;
  formType: FormType | null;
  dateFrom: string; // YYYY-MM-DD, received_date, inclusive
  dateTo: string;
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
  page: 1,
};

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
  if (filters.page > 1) params.set("page", String(filters.page));
  return params;
}

/** A change to any filter starts again at the first page; only paging keeps it. */
export function withChange(filters: RecordFilters, change: Partial<RecordFilters>): RecordFilters {
  return { ...filters, page: 1, ...change };
}

export function hasFilters(filters: RecordFilters): boolean {
  return toParams({ ...filters, page: 1 }).size > 0;
}

/** GET /api/v1/records for these filters: the same names, plus limit and offset. */
export function listUrl(filters: RecordFilters): string {
  const params = toParams({ ...filters, page: 1 });
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String((filters.page - 1) * PAGE_SIZE));
  return `/api/v1/records?${params}`;
}
