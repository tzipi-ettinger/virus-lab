// The records filters in the URL (PLAN-DEV-B 3.1, 3.3).
// Owner: B

import { describe, expect, test } from "vitest";
import {
  NO_FILTERS,
  PAGE_SIZE,
  exportUrl,
  hasFilters,
  listUrl,
  nextSort,
  parseFilters,
  sortDirection,
  toParams,
  withChange,
  type RecordFilters,
} from "./filters";

const ALL: RecordFilters = {
  q: "0112",
  status: "approved",
  needsReview: true,
  sender: "מכבי",
  formType: "hmo_form",
  dateFrom: "2026-10-01",
  dateTo: "2026-10-19",
  sort: "-received_date",
  page: 3,
};

describe("filters in the URL", () => {
  test("every filter survives a round trip", () => {
    expect(parseFilters(toParams(ALL))).toEqual(ALL);
  });

  test("no filters is an empty query", () => {
    expect(toParams(NO_FILTERS).toString()).toBe("");
    expect(parseFilters(new URLSearchParams())).toEqual(NO_FILTERS);
  });

  test("values it can't use are left out, not an error", () => {
    const params = new URLSearchParams(
      "status=done&form_type=clalit&date_from=19/10/2026&page=-2&needs_review=yes&sort=search_text",
    );

    expect(parseFilters(params)).toEqual(NO_FILTERS);
  });

  test("a search keeps its leading zeros", () => {
    expect(parseFilters(new URLSearchParams("q=011223344")).q).toBe("011223344");
  });
});

describe("withChange", () => {
  test("a new filter starts again at page 1", () => {
    expect(withChange(ALL, { status: "pending" })).toMatchObject({ status: "pending", page: 1 });
  });

  test("paging keeps the filters", () => {
    expect(withChange(ALL, { page: 4 })).toEqual({ ...ALL, page: 4 });
  });
});

describe("hasFilters", () => {
  test("the page alone is not a filter, and neither is the order", () => {
    expect(hasFilters({ ...NO_FILTERS, page: 2 })).toBe(false);
    expect(hasFilters({ ...NO_FILTERS, sort: "last_name" })).toBe(false);
    expect(hasFilters({ ...NO_FILTERS, sender: "מכבי" })).toBe(true);
  });
});

describe("sorting", () => {
  test("the default order stays out of the URL", () => {
    expect(toParams({ ...NO_FILTERS, sort: "-created_at" }).has("sort")).toBe(false);
    expect(parseFilters(new URLSearchParams("sort=last_name")).sort).toBe("last_name");
  });

  test("a click sorts up, a second click turns it around", () => {
    expect(nextSort("-created_at", "last_name")).toBe("last_name");
    expect(nextSort("last_name", "last_name")).toBe("-last_name");
    expect(nextSort("-last_name", "last_name")).toBe("last_name");
  });

  test("dates start with the newest", () => {
    expect(nextSort("last_name", "received_date")).toBe("-received_date");
  });

  test("a new order starts again at page 1", () => {
    expect(withChange(ALL, { sort: "sender" })).toMatchObject({ sort: "sender", page: 1 });
  });

  test("aria-sort follows the order", () => {
    expect(sortDirection("sender", "sender")).toBe("ascending");
    expect(sortDirection("-sender", "sender")).toBe("descending");
    expect(sortDirection("sender", "status")).toBe("none");
  });
});

describe("exportUrl", () => {
  test("sends the same filters and the format, and never the page", () => {
    const params = new URL(exportUrl(ALL, "csv"), "http://x").searchParams;

    expect(Object.fromEntries(params)).toEqual({
      q: "0112",
      status: "approved",
      needs_review: "true",
      sender: "מכבי",
      form_type: "hmo_form",
      date_from: "2026-10-01",
      date_to: "2026-10-19",
      sort: "-received_date",
      format: "csv",
    });
  });

  test("with no filters, only the format", () => {
    expect(exportUrl(NO_FILTERS, "json")).toBe("/api/v1/records/export?format=json");
  });
});

describe("listUrl", () => {
  test("uses the API's names, with limit and offset for the page", () => {
    const params = new URL(listUrl(ALL), "http://x").searchParams;

    expect(Object.fromEntries(params)).toEqual({
      q: "0112",
      status: "approved",
      needs_review: "true",
      sender: "מכבי",
      form_type: "hmo_form",
      date_from: "2026-10-01",
      date_to: "2026-10-19",
      sort: "-received_date",
      limit: String(PAGE_SIZE),
      offset: String(2 * PAGE_SIZE),
    });
  });
});
