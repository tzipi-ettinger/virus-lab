// @vitest-environment jsdom
// The review list: a short row per record, the selection, and "approve all ready"
// (PLAN-DEV-B 3.1, D20). Editing is in RecordPanel (ReviewPage.test.tsx).
// Owner: B

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { ApiRecord } from "./recordMutations";
import { ReviewTable } from "./ReviewTable";
import { replaceRecords } from "./reviewRows";
import { field, flagged, record } from "./testRecords";

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function Table({ initial }: { initial: ApiRecord[] }) {
  const [records, setRecords] = useState(initial);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  return (
    <ReviewTable
      records={records}
      selectedId={selectedId}
      onSelect={setSelectedId}
      onRecords={(changed) => setRecords((current) => replaceRecords(current, changed))}
    />
  );
}

const reply = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

const blocked = (over: Partial<ApiRecord> = {}) =>
  record({
    needs_review: true,
    fields: { ...record().fields, national_id: field("1122", flagged("1122")) },
    central_numbers: [field("12", flagged("12"))],
    ...over,
  });

describe("ReviewTable", () => {
  test("a row shows the source, the name, the ID and what is left to do", () => {
    render(<Table initial={[record(), blocked({ record_id: "r2" }), record({ record_id: "r3", status: "approved" })]} />);

    const [, ready, toFix, approved] = screen.getAllByRole("row");
    expect(within(ready).getByText("part1.pdf")).toBeTruthy();
    expect(within(ready).getByText("עמוד 1")).toBeTruthy();
    expect(within(ready).getByText("דנה לוי")).toBeTruthy();
    expect(within(ready).getByText("011223344")).toBeTruthy();
    expect(within(ready).getByText("מוכן לאישור")).toBeTruthy();
    const badge = within(toFix).getByText("⚠ 2 לתיקון");
    expect(badge.getAttribute("title")).toBe("לטפל קודם ב: ת״ז, מספר מרכזי 1");
    expect(within(approved).getByText("✓ אושר")).toBeTruthy();
    expect(screen.getByText("3 רשומות · 1 לתיקון")).toBeTruthy();
  });

  test("the list has no editors: fields are edited in the panel", () => {
    render(<Table initial={[blocked()]} />);

    expect(screen.queryByRole("button", { name: /לעריכה/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /אישור ערך/ })).toBeNull();
  });

  test("a click selects the row, and the arrows move the selection", async () => {
    render(<Table initial={[record(), record({ record_id: "r2", source_file: "part2.pdf" })]} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /part1\.pdf/ }));
    const [, row1, row2] = screen.getAllByRole("row");
    expect(row1.getAttribute("aria-selected")).toBe("true");

    await user.keyboard("{ArrowDown}");
    expect(row1.getAttribute("aria-selected")).toBe("false");
    expect(row2.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(within(row2).getByRole("button"));

    await user.keyboard("{ArrowDown}"); // the last row: stays
    expect(row2.getAttribute("aria-selected")).toBe("true");
    await user.keyboard("{ArrowUp}");
    expect(row1.getAttribute("aria-selected")).toBe("true");
  });

  test("approve all ready sends only the ready ones and says what's left", async () => {
    const ready1 = record();
    const ready2 = record({ record_id: "r2", version: 3 });
    const answer = {
      approved: [{ ...ready1, status: "approved", version: 2 }],
      skipped: [{ record_id: "r2", type: "version_conflict" }],
    };
    fetchMock.mockImplementation(async () => reply(answer));
    render(<Table initial={[ready1, ready2, blocked({ record_id: "r3" })]} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "✓ אשרי את כל המוכנות (2)" }));

    const call = fetchMock.mock.calls.find(([url]) => url === "/api/v1/records/approve");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      items: [
        { record_id: "r1", version: 1 },
        { record_id: "r2", version: 3 },
      ],
    });
    expect(screen.getByRole("status").textContent).toBe("אושרו 1 רשומות. 2 נשארו לבדיקה");
    const [, row1, row2] = screen.getAllByRole("row");
    expect(within(row1).getByText("✓ אושר")).toBeTruthy();
    expect(within(row2).getByText("לא אושרה: עודכנה בינתיים בחלון אחר")).toBeTruthy();
  });

  test("nothing ready, nothing to send", () => {
    render(<Table initial={[blocked()]} />);

    expect((screen.getByRole("button", { name: /אשרי את כל המוכנות \(0\)/ }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});
