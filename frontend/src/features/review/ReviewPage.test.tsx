// @vitest-environment jsdom
// The review screen end to end: the list picks a record and RecordPanel edits it.
// A correction goes to the server, and its answer, siblings included, replaces the
// records in both (PLAN-DEV-B 3.3). The upload (A) is stubbed: a button that hands
// over the records.
// Owner: B

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { ApiRecord } from "./recordMutations";
import { ReviewPage } from "./ReviewPage";
import { field, flagged, record } from "./testRecords";

const uploaded = vi.hoisted(() => ({ records: [] as unknown[] }));
vi.mock("../upload/UploadPanel", () => ({
  UploadPanel: ({ onResult }: { onResult: (result: { records: unknown[] }) => void }) => (
    <button type="button" onClick={() => onResult({ records: uploaded.records })}>
      העלאה
    </button>
  ),
}));

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => reply([]));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const reply = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

async function upload(records: ApiRecord[]) {
  uploaded.records = records;
  render(<ReviewPage />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "העלאה" }));
  return user;
}

const named = (first: string, last: string, over: Partial<ApiRecord> = {}) =>
  record({ ...over, fields: { ...record().fields, first_name: field(first), last_name: field(last), ...over.fields } });

const toFix = (over: Partial<ApiRecord> = {}) =>
  record({
    needs_review: true,
    ...over,
    fields: { ...record().fields, ...over.fields, national_id: field("1122", flagged("1122")) },
  });

const panel = () => screen.getByRole("complementary");

