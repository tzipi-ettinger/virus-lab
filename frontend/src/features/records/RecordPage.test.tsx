// @vitest-environment jsdom
// The record page: raw next to value, evidence, confidence and issues (PLAN-DEV-B 3.1).
// Owner: B

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { components } from "../../api/schema";
import { RecordPage } from "./RecordPage";

type ApiRecord = components["schemas"]["Record"];
type FormField = components["schemas"]["FormField"];

function field(value: string | null, over: Partial<FormField> = {}): FormField {
  return {
    raw: value,
    value,
    model_status: value ? "found" : "not_found",
    evidence: value ? `ליד הכיתוב: ${value}` : null,
    issues: [],
    needs_review: false,
    corrected: false,
    confirmed: false,
    ...over,
  };
}

function record(over: Partial<ApiRecord> = {}): ApiRecord {
  return {
    record_id: "r1",
    page_id: "p1",
    source_file: "part1.pdf",
    page_number: 4,
    continuation_pages: [],
    continuation_page_ids: [],
    commitment_index: 0,
    status: "pending",
    version: 2,
    form_type: "hmo_form",
    fields: {
      first_name: field("דנה"),
      last_name: field("לוי"),
      national_id: field("011223344", {
        raw: "11223344",
        corrected: true,
        issues: [{ code: "ID_PADDED", severity: "info", message: "הושלם 0 מוביל" }],
      }),
      received_date: field("2026-10-09", { raw: "9/10/26" }),
      sender: field("מכבי"),
      commitment_number: field(null, {
        needs_review: true,
        issues: [{ code: "REQUIRED_MISSING", severity: "warning", message: "לא נמצא בטופס — יש לבדוק" }],
      }),
    },
    central_numbers: [field("948062")],
    issues: [],
    needs_review: true,
    created_at: "2026-10-19T09:00:00Z",
    updated_at: "2026-10-19T09:00:00Z",
    approved_at: null,
    ...over,
  };
}

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": status < 400 ? "application/json" : "application/problem+json" },
  });

/** The record for GET /records/r1, the senders list, and `others` by method. */
function serve(status: number, body: unknown, others: Record<string, () => Response> = {}) {
  fetchMock.mockImplementation(async (url, init) => {
    if (String(url).endsWith("/senders")) return json(200, ["מכבי", "כללית"]);
    const other = others[init?.method ?? "GET"];
    return other ? other() : json(status, body);
  });
}

const call = (method: string) => fetchMock.mock.calls.find(([, init]) => init?.method === method);

