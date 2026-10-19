// Tests for the review table's rows: merging upload answers, confidence labels.
// Owner: B

import { describe, expect, test } from "vitest";
import type { components } from "../../api/schema";
import { confidence, fieldCell, findRecord, listCell, mergeRecords, statusText } from "./reviewRows";

type ApiRecord = components["schemas"]["Record"];
type FormField = components["schemas"]["FormField"];

function field(over: Partial<FormField> = {}): FormField {
  return {
    raw: "1",
    value: "1",
    model_status: "found",
    evidence: null,
    issues: [],
    needs_review: false,
    corrected: false,
    confirmed: false,
    ...over,
  };
}

function record(id: string, over: Partial<ApiRecord> = {}): ApiRecord {
  return {
    record_id: id,
    page_id: `p_${id}`,
    source_file: "a.pdf",
    page_number: 1,
    continuation_pages: [],
    commitment_index: 0,
    status: "pending",
    version: 1,
    form_type: "hmo_form",
    fields: {
      first_name: field(),
      last_name: field(),
      national_id: field(),
      received_date: field(),
      sender: field(),
      commitment_number: field(),
    },
    central_numbers: [],
    issues: [],
    needs_review: false,
    created_at: "2026-10-19T00:00:00Z",
    updated_at: "2026-10-19T00:00:00Z",
    approved_at: null,
    ...over,
  };
}

const ids = (records: ApiRecord[]) => records.map((r) => r.record_id);

describe("mergeRecords", () => {
  test("adds new records after the ones already there, in their order", () => {
    expect(ids(mergeRecords([record("a")], [record("b"), record("c")]))).toEqual(["a", "b", "c"]);
  });

  test("replaces a known record in place with the newer copy", () => {
    const merged = mergeRecords([record("a"), record("b")], [record("a", { version: 2 })]);
    expect(ids(merged)).toEqual(["a", "b"]);
    expect(merged[0].version).toBe(2);
  });

  test("an answer with no records changes nothing", () => {
    const current = [record("a")];
    expect(mergeRecords(current, [])).toEqual(current);
  });
});

describe("findRecord", () => {
  test("finds by id, and gives null for none or an unknown id", () => {
    const records = [record("a"), record("b")];
    expect(findRecord(records, "b")?.record_id).toBe("b");
    expect(findRecord(records, null)).toBeNull();
    expect(findRecord(records, "x")).toBeNull();
  });
});

describe("confidence", () => {
  test.each([
    [field(), "sure"],
    [field({ model_status: "unclear", needs_review: true }), "check"],
    [field({ needs_review: true }), "check"],
    [field({ model_status: "not_found", value: null, raw: null }), "missing"],
    [field({ corrected: true, needs_review: true }), "corrected"],
    [field({ confirmed: true, needs_review: false, model_status: "unclear" }), "confirmed"],
  ] as const)("%o is %s", (f, expected) => {
    expect(confidence(f)).toBe(expected);
  });
});

describe("cells", () => {
  test("a field cell carries its value, flag and issue messages", () => {
    const issue = { code: "ID_CHECKSUM_INVALID", severity: "error", message: "ספרת ביקורת שגויה" } as const;
    expect(fieldCell(field({ value: "012", needs_review: true, issues: [issue] }))).toEqual({
      text: "012",
      confidence: "check",
      flagged: true,
      issues: ["ספרת ביקורת שגויה"],
    });
  });

  test("a list cell joins the values and takes its least certain item", () => {
    const cell = listCell([field({ value: "11" }), field({ value: "22", needs_review: true })]);
    expect(cell.text).toBe("11, 22");
    expect(cell.confidence).toBe("check");
    expect(cell.flagged).toBe(true);
  });

  test("an empty list is not found, and not flagged", () => {
    expect(listCell([])).toMatchObject({ text: "", confidence: "missing", flagged: false });
  });
});

describe("statusText", () => {
  test.each([
    [record("a", { needs_review: true }), "דורש בדיקה"],
    [record("a"), "מוכן לאישור"],
    [record("a", { status: "approved" }), "אושר"],
  ])("%#", (r, expected) => {
    expect(statusText(r)).toBe(expected);
  });
});
