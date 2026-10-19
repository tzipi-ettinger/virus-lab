// The central numbers of a record: a list, each item with its own confidence and
// "אישור ערך", edited together (PLAN-DEV-B 3.2). Saving sends the full new list:
// an item kept by its position keeps its raw, a new one has no position (SPEC 7.4).
// Owner: B

import { useState } from "react";
import type { components } from "../../api/schema";
import { centralsEdit, keepCentrals, type ListDraft, type ListItemEdit, type Saved } from "./recordMutations";
import { CONFIDENCE_TEXT, fieldCell, listCell } from "./reviewRows";

type FormField = components["schemas"]["FormField"];

interface Props {
  items: FormField[];
  editable: boolean;
  onSave: (items: ListItemEdit[]) => Promise<Saved>;
}

export function CentralNumbersCell({ items, editable, onSave }: Props) {
  const summary = listCell(items);
  const [drafts, setDrafts] = useState<ListDraft[] | null>(null); // null: not editing
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(edits: ListItemEdit[], closeOnError: boolean) {
    setBusy(true);
    const message = await onSave(edits);
    setBusy(false);
    setError(message);
    if (message === null || closeOnError) setDrafts(null);
  }

  function save() {
    if (drafts === null) return;
    const edits = centralsEdit(items, drafts);
    if (edits === null) setDrafts(null);
    else void send(edits, false);
  }

  const update = (i: number, value: string) =>
    setDrafts((current) => current && current.map((d, j) => (j === i ? { ...d, value } : d)));

  return (
    <td
      className={summary.flagged ? "review-cell is-flagged" : "review-cell"}
      title={summary.issues.join("\n") || undefined}
      onClick={drafts !== null ? (event) => event.stopPropagation() : undefined}
    >
      {drafts !== null ? (
        <div className="review-list-editor" role="group" aria-label="עריכת מספרים מרכזיים">
          {drafts.map((d, i) => (
            <div key={i} className="review-list-item">
              <input
                className="review-cell-input"
                aria-label={`מספר מרכזי ${i + 1}`}
                inputMode="numeric"
                value={d.value}
                disabled={busy}
                autoFocus={i === drafts.length - 1 && d.idx === null}
                onChange={(event) => update(i, event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") save();
                  if (event.key === "Escape") setDrafts(null);
                }}
              />
              <button
                type="button"
                aria-label={`הסרת מספר מרכזי ${i + 1}`}
                disabled={busy}
                onClick={() => setDrafts(drafts.filter((_, j) => j !== i))}
              >
                ✕
              </button>
            </div>
          ))}
          <div className="review-list-actions">
            <button type="button" disabled={busy} onClick={() => setDrafts([...drafts, { idx: null, value: "" }])}>
              + הוספה
            </button>
            <button type="button" disabled={busy} onClick={save}>
              שמירה
            </button>
            <button type="button" disabled={busy} onClick={() => setDrafts(null)}>
              ביטול
            </button>
          </div>
        </div>
      ) : (
        <>
          {items.length === 0 && <span className="review-value">—</span>}
          <ul className="review-list">
            {items.map((item, idx) => {
              const cell = fieldCell(item);
              return (
                <li key={idx} className={cell.flagged ? "is-flagged" : undefined}>
                  <span className="review-value">{cell.text ? <bdi>{cell.text}</bdi> : "—"}</span>
                  <span className={`review-confidence is-${cell.confidence}`}>{CONFIDENCE_TEXT[cell.confidence]}</span>
                  {editable && item.needs_review && (
                    <button
                      type="button"
                      className="review-confirm"
                      disabled={busy}
                      aria-label={`אישור ערך: מספר מרכזי ${idx + 1}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        void send(keepCentrals(items, { [idx]: { confirmed: true } }), true);
                      }}
                    >
                      ✓ אישור ערך
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
          {editable && (
            <button
              type="button"
              className="review-list-edit"
              disabled={busy}
              onClick={(event) => {
                event.stopPropagation();
                setError(null);
                setDrafts(items.map((item, idx) => ({ idx, value: item.value ?? "" })));
              }}
            >
              עריכת הרשימה
            </button>
          )}
        </>
      )}
      {error && (
        <span className="review-cell-error" role="alert">
          {error}
        </span>
      )}
    </td>
  );
}
