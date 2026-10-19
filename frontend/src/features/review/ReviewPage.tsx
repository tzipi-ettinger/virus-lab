// Upload and review screen: the one place that holds the records and the selected
// row. UploadPanel (A) sends records up, DocumentPreview (A) gets the selected one
// down (#32). The selection is kept as an id, so a newer copy of the record shows.
// Owner: B

import { useState } from "react";
import type { components } from "../../api/schema";
import { DocumentPreview } from "../preview/DocumentPreview";
import { UploadPanel } from "../upload/UploadPanel";
import { ReviewTable } from "./ReviewTable";
import { findRecord, mergeRecords } from "./reviewRows";
import "./ReviewPage.css";

type ApiRecord = components["schemas"]["Record"];

export function ReviewPage() {
  const [records, setRecords] = useState<ApiRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div className="review-page">
      <UploadPanel onResult={(result) => setRecords((current) => mergeRecords(current, result.records))} />
      <div className="review-page-work">
        <ReviewTable records={records} selectedId={selectedId} onSelect={setSelectedId} />
        <DocumentPreview record={findRecord(records, selectedId)} />
      </div>
    </div>
  );
}

export default ReviewPage;
