// Which pages DocumentPreview shows, and the zoom steps.
// Owner: A

import { describe, expect, test } from "vitest";
import {
  MAX_ZOOM,
  boxStyle,
  fieldHighlight,
  highlightPageIndex,
  pageImageUrl,
  previewPages,
  zoomIn,
  zoomOut,
  type ApiRecord,
  type FieldBox,
} from "./previewPages";

function record(over: Partial<ApiRecord> = {}): ApiRecord {
  return { page_id: "p_1", page_number: 3, continuation_pages: [], ...over } as ApiRecord;
}

describe("previewPages", () => {
  test("a one-page form shows its page image from the relative URL", () => {
    expect(previewPages(record())).toEqual([{ pageNumber: 3, imageUrl: "/api/v1/pages/p_1/image" }]);
  });

  test("continuation pages follow the first page, each with its own image", () => {
    const form = record({ continuation_pages: [4, 5], continuation_page_ids: ["p_4", "p_5"] });
    expect(previewPages(form)).toEqual([
      { pageNumber: 3, imageUrl: "/api/v1/pages/p_1/image" },
      { pageNumber: 4, imageUrl: "/api/v1/pages/p_4/image" },
      { pageNumber: 5, imageUrl: "/api/v1/pages/p_5/image" },
    ]);
  });

  test("a continuation page without an id still shows, without an image", () => {
    // An answer from before continuation_page_ids existed.
    expect(previewPages(record({ continuation_pages: [4] }))).toEqual([
      { pageNumber: 3, imageUrl: "/api/v1/pages/p_1/image" },
      { pageNumber: 4, imageUrl: null },
    ]);
  });

  test("a record without continuation_pages (an older answer) is one page", () => {
    expect(previewPages(record({ continuation_pages: undefined }))).toHaveLength(1);
  });

  test("the page id is escaped in the URL", () => {
    expect(pageImageUrl("p/1 #2")).toBe("/api/v1/pages/p%2F1%20%232/image");
  });
});

describe("zoom", () => {
  test("zooming in goes up the steps and stops at the last", () => {
    expect(zoomIn("fit")).toBe(150);
    expect(zoomIn(150)).toBe(200);
    expect(zoomIn(MAX_ZOOM)).toBe(MAX_ZOOM);
  });

  test("zooming out comes back to fit, never below it", () => {
    expect(zoomOut(300)).toBe(200);
    expect(zoomOut(150)).toBe("fit");
    expect(zoomOut("fit")).toBe("fit");
  });
});

describe("field boxes", () => {
  const box = (page_number: number, top = 100): FieldBox => ({ page_number, top, left: 200, bottom: top + 50, right: 450 });
  const field = (b: FieldBox | null) => ({ box: b }) as Parameters<typeof fieldHighlight>[2][number];

  test("a highlight keeps only the items that have a box", () => {
    const highlight = fieldHighlight("r1:central_numbers", "מספרים מרכזיים", [field(box(3)), field(null), field(box(3, 300))]);
    expect(highlight.boxes.map((b) => b.top)).toEqual([100, 300]);
  });

  test("the preview turns to the page the value was read on", () => {
    const pages = previewPages(record({ continuation_pages: [4], continuation_page_ids: ["p_4"] }));
    expect(highlightPageIndex(pages, fieldHighlight("k", "תאריך", [field(box(4))]))).toBe(1);
    expect(highlightPageIndex(pages, fieldHighlight("k", "ת״ז", [field(box(3))]))).toBe(0);
  });

  test("no box, or a box on a page the record doesn't have, turns no page", () => {
    const pages = previewPages(record());
    expect(highlightPageIndex(pages, fieldHighlight("k", "ת״ז", [field(null)]))).toBeNull();
    expect(highlightPageIndex(pages, fieldHighlight("k", "ת״ז", [field(box(9))]))).toBeNull();
  });

  test("the box is drawn in percents of the image", () => {
    expect(boxStyle({ page_number: 1, top: 100, left: 205, bottom: 150, right: 450 })).toEqual({
      top: "10%",
      left: "20.5%",
      width: "24.5%",
      height: "5%",
    });
  });
});
