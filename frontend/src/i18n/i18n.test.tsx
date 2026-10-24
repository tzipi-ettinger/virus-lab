// @vitest-environment jsdom
// The texts by key (he.json, en.json): lookup and placeholders, an element inside a
// sentence, and picking the language. The guards over the sources are in
// sources.test.ts.
// Owner: B

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { LanguageSwitch } from "../shared/ui/LanguageSwitch";
import { LANGUAGE_KEY, applyLanguage, chooseLanguage, language, t, type TextKey } from "./index";
import { tRich } from "./rich";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.resetModules();
});

describe("the language", () => {
  test("is Hebrew when nothing was chosen, right to left", () => {
    expect(language).toBe("he");
    const root = document.createElement("html");
    applyLanguage(root);
    expect([root.lang, root.dir]).toEqual(["he", "rtl"]);
    expect(document.title).toBe("המעבדה המרכזית לנגיפים · טפסי התחייבות");
  });

  test("is English once chosen, left to right, and every text comes from en.json", async () => {
    localStorage.setItem(LANGUAGE_KEY, "en");
    vi.resetModules();
    const english = await import("./index");
    expect(english.language).toBe("en");
    expect(english.t("records.title")).toBe("Records");
    expect(english.t("records.pages.range", { first: 1, last: 50, total: 120 })).toBe("1–50 of 120");
    const root = document.createElement("html");
    english.applyLanguage(root);
    expect([root.lang, root.dir]).toEqual(["en", "ltr"]);
    expect(document.title).toBe("Central Virology Laboratory · Commitment forms");
  });

  test("choosing one saves it and loads the page again", () => {
    const reload = vi.fn();
    chooseLanguage("en", reload);
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe("en");
    expect(reload).toHaveBeenCalledOnce();
  });

  test("anything else saved is Hebrew", async () => {
    localStorage.setItem(LANGUAGE_KEY, "fr");
    vi.resetModules();
    expect((await import("./index")).language).toBe("he");
  });

  test("the switch offers the other language, in that language, and saves it", async () => {
    render(<LanguageSwitch />);
    const button = screen.getByRole("button", { name: "החלפת השפה לאנגלית" });
    expect(button.textContent).toBe("English");
    expect(button.getAttribute("lang")).toBe("en");
    // Loading the page again is not something jsdom does: only the choice is checked here.
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    await userEvent.setup().click(button);
    quiet.mockRestore();
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe("en");
  });
});

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
