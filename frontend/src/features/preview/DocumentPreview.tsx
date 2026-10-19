// Original page next to the selected row (selection comes in as a prop).
// Owner: A

import { useState } from "react";
import { MAX_ZOOM, previewPages, zoomIn, zoomOut, type ApiRecord, type Zoom } from "./previewPages";
import "./DocumentPreview.css";

interface DocumentPreviewProps {
  // The selected record, or null when nothing is selected (#32).
  record: ApiRecord | null;
}

export function DocumentPreview({ record }: DocumentPreviewProps) {
  return (
    <section className="preview" aria-labelledby="preview-title">
      <h2 id="preview-title" className="preview-title">הטופס המקורי</h2>
      {record ? (
        // A different form starts on its first page, fitted to the width. Records of
        // the same form (one per commitment) share its pages, so page and zoom stay.
        <Pages key={record.page_id} record={record} />
      ) : (
        <p className="preview-empty">בחרי שורה בטבלה כדי לראות את הטופס המקורי</p>
      )}
    </section>
  );
}

function Pages({ record }: { record: ApiRecord }) {
  const pages = previewPages(record);
  const [index, setIndex] = useState(0);
  const [zoom, setZoom] = useState<Zoom>("fit");
  const [failed, setFailed] = useState<string | null>(null); // the image URL that did not load
  const page = pages[index];

  return (
    <>
      <p className="preview-source">
        <bdi>{record.source_file}</bdi>, עמוד {page.pageNumber}
        {pages.length > 1 && ` (${index + 1} מתוך ${pages.length} בטופס)`}
      </p>

      <div className="preview-toolbar" role="group" aria-label="תצוגת העמוד">
        {pages.length > 1 && (
          <div className="preview-pages">
            {pages.map((p, i) => (
              <button
                key={p.pageNumber}
                type="button"
                className="preview-button"
                aria-pressed={i === index}
                onClick={() => setIndex(i)}
              >
                עמוד {p.pageNumber}
              </button>
            ))}
          </div>
        )}
        <div className="preview-zoom">
          <button
            type="button"
            className="preview-button"
            onClick={() => setZoom(zoomOut)}
            disabled={zoom === "fit"}
            aria-label="הקטנה"
          >
            −
          </button>
          <button
            type="button"
            className="preview-button"
            onClick={() => setZoom("fit")}
            aria-pressed={zoom === "fit"}
          >
            התאמה לרוחב
          </button>
          <button
            type="button"
            className="preview-button"
            onClick={() => setZoom(zoomIn)}
            disabled={zoom === MAX_ZOOM}
            aria-label="הגדלה"
          >
            +
          </button>
          <span className="preview-zoom-level" aria-live="polite">
            {zoom === "fit" ? "רוחב מלא" : `${zoom}%`}
          </span>
        </div>
      </div>

      <div className="preview-frame" role="region" tabIndex={0} aria-label="תמונת העמוד. אפשר לגלול עם החיצים">
        {page.imageUrl === null ? (
          <p className="preview-message">התמונה של העמוד הזה לא זמינה. העמוד שייך לטופס הזה</p>
        ) : failed === page.imageUrl ? (
          <p className="preview-message" role="alert">לא ניתן להציג את תמונת העמוד</p>
        ) : (
          <img
            key={page.imageUrl}
            className="preview-image"
            src={page.imageUrl}
            alt={`עמוד ${page.pageNumber} של הטופס`}
            style={{ inlineSize: zoom === "fit" ? "100%" : `${zoom}%` }}
            onError={() => setFailed(page.imageUrl)}
          />
        )}
      </div>
    </>
  );
}

export default DocumentPreview;
