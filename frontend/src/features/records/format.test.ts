// Dates and statuses as the records screens show them.
// Owner: B

import { describe, expect, test } from "vitest";
import { formatDate, formatDateTime, statusView } from "./format";

describe("formatDate", () => {
  test("shows DD/MM/YYYY", () => {
    expect(formatDate("2026-10-09")).toBe("09/10/2026");
  });

  test("an empty date is a dash, and anything else is shown as it is", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("25.8")).toBe("25.8");
  });
});

describe("formatDateTime", () => {
  test("in Israel time", () => {
    expect(formatDateTime("2026-10-19T11:05:00Z")).toBe("19/10/2026 14:05");
  });
});

describe("statusView", () => {
  test("every status has its own text and icon", () => {
    const views = [
      statusView({ status: "approved", needs_review: false }),
      statusView({ status: "pending", needs_review: true }),
      statusView({ status: "pending", needs_review: false }),
    ];

    expect(views.map((v) => v.text)).toEqual(["אושר", "דורש בדיקה", "ממתין לאישור"]);
    expect(new Set(views.map((v) => v.icon)).size).toBe(3);
  });
});
