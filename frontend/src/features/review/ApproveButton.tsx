// Approve one record (PLAN-DEV-B 3.2). Blocked while a field is still flagged, and
// then it lists what to fix; the server checks again and has the last word (D3).
// Once nothing is left to fix it turns green, with a small pop, so "all good" shows.
// Owner: B

import { useId, useState } from "react";
import { t } from "../../i18n";
import type { ApiRecord, Saved } from "./recordMutations";
import { blockingFields, fieldTitle } from "./reviewRows";

interface Props {
  record: ApiRecord;
  onApprove: (record: ApiRecord) => Promise<Saved>;
  /** Approved on screen, still waiting for its "undo" to run out (useUndo). */
  queued?: boolean;
}

export function ApproveButton({ record, onApprove, queued = false }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hintId = useId();

  if (record.status === "approved" || queued) {
    return <span className="review-approved">{t("review.approved")}</span>;
  }
  const blocking = blockingFields(record);

  async function approve() {
    setBusy(true);
    const message = await onApprove(record);
    setBusy(false);
    setError(message);
  }

  return (
    <span className="review-approve">
      <button
        type="button"
        className={blocking.length === 0 ? "is-ready" : undefined}
        disabled={busy || blocking.length > 0}
        aria-describedby={blocking.length > 0 ? hintId : undefined}
        onClick={(event) => {
          event.stopPropagation();
          void approve();
        }}
      >
        {busy ? (
          t("review.approving")
        ) : (
          <>
            {blocking.length === 0 && <span aria-hidden="true">✓ </span>}
            {t("review.approve")}
          </>
        )}
      </button>
      {blocking.length > 0 && (
        <span id={hintId} className="review-blocking">
          {t("review.fixFirst", { fields: blocking.map(fieldTitle).join(", ") })}
        </span>
      )}
      {error && (
        <span className="review-cell-error" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
