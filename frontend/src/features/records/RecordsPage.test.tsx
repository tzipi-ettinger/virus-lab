// @vitest-environment jsdom
// The records screen: the list, the counts, paging and the empty state (PLAN-DEV-B 3.1).
// Owner: B

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
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
const SENDERS = ["כללית", "מכבי", "מאוחדת", "לאומית"];

/** The records answer for /records, and the senders list for /senders. */
function serve(records: RecordList) {
  fetchMock.mockImplementation(async (url) =>
    answer(String(url).startsWith("/api/v1/senders") ? SENDERS : records),
  );
}

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

const recordCalls = () =>
  fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.startsWith("/api/v1/records"));
const requested = () => new URL(recordCalls().at(-1) ?? "", "http://x").searchParams;

describe("RecordsPage", () => {
  test("shows each record with its values, date and status", async () => {
    serve(list([summary(), summary({ record_id: "r2", status: "approved" })]));
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
    serve(list([summary()]));
    renderAt("/records?status=approved&q=0112&page=2");

    await screen.findAllByRole("row");
    expect(Object.fromEntries(requested())).toEqual({ q: "0112", status: "approved", limit: "50", offset: "50" });
  });

  test("a count filters by its status and starts at page 1", async () => {
    serve(list([summary()]));
    renderAt("/records?page=3");

    await userEvent.setup().click(await screen.findByRole("button", { name: /דורשות בדיקה/ }));

    expect(screen.getByTestId("where").textContent).toBe("/records?status=pending&needs_review=true");
    expect(requested().get("needs_review")).toBe("true");
    expect(screen.getByRole("button", { name: /דורשות בדיקה/ }).getAttribute("aria-pressed")).toBe("true");
  });

  test("pages through the list", async () => {
    serve(list([summary()], { total: 120 }));
    renderAt("/records");

    expect(await screen.findByText("1–50 מתוך 120")).toBeTruthy();
    await userEvent.setup().click(screen.getByRole("button", { name: "הבא" }));

    expect(screen.getByTestId("where").textContent).toBe("/records?page=2");
    expect(requested().get("offset")).toBe("50");
  });

  test("a row opens its record page", async () => {
    serve(list([summary()]));
    renderAt("/records?status=pending");

    const [, row] = await screen.findAllByRole("row");
    await userEvent.setup().click(within(row).getByText("מכבי"));

    expect(screen.getByTestId("where").textContent).toBe("/records/r1");
  });

  test("nothing under the filters says so, and offers to clear them", async () => {
    serve(list([]));
    renderAt("/records?sender=מכבי");

    expect(await screen.findByText("אין רשומות לפי הסינון הנוכחי.")).toBeTruthy();
    await userEvent.setup().click(screen.getByRole("button", { name: "ניקוי הסינון" }));
    expect(screen.getByTestId("where").textContent).toBe("/records");
  });

  test("export downloads every record under the current filters, not one page", async () => {
    serve(list([summary()], { total: 120 }));
    renderAt("/records?status=approved&page=2");

    const csv = await screen.findByRole("link", { name: "CSV" });
    expect(screen.getByText("ייצוא 120 רשומות:")).toBeTruthy();
    expect(csv.getAttribute("href")).toBe("/api/v1/records/export?status=approved&format=csv");
    expect(csv.hasAttribute("download")).toBe(true);
    expect(screen.getByRole("link", { name: "JSON" }).getAttribute("href")).toBe(
      "/api/v1/records/export?status=approved&format=json",
    );
  });

  test("with nothing to export, there is no link and it says why", async () => {
    serve(list([]));
    renderAt("/records?sender=מכבי");

    expect(await screen.findByText("אין רשומות לייצוא לפי הסינון הנוכחי")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "CSV" })).toBeNull();
  });

  test("a failed load says so and can try again", async () => {
    fetchMock.mockImplementation(async (url) => {
      if (String(url).startsWith("/api/v1/senders")) return answer(SENDERS);
      throw new TypeError("Failed to fetch");
    });
    renderAt("/records");

    expect((await screen.findByRole("alert")).textContent).toContain("אין חיבור לשרת");
    serve(list([summary()]));
    await userEvent.setup().click(screen.getByRole("button", { name: "נסי שוב" }));
    expect(await screen.findByText("דנה לוי")).toBeTruthy();
  });
});

describe("RecordsFilters", () => {
  test("the search waits for the typing to stop, then asks once", async () => {
    serve(list([summary()]));
    renderAt("/records");
    await screen.findByText("דנה לוי");
    const before = recordCalls().length;

    await userEvent.setup().type(screen.getByRole("searchbox"), "0112");

    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/records?q=0112"));
    expect(recordCalls().length).toBe(before + 1);
    expect(requested().get("q")).toBe("0112");
  });

  test("the senders come from the closed list", async () => {
    serve(list([summary()]));
    renderAt("/records");

    const sender = screen.getByLabelText("גורם שולח");
    await within(sender).findByRole("option", { name: "מאוחדת" });
    await userEvent.setup().selectOptions(sender, "מאוחדת");

    expect(screen.getByTestId("where").textContent).toBe("/records?sender=%D7%9E%D7%90%D7%95%D7%97%D7%93%D7%AA");
  });

  test("form type, status and dates all go to the URL", async () => {
    serve(list([summary()]));
    renderAt("/records");
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("סוג טופס"), "lab_report");
    await user.selectOptions(screen.getByLabelText("סטטוס"), "approved");
    await user.type(screen.getByLabelText("מתאריך קבלה"), "2026-10-01");
    await user.type(screen.getByLabelText("עד תאריך קבלה"), "2026-10-19");

    expect(Object.fromEntries(requested())).toMatchObject({
      form_type: "lab_report",
      status: "approved",
      date_from: "2026-10-01",
      date_to: "2026-10-19",
    });
  });

  test("clearing the filters empties the search box too", async () => {
    serve(list([]));
    renderAt("/records?q=0112");

    await userEvent.setup().click(await screen.findByRole("button", { name: "ניקוי הסינון" }));

    expect((screen.getByRole("searchbox") as HTMLInputElement).value).toBe("");
  });
});

describe("sorting", () => {
  test("a header sorts by its column, and a second click turns it around", async () => {
    serve(list([summary()]));
    renderAt("/records?status=pending&page=2");
    const user = userEvent.setup();

    const date = await screen.findByRole("columnheader", { name: /תאריך קבלה/ });
    expect(date.getAttribute("aria-sort")).toBe("none");
    await user.click(within(date).getByRole("button"));

    expect(screen.getByTestId("where").textContent).toBe("/records?status=pending&sort=-received_date");
    expect(requested().get("sort")).toBe("-received_date");
    expect(screen.getByRole("columnheader", { name: /תאריך קבלה/ }).getAttribute("aria-sort")).toBe("descending");

    await user.click(within(screen.getByRole("columnheader", { name: /תאריך קבלה/ })).getByRole("button"));
    expect(requested().get("sort")).toBe("received_date");
  });

  test("the order from the URL is shown on its column", async () => {
    serve(list([summary()]));
    renderAt("/records?sort=-last_name");

    const name = await screen.findByRole("columnheader", { name: /שם/ });
    expect(name.getAttribute("aria-sort")).toBe("descending");
    expect(requested().get("sort")).toBe("-last_name");
  });

  test("central numbers are a list, with nothing to sort by", async () => {
    serve(list([summary()]));
    renderAt("/records");

    const centrals = await screen.findByRole("columnheader", { name: "מספרים מרכזיים" });
    expect(within(centrals).queryByRole("button")).toBeNull();
  });
});
