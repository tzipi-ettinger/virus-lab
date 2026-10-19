// What the review table shows for each record, and how records from the upload
// join it. No React here, so it is tested without a browser.
// Owner: B

import type { components } from "../../api/schema";

type ApiRecord = components["schemas"]["Record"];
type FormField = components["schemas"]["FormField"];
type FieldName = keyof components["schemas"]["RecordFields"];

// Records from /extract join the table as each file's answer arrives. A record
// that is already there (same record_id) is replaced in place, so a newer copy
// from the server wins and the row keeps its position.
export function mergeRecords(current: ApiRecord[], incoming: ApiRecord[]): ApiRecord[] {
  const byId = new Map(incoming.map((r) => [r.record_id, r]));
  const merged = current.map((r) => byId.get(r.record_id) ?? r);
  const known = new Set(current.map((r) => r.record_id));
  return [...merged, ...incoming.filter((r) => !known.has(r.record_id))];
}

export function findRecord(records: ApiRecord[], id: string | null): ApiRecord | null {
  return records.find((r) => r.record_id === id) ?? null;
}

// The confidence label every field carries (PLAN-DEV-B 3.0), in text, not color only.
export type Confidence = "sure" | "check" | "missing" | "corrected" | "confirmed";

export const CONFIDENCE_TEXT: Record<Confidence, string> = {
  sure: "בטוח",
  check: "לא בטוח – בדקי",
  missing: "לא נמצא",
  corrected: "תוקן",
  confirmed: "אושר ידנית",
};

export function confidence(field: FormField): Confidence {
  if (field.confirmed) return "confirmed";
  if (field.corrected) return "corrected";
  if (field.model_status === "not_found" && !field.value) return "missing";
  if (field.needs_review || field.model_status === "unclear") return "check";
  return "sure";
}

export interface Cell {
  text: string;
  confidence: Confidence;
  flagged: boolean; // needs review: orange, and blocks approval
  issues: string[]; // the messages, for the cell's title
}

export function fieldCell(field: FormField): Cell {
  return {
    text: field.value ?? "",
    confidence: confidence(field),
    flagged: field.needs_review,
    issues: field.issues.map((i) => i.message),
  };
}

const RANK: Confidence[] = ["check", "missing", "corrected", "confirmed", "sure"];

// Central numbers are a list: one cell, labeled by its least certain item.
export function listCell(items: FormField[]): Cell {
  if (items.length === 0) return { text: "", confidence: "missing", flagged: false, issues: [] };
  const cells = items.map(fieldCell);
  return {
    text: cells.map((c) => c.text).filter(Boolean).join(", "),
    confidence: RANK.find((c) => cells.some((cell) => cell.confidence === c)) ?? "sure",
    flagged: cells.some((c) => c.flagged),
    issues: cells.flatMap((c) => c.issues),
  };
}

export const FIELD_COLUMNS: { name: FieldName; title: string }[] = [
  { name: "national_id", title: "ת״ז" },
  { name: "first_name", title: "שם פרטי" },
  { name: "last_name", title: "שם משפחה" },
  { name: "commitment_number", title: "מספר התחייבות" },
  { name: "sender", title: "גורם שולח" },
  { name: "received_date", title: "תאריך קבלה" },
];

export const FORM_TYPE_TEXT: Record<ApiRecord["form_type"], string> = {
  hmo_form: "טופס קופה",
  hospital_form: "טופס בית חולים",
  hospital_system_screenshot: "צילום מסך ממערכת",
  lab_report: "דוח מעבדה",
  private_lab: "מעבדה פרטית",
  government: "גוף ממשלתי",
  unknown: "לא ידוע",
};

export function statusText(record: ApiRecord): string {
  if (record.status === "approved") return "אושר";
  return record.needs_review ? "דורש בדיקה" : "מוכן לאישור";
}
