// @vitest-environment jsdom
// The texts by key (he.json): lookup and placeholders, and an element inside a
// sentence. The guards over the sources are in sources.test.ts.
// Owner: B

import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { t, type TextKey } from "./index";
import { tRich } from "./rich";

afterEach(cleanup);

describe("t", () => {
  test("the text under a key, with its placeholders filled", () => {
    expect(t("records.title")).toBe("רשומות");
    expect(t("records.pages.range", { first: 1, last: 50, total: 120 })).toBe("1–50 מתוך 120");
  });

  test("a placeholder with no value stays as it is", () => {
    expect(t("stats.total")).toBe("{n} רשומות במערכת");
  });

  test("a key that is not a text throws, so a test fails before a user sees it", () => {
    expect(() => t("records.nope" as TextKey)).toThrow('no text for "records.nope"');
    expect(() => t("records.counts" as TextKey)).toThrow(); // a group, not a text
  });
});

describe("tRich", () => {
  test("puts an element where its placeholder is, and keeps the rest of the sentence", () => {
    const { container } = render(<p>{tRich("record.history.by", { name: <bdi>דנה לוי</bdi> })}</p>);
    expect(container.innerHTML).toBe("<p>על ידי <bdi>דנה לוי</bdi></p>");
  });

  test("plain values work too, and an element can sit inside another rich text", () => {
    const share = <strong>{tRich("stats.status.approvedShare", { pct: <bdi>3%</bdi> })}</strong>;
    const { container } = render(<p>{tRich("stats.status.note", { approved: share })}</p>);
    expect(container.textContent).toBe("3% כבר אושרו. רשומה עוברת לאישור רק כשאין בה שדה מסומן.");
    expect(container.querySelector("strong bdi")?.textContent).toBe("3%");
  });
});
