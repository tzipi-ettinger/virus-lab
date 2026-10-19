// Made-up records for the review tests. No real names or IDs.
// Owner: B

import type { components } from "../../api/schema";

type ApiRecord = components["schemas"]["Record"];
type FormField = components["schemas"]["FormField"];

export function field(value: string | null, over: Partial<FormField> = {}): FormField {
  return {
    raw: value,
    value,
    model_status: value ? "found" : "not_found",
    evidence: null,
    issues: [],
    needs_review: false,
    corrected: false,
    confirmed: false,
    ...over,
  };
}

export const flagged = (value: string | null, message = "יש לבדוק"): Partial<FormField> => ({
  value,
  raw: value,
  needs_review: true,
  issues: [{ code: "FIELD_UNCLEAR", severity: "warning", message }],
});

export function record(over: Partial<ApiRecord> = {}): ApiRecord {
  return {
    record_id: "r1",
    page_id: "p1",
    source_file: "part1.pdf",
    page_number: 1,
    continuation_pages: [],
    continuation_page_ids: [],
    commitment_index: 0,
    status: "pending",
    version: 1,
    form_type: "hmo_form",
    fields: {
      first_name: field("דנה"),
      last_name: field("לוי"),
      national_id: field("011223344"),
      received_date: field("2026-10-09"),
      sender: field("מכבי"),
      commitment_number: field("50364186"),
    },
    central_numbers: [field("948062"), field("123456")],
    issues: [],
    needs_review: false,
    created_at: "2026-10-19T09:00:00Z",
    updated_at: "2026-10-19T09:00:00Z",
    approved_at: null,
    ...over,
  };
}
