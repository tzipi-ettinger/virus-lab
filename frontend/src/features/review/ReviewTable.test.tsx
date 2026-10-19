// @vitest-environment jsdom
// The review table end to end: a correction goes to the server, and its answer,
// siblings included, replaces the rows (PLAN-DEV-B 3.3).
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
  return (
    <ReviewTable
      records={records}
      selectedId={null}
      onSelect={() => {}}
      onRecords={(changed) => setRecords((current) => replaceRecords(current, changed))}
    />
  );
}

const reply = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

describe("ReviewTable", () => {
  test("a corrected ID updates its row and the form's other record from the answer", async () => {
    const first = record({ needs_review: true, fields: { ...record().fields, national_id: field(null, flagged("1122")) } });
    const second = record({ record_id: "r2", commitment_index: 1, fields: first.fields, needs_review: true });
    const fixed = { ...first.fields, national_id: field("011223344", { raw: "1122", corrected: true }) };
    const saved = {
      record: { ...first, version: 2, needs_review: false, fields: fixed },
      siblings: [{ ...second, version: 2, needs_review: false, fields: fixed }],
    };
    fetchMock.mockImplementation(async (url) => reply(String(url).endsWith("/senders") ? [] : saved));
    render(<Table initial={[first, second]} />);
    const user = userEvent.setup();

    const [, row1, row2] = screen.getAllByRole("row");
    await user.click(within(row1).getByRole("button", { name: /^ת״ז:/ }));
    await user.type(screen.getByRole("textbox"), "{Control>}a{/Control}011223344{Enter}");

    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      version: 1,
      fields: { national_id: { value: "011223344" } },
    });
    expect(within(row1).getByText("011223344")).toBeTruthy();
    expect(within(row2).getByText("011223344")).toBeTruthy();
    expect(within(row1).getAllByText("תוקן").length).toBeGreaterThan(0);
    expect(within(row1).queryByText("דורש בדיקה")).toBeNull();
  });

  test("an approved row is read-only", () => {
    render(<Table initial={[record({ status: "approved" })]} />);

    expect(screen.queryByRole("button", { name: /לעריכה/ })).toBeNull();
  });
});
