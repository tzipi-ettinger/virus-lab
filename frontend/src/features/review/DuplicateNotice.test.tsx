// @vitest-environment jsdom
// "Already in the history": every earlier copy with when and by whom, and a link.
// Made-up records.
// Owner: B

import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, test } from "vitest";
import { DuplicateNotice } from "./DuplicateNotice";
import { field, record } from "./testRecords";

afterEach(cleanup);

const MESSAGE = "כבר קיים בהיסטוריה — אותו מספר התחייבות ואותם מספרים מרכזיים. יש לבדוק";

function duplicate(duplicate_of: { record_id: string; created_at: string; created_by: string }[] | null) {
  return record({
    fields: {
      ...record().fields,
      commitment_number: field("50364186", {
        needs_review: true,
        issues: [{ code: "DUPLICATE_RECORD", severity: "warning", message: MESSAGE, duplicate_of }],
      }),
    },
  });
}

const EARLIER = [
  { record_id: "old-1", created_at: "2026-10-19T09:00:00Z", created_by: "דנה" },
  { record_id: "old-2", created_at: "2026-10-20T11:30:00Z", created_by: "רות" },
];

describe("DuplicateNotice", () => {
  test("shows nothing for a record that is not a duplicate", () => {
    const { container } = render(<DuplicateNotice record={record()} newTab />);
    expect(container.innerHTML).toBe("");
  });

  test("names every earlier copy, when and by whom, in Israel time", () => {
    render(<DuplicateNotice record={duplicate(EARLIER)} newTab />);

    screen.getByText(`⚠ ${MESSAGE}`);
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toContain("הוכנס ב־19/10/2026 12:00 על ידי דנה");
    expect(items[1]).toContain("הוכנס ב־20/10/2026 14:30 על ידי רות");
  });

  test("on the upload screen each link opens the earlier record in a new tab", () => {
    render(<DuplicateNotice record={duplicate(EARLIER)} newTab />);

    const links = screen.getAllByRole("link", { name: /פתיחת הרשומה/ });
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/records/old-1", "/records/old-2"]);
    expect(links[0].getAttribute("target")).toBe("_blank");
    expect(links[0].getAttribute("rel")).toBe("noopener noreferrer");
  });

  test("on the record page the link stays in the app", () => {
    render(
      <MemoryRouter>
        <DuplicateNotice record={duplicate(EARLIER.slice(0, 1))} />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: "פתיחת הרשומה" });
    expect(link.getAttribute("href")).toBe("/records/old-1");
    expect(link.hasAttribute("target")).toBe(false);
  });

  test("a record flagged before the list existed shows the message only", () => {
    render(<DuplicateNotice record={duplicate(null)} newTab />);

    screen.getByText(`⚠ ${MESSAGE}`);
    expect(screen.queryByRole("list")).toBeNull();
  });
});
