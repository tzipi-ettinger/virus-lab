// "Approve all ready" (D20): one click for every pending record with nothing left
// to fix. The server checks each one again, so some may be skipped; the summary
// says how many were approved and how many are left. With nothing ready there is no
// button (a big button that can't be pressed only draws the eye), just a short note.
// Owner: B

import { useState } from "react";
import type { ApiRecord, BulkApproveResponse } from "./recordMutations";
import { isReady, skipReason } from "./reviewRows";

interface Props {
  records: ApiRecord[];
  onApproveMany: (records: ApiRecord[]) => Promise<BulkApproveResponse | string>;
  /** Why each skipped record was skipped, for its row. */
  onSkipped: (reasons: Record<string, string>) => void;
}

export function ApproveAllBar({ records, onApproveMany, onSkipped }: Props) {
  const ready = records.filter(isReady);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<{ text: string; failed: boolean } | null>(null);

  async function approveAll() {
    setBusy(true);
    const pendingBefore = records.filter((r) => r.status === "pending").length;
    const answer = await onApproveMany(ready);
    setBusy(false);
    if (typeof answer === "string") {
      setSummary({ text: answer, failed: true });
      return;
    }
    onSkipped(Object.fromEntries(answer.skipped.map((s) => [s.record_id, skipReason(s)])));
    const left = pendingBefore - answer.approved.length;
    setSummary({
      text:
        left > 0
          ? `אושרו ${answer.approved.length} רשומות. ${left} נשארו לבדיקה`
          : `אושרו ${answer.approved.length} רשומות. כל הרשומות אושרו`,
      failed: false,
    });
  }

  return (
    <div className="review-approve-all">
      {ready.length > 0 || busy ? (
        <button type="button" disabled={busy} onClick={() => void approveAll()}>
          {busy ? "מאשרת…" : `✓ אשרי את כל המוכנות (${ready.length})`}
        </button>
      ) : (
        !summary && <span className="review-approve-all-note">אישור גורף יופיע כשיהיו רשומות מוכנות</span>
      )}
      {summary && (
        <span className={summary.failed ? "review-cell-error" : "review-summary"} role="status">
          {summary.text}
        </span>
      )}
    </div>
  );
}
