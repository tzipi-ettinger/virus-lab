// Delete a pending record, e.g. a duplicate (A5). Asks first: it can't be undone.
// Approved records stay, so they have no button.
// Owner: B

import { useState } from "react";
import { t } from "../../i18n";
import type { ApiRecord, Saved } from "./recordMutations";

interface Props {
  record: ApiRecord;
  onDelete: (record: ApiRecord) => Promise<Saved>;
  onDeleted: (record: ApiRecord) => void;
  confirm?: (question: string) => boolean;
}

export function DeleteButton({ record, onDelete, onDeleted, confirm = window.confirm }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (record.status !== "pending") return null;

  async function remove() {
    const name = [record.fields.first_name.value, record.fields.last_name.value].filter(Boolean).join(" ");
    const question = t(name ? "review.delete.questionOf" : "review.delete.question", {
      name,
      file: record.source_file,
      page: record.page_number,
    });
    if (!confirm(question)) return;
    setBusy(true);
    const message = await onDelete(record);
    setBusy(false);
    setError(message);
    if (message === null) onDeleted(record);
  }

  return (
    <>
      <button
        type="button"
        className="review-delete"
        disabled={busy}
        onClick={(event) => {
          event.stopPropagation();
          void remove();
        }}
      >
        {t("review.delete.button")}
      </button>
      {error && (
        <span className="review-cell-error" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