describe("ReviewPage", () => {
  test("the first record opens in the panel, and a row click opens another", async () => {
    const user = await upload([record(), named("יוסי", "כהן", { record_id: "r2" })]);

    expect(within(panel()).getByRole("heading", { name: "דנה לוי" })).toBeTruthy();
    expect(within(panel()).getByText("טופס קופה · רשומה 1 מתוך 2")).toBeTruthy();

    await user.click(screen.getByText("יוסי כהן"));

    expect(within(panel()).getByRole("heading", { name: "יוסי כהן" })).toBeTruthy();
    expect(screen.getAllByRole("row")[2].getAttribute("aria-current")).toBe("true");
  });

  test("a corrected ID updates the record and the form's other record from the answer", async () => {
    const first = record({ needs_review: true, fields: { ...record().fields, national_id: field(null, flagged("1122")) } });
    const second = record({ record_id: "r2", commitment_index: 1, fields: first.fields, needs_review: true });
    const fixed = { ...first.fields, national_id: field("011223344", { raw: "1122", corrected: true }) };
    const saved = {
      record: { ...first, version: 2, needs_review: false, fields: fixed },
      siblings: [{ ...second, version: 2, needs_review: false, fields: fixed }],
    };
    fetchMock.mockImplementation(async (_url, init) => reply(init?.method === "PATCH" ? saved : []));
    const user = await upload([first, second]);

    await user.click(within(panel()).getByRole("button", { name: /^ת״ז:/ }));
    await user.type(within(panel()).getByRole("textbox"), "{Control>}a{/Control}011223344{Enter}");

    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(String(patch?.[0])).toBe("/api/v1/records/r1");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      version: 1,
      fields: { national_id: { value: "011223344" } },
    });
    expect(within(panel()).getByText("011223344")).toBeTruthy();
    expect(within(panel()).getByText("תוקן")).toBeTruthy();
    const [, row1, row2] = screen.getAllByRole("row").filter((row) => !panel().contains(row));
    expect(within(row1).getByText("011223344")).toBeTruthy();
    expect(within(row1).getByText("מוכן לאישור")).toBeTruthy();
    expect(within(row2).getByText("011223344")).toBeTruthy();
  });

  test("a pending record is deleted after asking, and the next one opens", async () => {
    fetchMock.mockImplementation(async (_url, init) =>
      init?.method === "DELETE" ? new Response(null, { status: 204 }) : reply([]),
    );
    const ask = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = await upload([record(), named("יוסי", "כהן", { record_id: "r2" })]);

    await user.click(within(panel()).getByRole("button", { name: "מחיקה" }));

    expect(ask.mock.calls[0][0]).toContain("למחוק את הרשומה של דנה לוי");
    expect(fetchMock.mock.calls.some(([url, init]) => url === "/api/v1/records/r1" && init?.method === "DELETE")).toBe(
      true,
    );
    expect(screen.queryByText("דנה לוי")).toBeNull();
    expect(within(panel()).getByRole("heading", { name: "יוסי כהן" })).toBeTruthy();
  });

  test("saying no deletes nothing", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = await upload([record()]);

    await user.click(within(panel()).getByRole("button", { name: "מחיקה" }));

    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
    expect(within(panel()).getByRole("heading", { name: "דנה לוי" })).toBeTruthy();
  });

  test("an approved record is read-only in the panel", async () => {
    await upload([record({ status: "approved" })]);

    expect(within(panel()).queryByRole("button", { name: /לעריכה/ })).toBeNull();
    expect(within(panel()).queryByRole("button", { name: "מחיקה" })).toBeNull();
    expect(within(panel()).getByText("✓ אושר")).toBeTruthy();
  });

  test("next to fix skips the ready ones and comes around", async () => {
    const user = await upload([
      toFix(),
      named("יוסי", "כהן", { record_id: "r2" }),
      toFix({ record_id: "r3", fields: named("מרים", "אברהם").fields }),
    ]);

    await user.click(within(panel()).getByRole("button", { name: "הבאה לתיקון ←" }));
    expect(within(panel()).getByRole("heading", { name: "מרים אברהם" })).toBeTruthy();

    await user.click(within(panel()).getByRole("button", { name: "הבאה לתיקון ←" }));
    expect(within(panel()).getByRole("heading", { name: "דנה לוי" })).toBeTruthy();
  });

  test("nothing else to fix, no next button", async () => {
    await upload([toFix(), record({ record_id: "r2" })]);

    expect(within(panel()).queryByRole("button", { name: "הבאה לתיקון ←" })).toBeNull();
  });

  test("on a narrow screen, a picked row brings the panel up and focuses its title", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query === "(max-width: 900px)" }));
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled; // jsdom has none
    try {
      const user = await upload([record(), named("יוסי", "כהן", { record_id: "r2" })]);

      await user.click(screen.getByText("יוסי כהן"));

      const title = within(panel()).getByRole("heading", { name: "יוסי כהן" });
      expect(document.activeElement).toBe(title);
      expect(scrolled).toHaveBeenCalledOnce();

      // The arrows only move the selection: the focus stays in the list.
      within(screen.getAllByRole("row")[1]).getByRole("button").focus();
      await user.keyboard("{ArrowDown}");
      expect(within(panel()).getByRole("heading", { name: "יוסי כהן" })).toBeTruthy();
      expect(panel().contains(document.activeElement)).toBe(false);
      expect(scrolled).toHaveBeenCalledOnce();
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView;
    }
  });

  test("on a wide screen, the focus stays on the picked row", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    const user = await upload([record(), named("יוסי", "כהן", { record_id: "r2" })]);

    await user.click(screen.getByText("יוסי כהן"));

    expect(panel().contains(document.activeElement)).toBe(false);
  });

  test("the original page starts small and grows on demand", async () => {
    const user = await upload([record()]);
    const toggle = within(panel()).getByRole("button", { name: "הגדלת הטופס" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    await user.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(toggle.textContent).toBe("הקטנת הטופס");
  });

  test("the panel says why a field is flagged, in text", async () => {
    await upload([record({ fields: { ...record().fields, sender: field("x", flagged("x", "גורם שולח לא מוכר")) } })]);

    expect(within(panel()).getByText("גורם שולח לא מוכר")).toBeTruthy();
  });
});
