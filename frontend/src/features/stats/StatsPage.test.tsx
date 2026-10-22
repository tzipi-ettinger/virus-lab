// @vitest-environment jsdom
// The overview screen: the three numbers, the corrections chart, and the empty and
// error states.
// Owner: B

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fieldTitle } from "./fieldTitle";
import { StatsPage } from "./StatsPage";
import type { RecordStats } from "./useStats";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stats(over: Partial<RecordStats> = {}): RecordStats {
  return {
    pending: 128,
    approved: 212,
    needs_review: 41,
    fields_total: 924,
    fields_flagged: 87,
    corrections: 35,
    corrected_records: 20,
    by_field: [
      { field: "commitment_number", corrections: 21 },
      { field: "central_numbers", corrections: 9 },
      { field: "national_id", corrections: 5 },
    ],
    ...over,
  };
}

function answer(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": status === 200 ? "application/json" : "application/problem+json" },
  });
}

function renderPage() {
  render(
    <MemoryRouter>
      <StatsPage />
    </MemoryRouter>,
  );
}

describe("StatsPage", () => {
  test("shows what is left, the flagged share and the most corrected fields", async () => {
    fetchMock.mockResolvedValue(answer(stats()));
    renderPage();

    const pending = await screen.findByRole("region", { name: "ממתינות לאישור" });
    expect(within(pending).getByText("128")).toBeTruthy();
    expect(within(pending).getByText(/41 דורשות בדיקה/)).toBeTruthy();
    expect(within(pending).getByText(/87 מוכנות לאישור/)).toBeTruthy();
    expect(within(pending).getByRole("link").getAttribute("href")).toBe("/records?status=pending");

    const flagged = screen.getByRole("region", { name: "שדות שסומנו לבדיקה" });
    expect(flagged.textContent).toContain("9.4%");
    expect(flagged.textContent).toContain("87 מתוך 924");

    const chart = screen.getByRole("region", { name: "השדות שתוקנו הכי הרבה" });
    const rows = within(chart).getAllByRole("listitem").map((li) => li.textContent);
    expect(rows).toEqual(["מספר התחייבות21", "מספר מרכזי9", "ת״ז5"]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/stats");
  });

  test("says so when nothing was corrected yet", async () => {
    fetchMock.mockResolvedValue(answer(stats({ corrections: 0, corrected_records: 0, by_field: [] })));
    renderPage();

    expect(await screen.findByText("עוד לא תוקן אף שדה")).toBeTruthy();
    expect(screen.getByText(/עוד לא תוקנו שדות/)).toBeTruthy();
  });

  test("with no records, leads to the upload", async () => {
    fetchMock.mockResolvedValue(
      answer(stats({ pending: 0, approved: 0, needs_review: 0, fields_total: 0, fields_flagged: 0 })),
    );
    renderPage();

    const link = await screen.findByRole("link", { name: "להעלאת טפסים" });
    expect(link.getAttribute("href")).toBe("/upload");
    expect(screen.queryByRole("region", { name: "ממתינות לאישור" })).toBeNull();
  });

  test("an error offers to try again", async () => {
    fetchMock
      .mockResolvedValueOnce(answer({ type: "server_error", title: "תקלה בשרת", status: 500 }, 500))
      .mockResolvedValueOnce(answer(stats()));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("תקלה בשרת");
    await userEvent.setup().click(screen.getByRole("button", { name: "נסי שוב" }));
    expect(await screen.findByRole("region", { name: "ממתינות לאישור" })).toBeTruthy();
  });
});

test("field names read as on the review screen", () => {
  expect(fieldTitle("sender")).toBe("גורם שולח");
  expect(fieldTitle("central_numbers")).toBe("מספר מרכזי");
});
