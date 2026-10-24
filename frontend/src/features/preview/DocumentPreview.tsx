// Original page next to the selected row (selection comes in as a prop). With a
// highlight, it turns to the page the value was read on and boxes the value there.
// Owner: A

import { useEffect, useRef, useState, type Dispatch, type HTMLAttributes, type SetStateAction } from "react";
import { t } from "../../i18n";
import { tRich } from "../../i18n/rich";
import { FileName } from "../../shared/FileName";
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
  // What "fit" fits: the width (a short frame that scrolls to the box) or the whole
  // page in a frame with a set height (the record page). Zooming in starts at 100%.
  fit?: Fit;
}

type Fit = "width" | "page";

export function DocumentPreview({ record, highlight = null, pointerArea, fit = "width" }: DocumentPreviewProps) {
  // Kept here, above the page, so the zoom the reviewer picked stays from one record
  // to the next instead of going back to "fit" every time.
  const [zoom, setZoom] = useState<Zoom>("fit");
  return (
    <section className="preview" aria-labelledby="preview-title" {...pointerArea}>
      <h2 id="preview-title" className="preview-title">{t("preview.title")}</h2>
      {record ? (
        // A different form starts on its first page, at the zoom picked before. Records
        // of the same form (one per commitment) share its pages, so the page stays too.
        <Pages key={record.page_id} record={record} highlight={highlight} fit={fit} zoom={zoom} setZoom={setZoom} />
      ) : (
        <p className="preview-empty">{t("preview.empty")}</p>
      )}
    </section>
  );
}

interface PagesProps {
  record: ApiRecord;
  highlight: Highlight | null;
  fit: Fit;
  zoom: Zoom;
  setZoom: Dispatch<SetStateAction<Zoom>>;
}

function Pages({ record, highlight, fit, zoom, setZoom }: PagesProps) {
  const pages = previewPages(record);
  const [index, setIndex] = useState(0);
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
  const wholePage = fit === "page" && zoom === "fit";
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
        {tRich("common.fileAndPage", { file: <FileName name={record.source_file} />, page: page.pageNumber })}
        {pages.length > 1 && t("preview.pageOfForm", { at: at + 1, total: pages.length })}
      </p>
      {/* Always there, a line high, so a note coming or going never moves what is below. */}
      <p className="preview-highlight">
        {highlight && <HighlightNote highlight={highlight} pages={pages} page={page} drawn={drawn} />}
      </p>

      <div className="preview-toolbar" role="group" aria-label={t("preview.toolbar")}>
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
                {t("common.page", { page: p.pageNumber })}
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
            aria-label={t("preview.zoomOut")}
          >
            −
          </button>
          <button
            type="button"
            className="preview-button"
            onClick={() => setZoom("fit")}
            aria-pressed={zoom === "fit"}
          >
            {fit === "page" ? t("preview.wholePage") : t("preview.fitWidth")}
          </button>
          <button
            type="button"
            className="preview-button"
            onClick={() => setZoom((z) => (fit === "page" && z === "fit" ? 100 : zoomIn(z)))}
            disabled={zoom === MAX_ZOOM}
            aria-label={t("preview.zoomIn")}
          >
            +
          </button>
          <span className="preview-zoom-level" aria-live="polite">
            {zoom === "fit" ? (fit === "page" ? "" : t("preview.fullWidth")) : zoom === 100 ? t("preview.fullWidth") : `${zoom}%`}
          </span>
        </div>
      </div>

      <div
        ref={frame}
        className={wholePage ? "preview-frame is-page" : "preview-frame"}
        role="region"
        tabIndex={0}
        aria-label={t("preview.frame")}
      >
        {page.imageUrl === null ? (
          <p className="preview-message">{t("preview.noImage")}</p>
        ) : failed === page.imageUrl ? (
          <p className="preview-message" role="alert">{t("preview.imageFailed")}</p>
        ) : (
          // The boxes sit on the image's own box, so they follow it through every zoom.
          <div
            className={wholePage ? "preview-canvas is-page" : "preview-canvas"}
            style={wholePage ? undefined : { inlineSize: zoom === "fit" ? "100%" : `${zoom}%` }}
          >
            <img
              key={page.imageUrl}
              className="preview-image"
              src={page.imageUrl}
              alt={t("preview.imageAlt", { page: page.pageNumber })}
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
  if (drawn) return tRich("preview.marked", { label });
  // Sent elsewhere only to a page the reviewer can turn to and see the box on.
  const turnTo = highlightPageIndex(pages, highlight);
  const elsewhere = turnTo === null ? null : pages[turnTo];
  if (elsewhere && elsewhere !== page && elsewhere.imageUrl !== null) {
    return tRich("preview.elsewhere", { label, page: elsewhere.pageNumber });
  }
  return tRich("preview.notMarked", { label });
}

export default DocumentPreview;
