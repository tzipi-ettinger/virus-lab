// Upload and review screen: the one place that holds the records and the selected
// row. UploadPanel (A) sends records up, DocumentPreview (A) gets the selected one
// down (#32). The selection is kept as an id, so a newer copy of the record shows.
// Owner: B

import { useCallback, useState } from "react";
import { DocumentPreview } from "../preview/DocumentPreview";
import { UploadPanel } from "../upload/UploadPanel";
import type { ApiRecord } from "./recordMutations";
import { ReviewTable } from "./ReviewTable";
import { findRecord, mergeRecords, replaceRecords } from "./reviewRows";
import "./ReviewPage.css";

export function ReviewPage() {
  const [records, setRecords] = useState<ApiRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Stable, so the table's save functions keep their identity between renders.
  const onRecords = useCallback(
    (changed: ApiRecord[]) => setRecords((current) => replaceRecords(current, changed)),
    [],
  );

  return (
    <div className="review-page">
      <UploadPanel onResult={(result) => setRecords((current) => mergeRecords(current, result.records))} />
      <div className="review-page-work">
        <ReviewTable records={records} selectedId={selectedId} onSelect={setSelectedId} onRecords={onRecords} />
        <DocumentPreview record={findRecord(records, selectedId)} />
      </div>
    </div>
  );
}

export default ReviewPage;
