// Dates and statuses as the records screens show them.
// Owner: B

import { describe, expect, test } from "vitest";
import { SENDER_TAGS, formatDate, formatDateTime, senderTag, statusView } from "./format";

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

describe("senderTag", () => {
  const HMOS = ["כללית", "מכבי", "מאוחדת", "לאומית"];

  test("a sender always gets the same tag, one of the defined ones", () => {
    for (const name of [...HMOS, "רבין (בילינסון / השרון)", "x"]) {
      expect(senderTag(name)).toBe(senderTag(name));
      expect(senderTag(name)).toBeGreaterThanOrEqual(1);
      expect(senderTag(name)).toBeLessThanOrEqual(SENDER_TAGS);
    }
  });

  test("the four health funds, the most common senders, each have their own color", () => {
    expect(new Set(HMOS.map(senderTag)).size).toBe(4);
  });
});
