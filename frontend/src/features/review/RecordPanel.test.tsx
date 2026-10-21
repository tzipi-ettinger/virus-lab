// @vitest-environment jsdom
// RecordPanel boxes the field under the pointer or in focus on the original page
// (field boxes). The pointer only once it rests on a row. Made-up records.
// Owner: B

import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { FieldBox } from "../preview/previewPages";
import { HOVER_DELAY_MS } from "../preview/useFieldFocus";
import { RecordPanel } from "./RecordPanel";
import { field, record } from "./testRecords";

const box = (top: number): FieldBox => ({ page_number: 1, top, left: 200, bottom: top + 30, right: 450 });

const boxed = record({
  record_id: "r1",
  fields: {
    ...record().fields,
    national_id: field("011223344", { box: box(100) }),
    commitment_number: field("50364186", { box: box(500) }),
  },
});
const other = record({ record_id: "r2", fields: boxed.fields });

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  // The panel asks for the sender list; an empty one keeps the fields as text.
  vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { headers: { "Content-Type": "application/json" } })));
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function panel(open = boxed) {
  const props = { records: [boxed, other], onSelect: () => {}, onRecords: () => {}, onRemoved: () => {} };
  const view = render(<RecordPanel record={open} {...props} />);
  return { reopen: (next: typeof open) => view.rerender(<RecordPanel record={next} {...props} />) };
}

const user = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
const row = (title: string) => screen.getAllByRole("row").find((r) => within(r).queryByRole("rowheader", { name: title }))!;
const drawnTop = () => screen.queryByTestId("preview-box")?.style.top ?? null;
const rest = () => act(() => vi.advanceTimersByTime(HOVER_DELAY_MS));

describe("RecordPanel field boxes", () => {
  test("nothing is boxed until a field is pointed at", () => {
    panel();
    expect(drawnTop()).toBeNull();
  });

  test("a field is boxed once the pointer rests on it, and the next field moves the box", async () => {
    panel();
    const pointer = user();

    await pointer.hover(row("ת״ז"));
    await rest();
    expect(drawnTop()).toBe("10%");

    await pointer.hover(row("מספר התחייבות"));
    await rest();
    expect(drawnTop()).toBe("50%");
    expect(screen.getByText(/מסומן בתמונה/).textContent).toBe("מסומן בתמונה: מספר התחייבות");
  });

  test("passing over a row on the way elsewhere boxes nothing", async () => {
    panel();

    const pointer = user(); // one pointer: it has to know it is on the row to leave it
    await pointer.hover(row("ת״ז"));
    await pointer.unhover(row("ת״ז"));
    await rest();

    expect(drawnTop()).toBeNull();
  });

  test("reaching a field with the keyboard boxes it at once", () => {
    panel();

    act(() => screen.getByRole("button", { name: /^ת״ז:/ }).focus());

    expect(drawnTop()).toBe("10%");
  });

  test("the next record opens with nothing boxed", () => {
    const { reopen } = panel();
    act(() => screen.getByRole("button", { name: /^ת״ז:/ }).focus());

    reopen(other);

    expect(drawnTop()).toBeNull();
  });
});
