// @vitest-environment jsdom
// The record page: raw next to value, evidence, confidence and issues (PLAN-DEV-B 3.1).
// Owner: B

import { cleanup, render, screen, within } from "@testing-library/react";
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

function serve(status: number, body: unknown) {
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": status < 400 ? "application/json" : "application/problem+json" },
    }),
  );
}

function renderPage(back?: string) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/records/r1", state: back ? { back } : null }]}>
      <Routes>
        <Route path="/records/:recordId" element={<RecordPage />} />
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
    expect(rowOf("תאריך קבלה").getByText("09/10/2026")).toBeTruthy();
    expect(rowOf("גורם שולח").getByText("ליד הכיתוב: מכבי")).toBeTruthy();
    expect(rowOf("מספר מרכזי 1").getAllByText("948062")).toHaveLength(2); // value and raw
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/records/r1");
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

  test("an approved record says who approved it and when", async () => {
    serve(200, record({ status: "approved", approved_by: "esty", approved_at: "2026-10-19T11:05:00Z" }));
    renderPage();

    expect(await screen.findByText(/אושר על ידי esty ב־19\/10\/2026 14:05/)).toBeTruthy();
  });

  test("back to the records keeps the filters", async () => {
    serve(200, record());
    renderPage("/records?status=pending&q=0112");

    const back = await screen.findByRole("link", { name: /חזרה לרשומות/ });
    expect(back.getAttribute("href")).toBe("/records?status=pending&q=0112");
  });

  test("a record that isn't there says so", async () => {
    serve(404, { type: "record_not_found", title: "x", status: 404 });
    renderPage();

    expect(await screen.findByText(/הרשומה לא נמצאה/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /חזרה לרשומות/ }).getAttribute("href")).toBe("/records");
  });
});
