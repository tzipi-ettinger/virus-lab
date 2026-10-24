// What the review table shows for each record, and how records from the upload
// join it. No React here, so it is tested without a browser.
// Owner: B

import type { components } from "../../api/schema";
import { t } from "../../i18n";

type ApiRecord = components["schemas"]["Record"];
type FormField = components["schemas"]["FormField"];
export type FieldName = keyof components["schemas"]["RecordFields"];

// Records from /extract join the table as each file's answer arrives. A record
// that is already there (same record_id) is replaced in place, so a newer copy
// from the server wins and the row keeps its position.
export function mergeRecords(current: ApiRecord[], incoming: ApiRecord[]): ApiRecord[] {
  const byId = new Map(incoming.map((r) => [r.record_id, r]));
  const merged = current.map((r) => byId.get(r.record_id) ?? r);
  const known = new Set(current.map((r) => r.record_id));
  return [...merged, ...incoming.filter((r) => !known.has(r.record_id))];
}

// After a change the server sends the record and its siblings back. Only rows
// already in the table are replaced: a sibling from an earlier upload stays out.
export function replaceRecords(current: ApiRecord[], incoming: ApiRecord[]): ApiRecord[] {
  const byId = new Map(incoming.map((r) => [r.record_id, r]));
  return current.map((r) => byId.get(r.record_id) ?? r);
}

export function findRecord(records: ApiRecord[], id: string | null): ApiRecord | null {
  return records.find((r) => r.record_id === id) ?? null;
}

// The confidence label every field carries (PLAN-DEV-B 3.0), in text, not color only.
export type Confidence = "sure" | "check" | "missing" | "corrected" | "confirmed";

export const CONFIDENCE_TEXT: Record<Confidence, string> = {
  sure: t("confidence.sure"),
  check: t("confidence.check"),
  missing: t("confidence.missing"),
  corrected: t("confidence.corrected"),
  confirmed: t("confidence.confirmed"),
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
  { name: "national_id", title: t("fields.national_id") },
  { name: "first_name", title: t("fields.first_name") },
  { name: "last_name", title: t("fields.last_name") },
  { name: "commitment_number", title: t("fields.commitment_number") },
  { name: "sender", title: t("fields.sender") },
  { name: "received_date", title: t("fields.received_date") },
];

/**
 * The fields that still block approval, named as the server names them in
 * blocking_fields (rules/records.py): a flagged field, or "central_numbers[i]".
 * An issue on the whole record shows but doesn't block (#59).
 */
export function blockingFields(record: ApiRecord): string[] {
  const names = FIELD_COLUMNS.filter((c) => record.fields[c.name].needs_review).map((c) => c.name as string);
  record.central_numbers.forEach((item, i) => {
    if (item.needs_review) names.push(`central_numbers[${i}]`);
  });
  return names;
}

/** Pending, with nothing left to fix: "approve all ready" sends these. */
export function isReady(record: ApiRecord): boolean {
  return record.status === "pending" && blockingFields(record).length === 0;
}

/** The next pending record with a field to fix, after this one and around: "הבאה לתיקון". */
export function nextToFix(records: ApiRecord[], currentId: string): ApiRecord | null {
  const start = records.findIndex((r) => r.record_id === currentId);
  for (let step = 1; step <= records.length; step++) {
    const r = records[(start + step) % records.length];
    if (r.record_id !== currentId && r.status === "pending" && blockingFields(r).length > 0) return r;
  }
  return null;
}

/**
 * Where to go after approving or deleting a record: the next one to fix, else the
 * next one still pending, else none (the current one stays open).
 */
export function nextAfter(records: ApiRecord[], currentId: string): ApiRecord | null {
  const toFix = nextToFix(records, currentId);
  if (toFix) return toFix;
  const start = records.findIndex((r) => r.record_id === currentId);
  for (let step = 1; step < records.length; step++) {
    const r = records[(start + step) % records.length];
    if (r.status === "pending") return r;
  }
  return null;
}

/** A blocking field's name in Hebrew: "national_id" → ת״ז, "central_numbers[1]" → מספר מרכזי 2. */
export function fieldTitle(name: string): string {
  const central = /^central_numbers\[(\d+)\]$/.exec(name);
  if (central) return t("fields.centralNumberN", { n: Number(central[1]) + 1 });
  return FIELD_COLUMNS.find((c) => c.name === name)?.title ?? name;
}

/** Why "approve all ready" skipped a record, for its row. */
export function skipReason(skipped: components["schemas"]["SkippedRecord"]): string {
  switch (skipped.type) {
    case "review_required":
      return t("review.skipped.blocked", { fields: (skipped.blocking_fields ?? []).map(fieldTitle).join(", ") });
    case "version_conflict":
      return t("review.skipped.conflict");
    case "record_approved":
      return t("review.skipped.approved");
    case "not_found":
      return t("review.skipped.deleted");
  }
}

export const FORM_TYPE_TEXT: Record<ApiRecord["form_type"], string> = {
  hmo_form: t("formTypes.hmo_form"),
  hospital_form: t("formTypes.hospital_form"),
  hospital_system_screenshot: t("formTypes.hospital_system_screenshot"),
  lab_report: t("formTypes.lab_report"),
  private_lab: t("formTypes.private_lab"),
  government: t("formTypes.government"),
  unknown: t("formTypes.unknown"),
};
