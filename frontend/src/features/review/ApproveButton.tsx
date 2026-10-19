// Approve one record (PLAN-DEV-B 3.2). Blocked while a field is still flagged, and
// then it lists what to fix; the server checks again and has the last word (D3).
// Owner: B

import { useId, useState } from "react";
import type { ApiRecord, Saved } from "./recordMutations";
import { blockingFields, fieldTitle } from "./reviewRows";

interface Props {
  record: ApiRecord;
  onApprove: (record: ApiRecord) => Promise<Saved>;
}

export function ApproveButton({ record, onApprove }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hintId = useId();

  if (record.status === "approved") {
    return <span className="review-approved">✓ אושר</span>;
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
        disabled={busy || blocking.length > 0}
        aria-describedby={blocking.length > 0 ? hintId : undefined}
        onClick={(event) => {
          event.stopPropagation();
          void approve();
        }}
      >
        {busy ? "מאשרת…" : "אישור"}
      </button>
      {blocking.length > 0 && (
        <span id={hintId} className="review-blocking">
          לטפל קודם ב: {blocking.map(fieldTitle).join(", ")}
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
