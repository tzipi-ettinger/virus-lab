// Which pages DocumentPreview shows for a record, and the zoom steps. No React here,
// so it is tested without a browser.
// Owner: A

import type { components } from "../../api/schema";

// Not named Record: that would hide TypeScript's built-in Record<K, V>.
export type ApiRecord = components["schemas"]["Record"];

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
export function previewPages(record: ApiRecord): PreviewPage[] {
  return [
    { pageNumber: record.page_number, imageUrl: pageImageUrl(record.page_id) },
    ...(record.continuation_pages ?? []).map((pageNumber) => ({ pageNumber, imageUrl: null })),
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
