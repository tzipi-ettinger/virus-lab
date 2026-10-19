// Saving a correction or a confirmation (PLAN-DEV-B 3.3, 3.5). The server reruns
// the rules and its answer replaces the local copy: it is the source of truth for
// flags. Every change carries the record's version, so two windows can't overwrite
// each other silently.
// Owner: B

import { useCallback } from "react";
import { ApiError, apiFetch } from "../../api/client";
import type { components } from "../../api/schema";
import { fieldTitle } from "./reviewRows";

export type ApiRecord = components["schemas"]["Record"];
export type FieldEdit = components["schemas"]["FieldEdit"];
export type ListItemEdit = components["schemas"]["ListItemEdit"];
export type FieldName = keyof components["schemas"]["RecordFieldsEdit"];
type RecordPatch = components["schemas"]["RecordPatch"];
type RecordPatchResponse = components["schemas"]["RecordPatchResponse"];
export type BulkApproveResponse = components["schemas"]["BulkApproveResponse"];
export type SkippedRecord = components["schemas"]["SkippedRecord"];

export const VERSION_CONFLICT =
  "הרשומה עודכנה בינתיים בחלון אחר. טענתי את הגרסה החדשה, ומה שהקלדת נשאר: בדקי ושמרי שוב";

/** The Hebrew message for a failed change: what happened and what to do. */
export function mutationError(error: unknown): string {
  if (!(error instanceof ApiError)) return "משהו השתבש. נסי שוב";
  switch (error.type) {
    case "version_conflict":
      return VERSION_CONFLICT;
    case "record_approved":
      return "הרשומה כבר אושרה, ואי אפשר לשנות אותה";
    case "sibling_approved":
      return "רשומה אחרת מאותו טופס כבר אושרה, ולכן אי אפשר לשנות שדה שמשותף לשתיהן";
    case "review_required":
      return `אי אפשר לאשר עדיין. יש לטפל קודם ב: ${error.blockingFields.map(fieldTitle).join(", ")}`;
    case "record_not_found":
    case "not_found":
      return "הרשומה לא נמצאה. ייתכן שנמחקה בחלון אחר";
    default:
      return error.message;
  }
}

export function fieldPatch(record: ApiRecord, name: FieldName, edit: FieldEdit): RecordPatch {
  return { version: record.version, fields: { [name]: edit } };
}

export function centralsPatch(record: ApiRecord, items: ListItemEdit[]): RecordPatch {
  return { version: record.version, central_numbers: items };
}

/** Every central number as it is ({idx} keeps an item), with one change applied. */
export function keepCentrals(items: unknown[], change: Record<number, ListItemEdit> = {}): ListItemEdit[] {
  return items.map((_, idx) => ({ idx, ...change[idx] }));
}

/** One input in the central numbers editor: an item already saved (idx) or a new one. */
export type ListDraft = { idx: number | null; value: string };

/** The list to send, or null when nothing changed. An emptied item is removed. */
export function centralsEdit(items: { value: string | null }[], drafts: ListDraft[]): ListItemEdit[] | null {
  const edits = drafts
    .filter((d) => d.value.trim() !== "")
    .map(({ idx, value }): ListItemEdit => {
      const clean = value.trim();
      if (idx === null) return { value: clean };
      return clean === (items[idx].value ?? "") ? { idx } : { idx, value: clean };
    });
  const unchanged = edits.length === items.length && edits.every((e, i) => e.idx === i && e.value === undefined);
  return unchanged ? null : edits;
}

/** Result of a change: null when saved, or the message to show next to it. */
export type Saved = string | null;

/**
 * Changes to records. `onRecords` gets every record the server sent back: the
 * record itself and the form's other records whose shared field changed too (A3).
 */
export function useRecordMutations(onRecords: (records: ApiRecord[]) => void) {
  /** The message for a failure; on a stale version, also show what the other window saved. */
  const failed = useCallback(
    async (record: ApiRecord, error: unknown): Promise<string> => {
      if (error instanceof ApiError && error.type === "version_conflict") {
        await apiFetch<ApiRecord>(`/api/v1/records/${record.record_id}`).then(
          (fresh) => onRecords([fresh]),
          () => {},
        );
      }
      return mutationError(error);
    },
    [onRecords],
  );

  const send = useCallback(
    async (record: ApiRecord, body: RecordPatch): Promise<Saved> => {
      try {
        const answer = await apiFetch<RecordPatchResponse>(`/api/v1/records/${record.record_id}`, {
          method: "PATCH",
          body,
        });
        onRecords([answer.record, ...answer.siblings]);
        return null;
      } catch (error) {
        return failed(record, error); // the editor keeps the user's text
      }
    },
    [onRecords, failed],
  );

  const approve = useCallback(
    async (record: ApiRecord): Promise<Saved> => {
      try {
        const approved = await apiFetch<ApiRecord>(`/api/v1/records/${record.record_id}/approve`, {
          method: "POST",
          body: { version: record.version },
        });
        onRecords([approved]);
        return null;
      } catch (error) {
        return failed(record, error);
      }
    },
    [onRecords, failed],
  );

  /** "Approve all ready" (D20): the server checks each one and may skip some. */
  const approveMany = useCallback(
    async (records: ApiRecord[]): Promise<BulkApproveResponse | string> => {
      try {
        const answer = await apiFetch<BulkApproveResponse>("/api/v1/records/approve", {
          method: "POST",
          body: { items: records.map((r) => ({ record_id: r.record_id, version: r.version })) },
        });
        onRecords(answer.approved);
        return answer;
      } catch (error) {
        return mutationError(error);
      }
    },
    [onRecords],
  );

  /** Delete a pending record (A5). The caller takes it off the screen when this is null. */
  const remove = useCallback(async (record: ApiRecord): Promise<Saved> => {
    try {
      await apiFetch(`/api/v1/records/${record.record_id}`, { method: "DELETE" });
      return null;
    } catch (error) {
      return mutationError(error);
    }
  }, []);

  const saveField = useCallback(
    (record: ApiRecord, name: FieldName, edit: FieldEdit) => send(record, fieldPatch(record, name, edit)),
    [send],
  );
  const saveCentrals = useCallback(
    (record: ApiRecord, items: ListItemEdit[]) => send(record, centralsPatch(record, items)),
    [send],
  );
  return { saveField, saveCentrals, approve, approveMany, remove };
}