function renderPage(back?: string) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/records/r1", state: back ? { back } : null }]}>
      <Routes>
        <Route path="/records/:recordId" element={<RecordPage />} />
        <Route path="/records" element={<p>מסך הרשומות</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const rowOf = (title: string) => within(screen.getByRole("rowheader", { name: title }).closest("tr")!);

describe("RecordPage", () => {
  test("shows what the model read next to the value now, with evidence and confidence", async () => {
    serve(200, record());
    renderPage();

    await screen.findByRole("heading", { name: "דנה לוי" });
    const id = rowOf("ת״ז");
    expect(id.getByText("011223344")).toBeTruthy();
    expect(id.getByText("11223344")).toBeTruthy();
    expect(id.getByText("תוקן")).toBeTruthy();
    expect(id.getByText("הושלם 0 מוביל")).toBeTruthy();
    expect(rowOf("תאריך קבלה").getByText("9/10/26")).toBeTruthy();
    expect(rowOf("גורם שולח").getByText("ליד הכיתוב: מכבי")).toBeTruthy();
    expect(rowOf("מספר מרכזי 1").getAllByText("948062")).toHaveLength(2); // value and raw
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/records/r1")).toBe(true);
  });

  test("the evidence, cut short on one line, is whole in the tooltip and keeps its own direction", async () => {
    serve(200, record({ fields: { ...record().fields, sender: field("מכבי", { evidence: "top header: מכבי" }) } }));
    renderPage();

    await screen.findByRole("heading", { name: "דנה לוי" });
    const evidence = rowOf("גורם שולח").getByText("top header: מכבי");
    expect(evidence.getAttribute("dir")).toBe("auto");
    expect(evidence.closest("[title]")?.getAttribute("title")).toBe("top header: מכבי");
  });

  test("a flagged field says what's wrong", async () => {
    serve(200, record());
    renderPage();

    await screen.findByRole("heading", { name: "דנה לוי" });
    const commitment = rowOf("מספר התחייבות");
    expect(commitment.getByText("לא נמצא")).toBeTruthy();
    expect(commitment.getByText("לא נמצא בטופס — יש לבדוק")).toBeTruthy();
    expect(screen.getByText(/דורש בדיקה/)).toBeTruthy();
  });

  test("an approved record says when it was approved", async () => {
    serve(200, record({ status: "approved", approved_at: "2026-10-19T11:05:00Z" }));
    renderPage();

    expect(await screen.findByText(/אושר ב־19\/10\/2026 14:05/)).toBeTruthy();
  });

  test("back to the records keeps the filters", async () => {
    serve(200, record());
    renderPage("/records?status=pending&q=0112");

    const back = await screen.findByRole("link", { name: /חזרה לרשומות/ });
    expect(back.getAttribute("href")).toBe("/records?status=pending&q=0112");
  });

  test("a flagged field is confirmed here too, and the answer replaces the record", async () => {
    const confirmed = record({
      version: 3,
      needs_review: false,
      fields: { ...record().fields, commitment_number: field(null, { confirmed: true }) },
    });
    serve(200, record(), { PATCH: () => json(200, { record: confirmed, siblings: [] }) });
    renderPage();
    await screen.findByRole("heading", { name: "דנה לוי" });

    await userEvent.setup().click(screen.getByRole("button", { name: "אישור ערך: מספר התחייבות" }));

    expect(JSON.parse(String(call("PATCH")?.[1]?.body))).toEqual({
      version: 2,
      fields: { commitment_number: { confirmed: true } },
    });
    expect(await rowOf("מספר התחייבות").findByText("אושר ידנית")).toBeTruthy();
  });

  test("a central number is edited alone, the others kept by position", async () => {
    serve(200, record({ central_numbers: [field("948062"), field("12345")] }), {
      PATCH: () => json(200, { record: record(), siblings: [] }),
    });
    renderPage();
    await screen.findByRole("heading", { name: "דנה לוי" });
    const user = userEvent.setup();

    await user.click(rowOf("מספר מרכזי 2").getByRole("button", { name: /^מספר מרכזי 2:/ }));
    await user.keyboard("6{Enter}");

    expect(JSON.parse(String(call("PATCH")?.[1]?.body))).toEqual({
      version: 2,
      central_numbers: [{ idx: 0 }, { idx: 1, value: "123456" }],
    });
  });

  test("a flagged record can't be approved here either", async () => {
    serve(200, record());
    renderPage();
    await screen.findByRole("heading", { name: "דנה לוי" });

    expect((screen.getByRole("button", { name: "אישור" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("לטפל קודם ב: מספר התחייבות")).toBeTruthy();
  });

  test("a ready record is approved, and then it's read-only", async () => {
    const ready = record({
      fields: { ...record().fields, commitment_number: field("50364186") },
      needs_review: false,
    });
    serve(200, ready, {
      POST: () => json(200, { ...ready, status: "approved", approved_at: "2026-10-19T11:05:00Z" }),
    });
    renderPage();
    await screen.findByRole("heading", { name: "דנה לוי" });

    await userEvent.setup().click(screen.getByRole("button", { name: "אישור" }));

    expect(call("POST")?.[0]).toBe("/api/v1/records/r1/approve");
    expect(await screen.findByText(/אושר ב־19\/10\/2026/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /לעריכה/ })).toBeNull();
  });

  test("deleting goes back to the records", async () => {
    serve(200, record(), { DELETE: () => new Response(null, { status: 204 }) });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderPage("/records");
    await screen.findByRole("heading", { name: "דנה לוי" });

    await userEvent.setup().click(screen.getByRole("button", { name: "מחיקה" }));

    expect(await screen.findByText("מסך הרשומות")).toBeTruthy();
  });

  test("a record that isn't there says so", async () => {
    serve(404, { type: "record_not_found", title: "x", status: 404 });
    renderPage();

    expect(await screen.findByText(/הרשומה לא נמצאה/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /חזרה לרשומות/ }).getAttribute("href")).toBe("/records");
  });
});
