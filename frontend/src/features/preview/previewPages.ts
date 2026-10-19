// Which pages DocumentPreview shows for a record, and the zoom steps. No React here,
// so it is tested without a browser.
// Owner: A

import type { components } from "../../api/schema";

export type Record = components["schemas"]["Record"];

export interface PreviewPage {
  pageNumber: number;
  // null: the page belongs to the form, but its image can't be asked for yet.
  imageUrl: string | null;
}

export function pageImageUrl(pageId: string): string {
  // Relative, so the session cookie goes with it (#15).
  return `/api/v1/pages/${encodeURIComponent(pageId)}/image`;
}

// The form's first page, then its continuation pages in order (A1 in #15).
// A Record has the continuation page numbers but not their page ids yet, so only
// the first page has an image until continuation_page_ids is in the contract
// (asked in #15); then this is the only place that changes.
export function previewPages(record: Record): PreviewPage[] {
  return [
    { pageNumber: record.page_number, imageUrl: pageImageUrl(record.page_id) },
    ...(record.continuation_pages ?? []).map((pageNumber) => ({ pageNumber, imageUrl: null })),
  ];
}

// "fit" follows the panel's width; the numbers are percent of that width.
export type Zoom = "fit" | number;
export const ZOOM_STEPS = [100, 150, 200, 300] as const;

export function zoomIn(zoom: Zoom): Zoom {
  const current = zoom === "fit" ? 100 : zoom;
  return ZOOM_STEPS.find((step) => step > current) ?? ZOOM_STEPS[ZOOM_STEPS.length - 1];
}

export function zoomOut(zoom: Zoom): Zoom {
  if (zoom === "fit") return "fit";
  const smaller = [...ZOOM_STEPS].reverse().find((step) => step < zoom);
  return smaller === undefined || smaller === 100 ? "fit" : smaller;
}
