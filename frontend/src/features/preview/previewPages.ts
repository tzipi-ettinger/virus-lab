// Which pages DocumentPreview shows for a record, and the zoom steps. No React here,
// so it is tested without a browser.
// Owner: A

import type { components } from "../../api/schema";

// Not named Record: that would hide TypeScript's built-in Record<K, V>.
export type ApiRecord = components["schemas"]["Record"];

export interface PreviewPage {
  pageNumber: number;
  // null: the page belongs to the form, but the record doesn't say where its image is.
  imageUrl: string | null;
}

export function pageImageUrl(pageId: string): string {
  // Relative, so the session cookie goes with it (#15).
  return `/api/v1/pages/${encodeURIComponent(pageId)}/image`;
}

// The form's first page, then its continuation pages in order (A1 in #15).
// continuation_page_ids is in the same order as continuation_pages. A page without
// an id (an answer from before the field existed) still shows, without an image.
export function previewPages(record: ApiRecord): PreviewPage[] {
  const ids = record.continuation_page_ids ?? [];
  return [
    { pageNumber: record.page_number, imageUrl: pageImageUrl(record.page_id) },
    ...(record.continuation_pages ?? []).map((pageNumber, i) => ({
      pageNumber,
      imageUrl: ids[i] ? pageImageUrl(ids[i]) : null,
    })),
  ];
}

// "fit" is the panel's width (100%); the steps are percent of that width.
export type Zoom = "fit" | number;
export const ZOOM_STEPS = [150, 200, 300] as const;
export const MAX_ZOOM = ZOOM_STEPS[ZOOM_STEPS.length - 1];

export function zoomIn(zoom: Zoom): Zoom {
  const current = zoom === "fit" ? 100 : zoom;
  return ZOOM_STEPS.find((step) => step > current) ?? MAX_ZOOM;
}

export function zoomOut(zoom: Zoom): Zoom {
  if (zoom === "fit") return "fit";
  return [...ZOOM_STEPS].reverse().find((step) => step < zoom) ?? "fit";
}

// --- Field boxes: where on the page the model read the value under the pointer.

type FormField = components["schemas"]["FormField"];
export type FieldBox = components["schemas"]["FieldBox"];

export interface Highlight {
  // Changes when another field (or record) is picked: the preview turns to its page then.
  key: string;
  label: string; // the field's name, said in text next to the image, not by color alone
  boxes: FieldBox[];
}

// A field, or all items of a list (central numbers), marked together. Items read
// without a box (records from before boxes, or a box the model got wrong) are skipped.
export function fieldHighlight(key: string, label: string, fields: FormField[]): Highlight {
  return { key, label, boxes: fields.flatMap((field) => (field.box ? [field.box] : [])) };
}

// The page to turn to: the first one a box is on. null when no box is on a page we show.
export function highlightPageIndex(pages: PreviewPage[], highlight: Highlight): number | null {
  for (const box of highlight.boxes) {
    const index = pages.findIndex((page) => page.pageNumber === box.page_number);
    if (index !== -1) return index;
  }
  return null;
}

// Edges in thousandths of the image, as CSS percents of the image's own box. Physical
// top / left on purpose: the page image is never mirrored for RTL.
export function boxStyle(box: FieldBox): { top: string; left: string; width: string; height: string } {
  const percent = (n: number) => `${n / 10}%`;
  return {
    top: percent(box.top),
    left: percent(box.left),
    width: percent(box.right - box.left),
    height: percent(box.bottom - box.top),
  };
}
