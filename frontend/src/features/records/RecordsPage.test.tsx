// @vitest-environment jsdom
// The records screen: the list, the counts, paging and the empty state (PLAN-DEV-B 3.1).
// Owner: B

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { components } from "../../api/schema";
import { RecordsPage } from "./RecordsPage";

type RecordSummary = components["schemas"]["RecordSummary"];
type RecordList = components["schemas"]["RecordList"];

export function summary(over: Partial<RecordSummary> = {}): RecordSummary {
  return {
    record_id: "r1",
    page_id: "p1",
    source_file: "a.pdf",
    page_number: 1,
    commitment_index: 0,
    status: "pending",
    needs_review: false,
    first_name: "דנה",
    last_name: "לוי",
    national_id: "011223344",
    commitment_number: "50364186",
    central_numbers: ["948062", "123456"],
    sender: "מכבי",
    form_type: "hmo_form",
    received_date: "2026-10-09",
    created_at: "2026-10-19T09:00:00Z",
    approved_at: null,
    ...over,
  };
}

export function list(items: RecordSummary[], over: Partial<RecordList> = {}): RecordList {
  return {
    items,
    total: items.length,
    limit: 50,
    offset: 0,
    counts: { pending: 7, approved: 3, needs_review: 2 },
    ...over,
  };
}

const fetchMock = vi.fn<typeof fetch>();
const answer = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function Where() {
  const { pathname, search } = useLocation();
  return <output data-testid="where">{pathname + search}</output>;
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/records" element={<RecordsPage />} />
        <Route path="/records/:id" element={<p>דף רשומה</p>} />
      </Routes>
      <Where />
    </MemoryRouter>,
  );
}

const requested = () => new URL(String(fetchMock.mock.calls.at(-1)?.[0]), "http://x").searchParams;

describe("RecordsPage", () => {
  test("shows each record with its values, date and status", async () => {
    fetchMock.mockResolvedValue(answer(list([summary(), summary({ record_id: "r2", status: "approved" })])));
    renderAt("/records");

    const rows = await screen.findAllByRole("row");
    expect(rows).toHaveLength(3); // the header and two records
    const first = within(rows[1]);
    expect(first.getByText("דנה לוי")).toBeTruthy();
    expect(first.getByText("011223344")).toBeTruthy(); // leading zero kept
    expect(first.getByText("948062, 123456")).toBeTruthy();
    expect(first.getByText("09/10/2026")).toBeTruthy();
    expect(first.getByText(/ממתין לאישור/)).toBeTruthy();
    expect(within(rows[2]).getByText(/אושר/)).toBeTruthy();
  });

  test("asks the API with the filters in the URL", async () => {
    fetchMock.mockResolvedValue(answer(list([summary()])));
    renderAt("/records?status=approved&q=0112&page=2");

    await screen.findAllByRole("row");
    expect(Object.fromEntries(requested())).toEqual({ q: "0112", status: "approved", limit: "50", offset: "50" });
  });

  test("a count filters by its status and starts at page 1", async () => {
    fetchMock.mockResolvedValue(answer(list([summary()])));
    renderAt("/records?page=3");

    await userEvent.setup().click(await screen.findByRole("button", { name: /דורשות בדיקה/ }));

    expect(screen.getByTestId("where").textContent).toBe("/records?status=pending&needs_review=true");
    expect(requested().get("needs_review")).toBe("true");
    expect(screen.getByRole("button", { name: /דורשות בדיקה/ }).getAttribute("aria-pressed")).toBe("true");
  });

  test("pages through the list", async () => {
    fetchMock.mockResolvedValue(answer(list([summary()], { total: 120 })));
    renderAt("/records");

    expect(await screen.findByText("1–50 מתוך 120")).toBeTruthy();
    await userEvent.setup().click(screen.getByRole("button", { name: "הבא" }));

    expect(screen.getByTestId("where").textContent).toBe("/records?page=2");
    expect(requested().get("offset")).toBe("50");
  });

  test("a row opens its record page", async () => {
    fetchMock.mockResolvedValue(answer(list([summary()])));
    renderAt("/records?status=pending");

    await userEvent.setup().click(await screen.findByText("מכבי"));

    expect(screen.getByTestId("where").textContent).toBe("/records/r1");
  });

  test("nothing under the filters says so, and offers to clear them", async () => {
    fetchMock.mockResolvedValue(answer(list([])));
    renderAt("/records?sender=מכבי");

    expect(await screen.findByText("אין רשומות לפי הסינון הנוכחי.")).toBeTruthy();
    await userEvent.setup().click(screen.getByRole("button", { name: "ניקוי הסינון" }));
    expect(screen.getByTestId("where").textContent).toBe("/records");
  });

  test("a failed load says so and can try again", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    renderAt("/records");

    expect((await screen.findByRole("alert")).textContent).toContain("אין חיבור לשרת");
    fetchMock.mockResolvedValue(answer(list([summary()])));
    await userEvent.setup().click(screen.getByRole("button", { name: "נסי שוב" }));
    expect(await screen.findByText("דנה לוי")).toBeTruthy();
  });
});
