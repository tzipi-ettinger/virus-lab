// Upload and review screen: the one place that holds the records and the selected
// row. UploadPanel (A) sends records up; the list picks one and RecordPanel opens it,
// with A's DocumentPreview inside (#32). The selection is kept as an id, so a newer
// copy of the record shows.
// Owner: B

import { useCallback, useState } from "react";
import { usePageTitle } from "../../shared/usePageTitle";
import { UploadPanel } from "../upload/UploadPanel";
import type { ApiRecord } from "./recordMutations";
import { RecordPanel } from "./RecordPanel";
import { ReviewTable } from "./ReviewTable";
import { findRecord, mergeRecords, replaceRecords } from "./reviewRows";
import "./ReviewPage.css";

export function ReviewPage() {
  usePageTitle("העלאה ובדיקה");
  const [records, setRecords] = useState<ApiRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reveal, setReveal] = useState(0); // grows with each row picked in the list
  // Nothing picked (yet, or the picked one was deleted): the first record is open,
  // so the panel isn't empty while there is something to review.
  const selected = findRecord(records, selectedId) ?? records[0] ?? null;
  // Stable, so the save functions keep their identity between renders.
  const onRecords = useCallback(
    (changed: ApiRecord[]) => setRecords((current) => replaceRecords(current, changed)),
    [],
  );
  const pick = useCallback((recordId: string, show: boolean) => {
    setSelectedId(recordId);
    if (show) setReveal((n) => n + 1);
  }, []);
  const onRemoved = useCallback((recordId: string) => {
    setRecords((current) => current.filter((r) => r.record_id !== recordId));
    setSelectedId((picked) => (picked === recordId ? null : picked));
  }, []);

  return (
    <div className="review-page">
      {/* The nav already shows the screen's name; the heading is for screen readers. */}
      <h1 className="visually-hidden">העלאה ובדיקה</h1>
      <UploadPanel onResult={(result) => setRecords((current) => mergeRecords(current, result.records))} />
      <div className="review-page-work">
        <ReviewTable
          records={records}
          selectedId={selected?.record_id ?? null}
          onSelect={pick}
          onRecords={onRecords}
        />
        <RecordPanel
          record={selected}
          records={records}
          onSelect={setSelectedId}
          onRecords={onRecords}
          onRemoved={onRemoved}
          reveal={reveal}
        />
      </div>
    </div>
  );
}

export default ReviewPage;
