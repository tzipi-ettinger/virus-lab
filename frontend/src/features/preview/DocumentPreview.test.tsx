// @vitest-environment jsdom
// Field boxes in DocumentPreview: the page the value was read on, a box around it, and
// the same in words. The records are made up (review/testRecords).
// Owner: A

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";
import { field, record } from "../review/testRecords";
import { DocumentPreview } from "./DocumentPreview";
import { fieldHighlight, type FieldBox } from "./previewPages";

const box = (page_number: number): FieldBox => ({ page_number, top: 100, left: 200, bottom: 150, right: 450 });

const twoPages = record({
  page_number: 3,
  continuation_pages: [4],
  continuation_page_ids: ["p4"],
});

afterEach(cleanup);

const shownPage = () => screen.getByRole("img").getAttribute("alt");

describe("DocumentPreview with a highlight", () => {
  test("without one, nothing is boxed", () => {
    render(<DocumentPreview record={twoPages} />);

    expect(screen.queryByTestId("preview-box")).toBeNull();
    expect(shownPage()).toBe("עמוד 3 של הטופס");
  });

  test("the value is boxed on its page, and named in words", () => {
    const highlight = fieldHighlight("r1:national_id", "ת״ז", [field("011223344", { box: box(3) })]);
    render(<DocumentPreview record={twoPages} highlight={highlight} />);

    const drawn = screen.getByTestId("preview-box");
    expect(drawn.style.top).toBe("10%");
    expect(drawn.style.left).toBe("20%");
    expect(screen.getByText(/מסומן בתמונה/).textContent).toBe("מסומן בתמונה: ת״ז");
  });

  test("a value read on a continuation page turns the preview to that page", () => {
    const highlight = fieldHighlight("r1:received_date", "תאריך קבלה", [field("2026-10-09", { box: box(4) })]);
    render(<DocumentPreview record={twoPages} highlight={highlight} />);

    expect(shownPage()).toBe("עמוד 4 של הטופס");
    expect(screen.queryByTestId("preview-box")).not.toBeNull();
  });

  test("turning back to another page by hand still works, and the box stays on its page", async () => {
    const highlight = fieldHighlight("r1:received_date", "תאריך קבלה", [field("2026-10-09", { box: box(4) })]);
    render(<DocumentPreview record={twoPages} highlight={highlight} />);

    await userEvent.click(screen.getByRole("button", { name: "עמוד 3" }));

    expect(shownPage()).toBe("עמוד 3 של הטופס");
    expect(screen.queryByTestId("preview-box")).toBeNull();
    expect(screen.getByText(/נקרא בעמוד 4/).textContent).toBe("תאריך קבלה נקרא בעמוד 4");
  });

  test("a field read without a box says so instead of drawing anything", () => {
    const highlight = fieldHighlight("r1:sender", "גורם שולח", [field("מכבי")]);
    render(<DocumentPreview record={twoPages} highlight={highlight} />);

    expect(screen.queryByTestId("preview-box")).toBeNull();
    expect(screen.getByText(/אין סימון בתמונה/).textContent).toBe("אין סימון בתמונה לגורם שולח");
  });

  test("every central number is boxed together", () => {
    const highlight = fieldHighlight("r1:central_numbers", "מספרים מרכזיים", [
      field("948062", { box: box(3) }),
      field("123456", { box: { ...box(3), top: 300, bottom: 340 } }),
    ]);
    render(<DocumentPreview record={twoPages} highlight={highlight} />);

    expect(screen.getAllByTestId("preview-box")).toHaveLength(2);
  });
});
