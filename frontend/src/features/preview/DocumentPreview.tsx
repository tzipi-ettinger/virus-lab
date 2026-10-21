// Original page next to the selected row (selection comes in as a prop). With a
// highlight, it turns to the page the value was read on and boxes the value there.
// Owner: A

import { useEffect, useRef, useState, type HTMLAttributes } from "react";
import {
  MAX_ZOOM,
  boxStyle,
  highlightPageIndex,
  previewPages,
  zoomIn,
  zoomOut,
  type ApiRecord,
  type Highlight,
  type PreviewPage,
  type Zoom,
} from "./previewPages";
import "./DocumentPreview.css";

interface DocumentPreviewProps {
  // The selected record, or null when nothing is selected (#32).
  record: ApiRecord | null;
  // The field under the pointer or in focus next to the preview (field boxes).
  highlight?: Highlight | null;
  // Pointer handlers for the whole preview (useFieldFocus's areaProps).
  pointerArea?: Pick<HTMLAttributes<HTMLElement>, "onMouseEnter" | "onMouseLeave">;
}

export function DocumentPreview({ record, highlight = null, pointerArea }: DocumentPreviewProps) {
  return (
    <section className="preview" aria-labelledby="preview-title" {...pointerArea}>
      <h2 id="preview-title" className="preview-title">הטופס המקורי</h2>
      {record ? (
        // A different form starts on its first page, fitted to the width. Records of
        // the same form (one per commitment) share its pages, so page and zoom stay.
        <Pages key={record.page_id} record={record} highlight={highlight} />
      ) : (
        <p className="preview-empty">בחרי שורה בטבלה כדי לראות את הטופס המקורי</p>
      )}
    </section>
  );
}

function Pages({ record, highlight }: { record: ApiRecord; highlight: Highlight | null }) {
  const pages = previewPages(record);
  const [index, setIndex] = useState(0);
  const [zoom, setZoom] = useState<Zoom>("fit");
  const [failed, setFailed] = useState<string | null>(null); // the image URL that did not load
  const frame = useRef<HTMLDivElement>(null);
  const mark = useRef<HTMLDivElement>(null);

  // Another field picked: turn to the page it was read on. Done while rendering, not
  // in an effect, so the old page never flashes; the page buttons still work after.
  const key = highlight?.key ?? null;
  const [shownKey, setShownKey] = useState<string | null>(null);
  if (key !== shownKey) {
    setShownKey(key);
    const turnTo = highlight ? highlightPageIndex(pages, highlight) : null;
    if (turnTo !== null) setIndex(turnTo);
  }

  // A refreshed record of the same form can have fewer pages than the one turned to.
  const at = Math.min(index, pages.length - 1);
  const page = pages[at];
  const boxes = highlight?.boxes.filter((box) => box.page_number === page.pageNumber) ?? [];
  const drawn = page.imageUrl !== null && failed !== page.imageUrl && boxes.length > 0;

  // Scroll the frame, never the window, so the first box is in view. Again once the
  // image loads: before that it has no height, and the box no place.
  function scrollToMark() {
    const outer = frame.current;
    const inner = mark.current;
    if (!outer || !inner) return;
    const o = outer.getBoundingClientRect();
    const i = inner.getBoundingClientRect();
    if (i.top < o.top || i.bottom > o.bottom) outer.scrollTop += i.top - o.top - o.height / 3;
    if (i.left < o.left || i.right > o.right) outer.scrollLeft += i.left - o.left - o.width / 3;
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- a new field, page or zoom only
  useEffect(scrollToMark, [key, at, zoom]);

  return (
    <>
      <p className="preview-source">
        <bdi>{record.source_file}</bdi>, עמוד {page.pageNumber}
        {pages.length > 1 && ` (${at + 1} מתוך ${pages.length} בטופס)`}
      </p>
      {/* Always there, a line high, so a note coming or going never moves what is below. */}
      <p className="preview-highlight">
        {highlight && <HighlightNote highlight={highlight} pages={pages} page={page} drawn={drawn} />}
      </p>

      <div className="preview-toolbar" role="group" aria-label="תצוגת העמוד">
        {pages.length > 1 && (
          <div className="preview-pages">
            {pages.map((p, i) => (
              <button
                key={p.pageNumber}
                type="button"
                className="preview-button"
                aria-pressed={i === at}
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

      <div
        ref={frame}
        className="preview-frame"
        role="region"
        tabIndex={0}
        aria-label="תמונת העמוד. אפשר לגלול עם החיצים"
      >
        {page.imageUrl === null ? (
          <p className="preview-message">התמונה של העמוד הזה לא זמינה. העמוד שייך לטופס הזה</p>
        ) : failed === page.imageUrl ? (
          <p className="preview-message" role="alert">לא ניתן להציג את תמונת העמוד</p>
        ) : (
          // The boxes sit on the image's own box, so they follow it through every zoom.
          <div className="preview-canvas" style={{ inlineSize: zoom === "fit" ? "100%" : `${zoom}%` }}>
            <img
              key={page.imageUrl}
              className="preview-image"
              src={page.imageUrl}
              alt={`עמוד ${page.pageNumber} של הטופס`}
              onLoad={scrollToMark}
              onError={() => setFailed(page.imageUrl)}
            />
            {boxes.map((box, i) => (
              <div
                key={`${box.top}-${box.left}-${i}`}
                ref={i === 0 ? mark : undefined}
                className="preview-box"
                style={boxStyle(box)}
                aria-hidden="true"
                data-testid="preview-box"
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

interface NoteProps {
  highlight: Highlight;
  pages: PreviewPage[];
  page: PreviewPage; // the one shown
  drawn: boolean; // a box is drawn on it
}

// The box in words, so it is never told by color (or by sight) alone. No aria-live:
// it would speak on every pointer move. With the keyboard, the field's own button
// already says which field it is.
function HighlightNote({ highlight, pages, page, drawn }: NoteProps) {
  const label = <bdi>{highlight.label}</bdi>;
  if (drawn) return <>מסומן בתמונה: {label}</>;
  // Sent elsewhere only to a page the reviewer can turn to and see the box on.
  const turnTo = highlightPageIndex(pages, highlight);
  const elsewhere = turnTo === null ? null : pages[turnTo];
  if (elsewhere && elsewhere !== page && elsewhere.imageUrl !== null) {
    return (
      <>
        {label} נקרא בעמוד {elsewhere.pageNumber}
      </>
    );
  }
  return <>אין סימון בתמונה ל{label}</>;
}

export default DocumentPreview;
