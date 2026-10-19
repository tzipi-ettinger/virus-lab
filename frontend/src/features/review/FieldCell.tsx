// One field in the review table: its value and confidence label, edited in place
// (PLAN-DEV-B 3.1, 3.3). Click or Enter opens it; Enter or leaving the field saves,
// Escape cancels. A flagged value can be confirmed as it is. The server's answer
// sets the new flags.
// Owner: B

import { useRef, useState, type KeyboardEvent } from "react";
import type { components } from "../../api/schema";
import type { FieldEdit, Saved } from "./recordMutations";
import { CONFIDENCE_TEXT, fieldCell } from "./reviewRows";

type FormField = components["schemas"]["FormField"];

interface FieldCellProps {
  title: string;
  field: FormField;
  editable: boolean; // false once the record is approved
  onSave: (edit: FieldEdit) => Promise<Saved>;
  /** A closed list (the senders): edited with a dropdown that saves on pick. */
  options?: string[];
}

export function FieldCell({ title, field, editable, onSave, options }: FieldCellProps) {
  const cell = fieldCell(field);
  const [draft, setDraft] = useState<string | null>(null); // null: not editing
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancelled = useRef(false);

  async function save(edit: FieldEdit, keepOpen: boolean) {
    setBusy(true);
    const message = await onSave(edit);
    setBusy(false);
    setError(message);
    if (message === null || !keepOpen) setDraft(null);
  }

  function commit() {
    if (draft === null || busy) return;
    const value = draft.trim();
    if (value === (field.value ?? "")) {
      setDraft(null);
      return;
    }
    void save({ value: value || null }, true); // on a conflict the typed text stays
  }

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      commit();
    } else if (event.key === "Escape") {
      cancelled.current = true;
      setDraft(null);
      setError(null);
    }
  }

  const content = (
    <>
      <span className="review-value">{cell.text ? <bdi>{cell.text}</bdi> : "—"}</span>
      <span className={`review-confidence is-${cell.confidence}`}>{CONFIDENCE_TEXT[cell.confidence]}</span>
    </>
  );

  return (
    <td
      className={cell.flagged ? "review-cell is-flagged" : "review-cell"}
      title={cell.issues.join("\n") || undefined}
    >
      {draft !== null && options ? (
        <select
          className="review-cell-input"
          aria-label={`עריכת ${title}`}
          value={draft}
          disabled={busy}
          autoFocus
          onChange={(event) => {
            const value = event.target.value;
            setDraft(value);
            if (value !== (field.value ?? "")) void save({ value: value || null }, true);
          }}
          onKeyDown={onKeyDown}
          onClick={(event) => event.stopPropagation()}
          onBlur={() => {
            if (!busy) setDraft(null);
          }}
        >
          {/* Text that isn't on the list stays as read, and stays flagged. */}
          {field.value && !options.includes(field.value) && (
            <option value={field.value}>כפי שנקרא: {field.value} (לא ברשימה)</option>
          )}
          <option value="">ריק</option>
          {options.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      ) : draft !== null ? (
        <input
          className="review-cell-input"
          aria-label={`עריכת ${title}`}
          value={draft}
          disabled={busy}
          autoFocus
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          onClick={(event) => event.stopPropagation()}
          onBlur={() => {
            if (cancelled.current) cancelled.current = false;
            else commit();
          }}
        />
      ) : editable ? (
        <button
          type="button"
          className="review-cell-value"
          aria-label={`${title}: ${cell.text || "ריק"}, ${CONFIDENCE_TEXT[cell.confidence]}. לעריכה`}
          onClick={() => {
            setError(null);
            setDraft(field.value ?? "");
          }}
        >
          {content}
        </button>
      ) : (
        content
      )}
      {draft === null && editable && field.needs_review && (
        // The value is right as it is: the flag goes, the issue stays shown.
        <button
          type="button"
          className="review-confirm"
          disabled={busy}
          aria-label={`אישור ערך: ${title}`}
          onClick={(event) => {
            event.stopPropagation();
            void save({ confirmed: true }, false);
          }}
        >
          ✓ אישור ערך
        </button>
      )}
      {error && (
        <span className="review-cell-error" role="alert">
          {error}
        </span>
      )}
    </td>
  );
}
