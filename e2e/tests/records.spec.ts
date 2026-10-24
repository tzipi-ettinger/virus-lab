// The records screen and the record page, through the real server: the tabs count
// what the server counts, every filter narrows the list and shows as a chip, search,
// sorting, paging and export follow the filters, and a record is fixed, approved and
// deleted from its own page, with its history. Every number is checked against the API.
// Owner: shared

import { readFile } from "node:fs/promises";
import {
  FIELD_TITLES,
  RUN,
  blocked,
  dateKey,
  expect,
  fixFlagged,
  fixable,
  getRecord,
  listRecords,
  requirePassword,
  signIn,
  signedInRequest,
  test,
  uploadViaApi,
  type ApiRecord,
} from "./helpers";
import type { Page } from "@playwright/test";

let uploaded: ApiRecord[] = [];

test.beforeAll(async () => {
  requirePassword();
  const request = await signedInRequest();
  uploaded = await uploadViaApi(request, `e2e-records-${RUN}.pdf`, 8);
  expect(uploaded.length).toBeGreaterThan(2);
  await request.dispose();
});

const rows = (page: Page) => page.locator(".records-table tbody tr");
const query = (page: Page) => new URL(page.url()).searchParams;

/** Does something that reloads the list, and waits until the new list is on screen. */
async function reloads(page: Page, action: () => Promise<unknown>) {
  await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/v1/records?") && r.request().method() === "GET"),
    action(),
  ]);
  await expect(page.locator('section.records[aria-busy="false"]')).toHaveCount(1);
}

/** The list and its paging show `total` records, a page at a time. */
async function expectListOf(page: Page, total: number) {
  if (total === 0) {
    await expect(page.getByText("אין רשומות לפי הסינון הנוכחי.")).toBeVisible();
    return;
  }
  await expect(rows(page)).toHaveCount(Math.min(50, total));
  await expect(page.locator(".records-pages span")).toHaveText(`1–${Math.min(50, total)} מתוך ${total}`);
}

test("the tabs count what the server counts, and each one filters the list", async ({ page }) => {
  await signIn(page);
  await page.goto("/records");
  const { counts, total } = await listRecords(page.request);
  const tabs = page.getByRole("group", { name: "מונים" });
  await expect(tabs.getByRole("button", { name: /הכול/ })).toHaveText(`הכול ${counts.pending + counts.approved}`);
  await expect(tabs.getByRole("button", { name: /ממתינות/ })).toContainText(String(counts.pending));
  await expect(tabs.getByRole("button", { name: /דורשות בדיקה/ })).toContainText(String(counts.needs_review));
  await expect(tabs.getByRole("button", { name: /מאושרות/ })).toContainText(String(counts.approved));
  await expect(tabs.getByRole("button", { name: /הכול/ })).toHaveAttribute("aria-pressed", "true");
  await expectListOf(page, total);

  for (const tab of [
    { name: /ממתינות/, api: "status=pending", status: /^(○ ממתין לאישור|⚠ דורש בדיקה)$/ },
    { name: /דורשות בדיקה/, api: "status=pending&needs_review=true", status: /^⚠ דורש בדיקה$/ },
    { name: /מאושרות/, api: "status=approved", status: /^✓ אושר$/ },
  ]) {
    await reloads(page, () => tabs.getByRole("button", { name: tab.name }).click());
    await expect(tabs.getByRole("button", { name: tab.name })).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => query(page).toString()).toBe(tab.api);
    const expected = await listRecords(page.request, tab.api);
    await expectListOf(page, expected.total);
    for (const status of await rows(page).locator(".records-status").allTextContents()) {
      expect(status.trim()).toMatch(tab.status);
    }
  }

  await tabs.getByRole("button", { name: /הכול/ }).click();
  await expect(page).toHaveURL(/\/records$/);
});

test("each filter shows as a chip: one × takes one off, and 'clear all' keeps the order", async ({ page }) => {
  await signIn(page);
  await page.goto("/records?sort=-last_name");
  const sender = uploaded.map((r) => r.fields.sender.value).find(Boolean)!;
  const chips = page.getByRole("group", { name: "סינון פעיל" });
  await expect(chips).toHaveCount(0);

  await reloads(page, () => page.locator(".records-filter-sender select").selectOption(sender));
  await expect.poll(() => query(page).get("sender")).toBe(sender);
  await expect(chips.getByRole("button", { name: `הסרת הסינון גורם שולח: ${sender}` })).toBeVisible();
  for (const tag of await rows(page).locator(".records-sender").allTextContents()) expect(tag.trim()).toBe(sender);

  await reloads(page, () => page.getByRole("group", { name: "מונים" }).getByRole("button", { name: /דורשות בדיקה/ }).click());
  await reloads(page, () => page.getByLabel("מתאריך קבלה", { exact: true }).fill("2020-01-01"));
  await reloads(page, () => page.locator(".records-filter-form select").selectOption("hospital_form"));
  await expect.poll(() => query(page).get("form_type")).toBe("hospital_form");
  await expect(chips.getByRole("button")).toHaveText([
    /^דורשות בדיקה/,
    new RegExp(`^גורם שולח: ${sender}`),
    /^סוג טופס: טופס בית חולים/,
    /^תאריך קבלה: מ־01\/01\/2020/,
    "ניקוי הכול",
  ]);
  const narrowed = await listRecords(page.request, query(page).toString().replace(/(^|&)sort=[^&]*/, ""));
  await expectListOf(page, narrowed.total);

  // One chip off: only its filter goes.
  await chips.getByRole("button", { name: `הסרת הסינון גורם שולח: ${sender}` }).click();
  await expect.poll(() => query(page).has("sender")).toBe(false);
  expect(query(page).get("form_type")).toBe("hospital_form");
  expect(query(page).get("needs_review")).toBe("true");
  await expect(page.locator(".records-filter-sender select")).toHaveValue("");

  // All of them off; the order stays.
  await chips.getByRole("button", { name: "ניקוי הכול" }).click();
  await expect.poll(() => query(page).toString()).toBe("sort=-last_name");
  await expect(chips).toHaveCount(0);
  await expect(page.getByLabel("מתאריך קבלה", { exact: true })).toHaveValue("");
});

test("search finds a record, and a search with no match says so and offers to clear", async ({ page }) => {
  await signIn(page);
  await page.goto("/records");
  const commitment = uploaded.map((r) => r.fields.commitment_number.value).find(Boolean)!;
  await reloads(page, () => page.getByRole("searchbox").fill(commitment));
  await expect.poll(() => query(page).get("q")).toBe(commitment);
  const found = await listRecords(page.request, `q=${encodeURIComponent(commitment)}`);
  await expectListOf(page, found.total);
  for (const row of await rows(page).allTextContents()) expect(row).toContain(commitment);

  await reloads(page, () => page.getByRole("searchbox").fill(`zz-nothing-${RUN}`));
  await expect(page.getByText("אין רשומות לפי הסינון הנוכחי.")).toBeVisible();
  await expect(page.getByText("אין רשומות לייצוא לפי הסינון הנוכחי")).toBeVisible();
  await page.getByRole("button", { name: "ניקוי הסינון" }).click();
  await expect(page).toHaveURL(/\/records$/);
  await expect(page.getByRole("searchbox")).toHaveValue("");
});

test("a column header sorts the list, and a second click turns it around", async ({ page }) => {
  await signIn(page);
  await page.goto("/records");
  const header = page.getByRole("columnheader", { name: /תאריך קבלה/ });
  const dates = async () =>
    (await rows(page).locator('td[data-label="תאריך קבלה"]').allTextContents())
      .map(dateKey)
      .filter((d): d is number => d !== null);

  await reloads(page, () => header.getByRole("button").click());
  await expect(header).toHaveAttribute("aria-sort", "descending");
  expect(query(page).get("sort")).toBe("-received_date");
  const down = await dates();
  expect(down).toEqual([...down].sort((a, b) => b - a));

  await reloads(page, () => header.getByRole("button").click());
  await expect(header).toHaveAttribute("aria-sort", "ascending");
  expect(query(page).get("sort")).toBe("received_date");
  const up = await dates();
  expect(up).toEqual([...up].sort((a, b) => a - b));

  // Sorting by name starts from A.
  await page.getByRole("columnheader", { name: /^שם/ }).getByRole("button").click();
  await expect(page.getByRole("columnheader", { name: /^שם/ })).toHaveAttribute("aria-sort", "ascending");
  expect(query(page).get("sort")).toBe("last_name");
});

test("paging moves 50 at a time, and stops at the ends", async ({ page }) => {
  await signIn(page);
  await page.goto("/records");
  const { total } = await listRecords(page.request);
  const previous = page.getByRole("button", { name: "הקודם" });
  const next = page.getByRole("button", { name: "הבא" });
  await expect(previous).toBeDisabled();
  if (total <= 50) {
    await expect(next).toBeDisabled();
    return;
  }
  await reloads(page, () => next.click());
  expect(query(page).get("page")).toBe("2");
  await expect(page.locator(".records-pages span")).toHaveText(`51–${Math.min(100, total)} מתוך ${total}`);
  await previous.click();
  expect(query(page).has("page")).toBe(false);
});

test("export downloads every record under the filters, as CSV and as JSON", async ({ page }) => {
  await signIn(page);
  await page.goto("/records?status=pending");
  const { total } = await listRecords(page.request, "status=pending");
  await expect(page.getByText(`ייצוא ${total} רשומות:`)).toBeVisible();

  const download = async (name: string) => {
    const [file] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name }).click()]);
    return readFile(await file.path(), "utf-8");
  };
  const json = JSON.parse(await download("JSON")) as ApiRecord[];
  expect(json).toHaveLength(total);
  expect(json.every((r) => r.status === "pending")).toBe(true);
  const csv = (await download("CSV")).replace(/^﻿/, "").trim().split(/\r?\n/);
  expect(csv.length - 1, "CSV rows after the header").toBe(total);
});

test("a row opens its record, and the way back keeps the filters", async ({ page }) => {
  await signIn(page);
  await page.goto("/records?status=pending&sort=-received_date");
  const list = page.url();
  await rows(page).first().getByRole("link").click();
  await expect(page).toHaveURL(/\/records\/[^/?]+$/);
  await page.getByRole("link", { name: "→ חזרה לרשומות" }).click();
  expect(page.url()).toBe(list);
});

test("on its own page a record is fixed and approved, then read-only, with its whole history", async ({ page }) => {
  const record = uploaded.find(fixable);
  test.skip(!record, "no uploaded record the spec knows how to fix");
  await signIn(page);
  await page.goto(`/records/${record!.record_id}`);
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const fields = page.locator(".record-fields");

  await expect(page.locator(".records-status")).toHaveText(/דורש בדיקה/);
  await expect(page.locator(".record-meta")).toContainText(`${record!.source_file}, עמוד ${record!.page_number}`);
  await expect(page.locator(".record-meta")).toContainText("נקלט");
  const flagged = Object.values(record!.fields).filter((f) => f.needs_review).length;
  await expect(fields.locator("tbody tr.is-flagged")).toHaveCount(flagged);
  await expect(page.locator(".preview-image")).toBeVisible();

  await fixFlagged(fields, record!);
  await expect(fields.locator("tbody tr.is-flagged")).toHaveCount(0);
  expect(blocked(await getRecord(page.request, record!.record_id))).toBe(false);

  await page.locator(".record-actions").getByRole("button", { name: "אישור", exact: true }).click();
  await expect(page.locator(".records-status")).toHaveText(new RegExp(`אושר על ידי ${me.display_name} ב־`));
  expect((await getRecord(page.request, record!.record_id)).status).toBe("approved");
  // Approved: nothing to change any more.
  await expect(page.locator(".record-actions").getByRole("button", { name: "מחיקה" })).toHaveCount(0);
  await expect(fields.locator(".review-cell-value")).toHaveCount(0);

  const historyButton = page.getByRole("button", { name: /^היסטוריה \(\d+\)$/ });
  await historyButton.click();
  const dialog = page.getByRole("dialog", { name: "היסטוריית הרשומה" });
  const what = await dialog.locator(".history-what").allTextContents();
  expect(what[0]).toBe("נקלט");
  expect(what.at(-1)).toBe("אושר");
  for (const [name, field] of Object.entries(record!.fields)) {
    if (field.needs_review) expect(what.join("|")).toMatch(new RegExp(`(תוקן|סומן כנבדק): ${FIELD_TITLES[name]}`));
  }
  await expect(dialog.locator(".history-who").last()).toHaveText(`על ידי ${me.display_name}`);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(historyButton).toBeFocused();
});

test("deleting from a record's page asks first; no keeps it, yes deletes it and goes back", async ({ page }) => {
  const record = uploaded.find((r) => r.status === "pending" && r.record_id !== uploaded.find(fixable)?.record_id);
  test.skip(!record, "no second pending record");
  await signIn(page);
  await page.goto(`/records/${record!.record_id}`);
  const remove = page.locator(".record-actions").getByRole("button", { name: "מחיקה" });

  page.once("dialog", (dialog) => {
    expect(dialog.message()).toContain("למחוק את הרשומה");
    void dialog.dismiss();
  });
  await remove.click();
  await expect(page).toHaveURL(new RegExp(`/records/${record!.record_id}$`));
  expect((await page.request.get(`/api/v1/records/${record!.record_id}`)).status()).toBe(200);

  page.once("dialog", (dialog) => void dialog.accept());
  await remove.click();
  await expect(page).toHaveURL(/\/records$/);
  expect((await page.request.get(`/api/v1/records/${record!.record_id}`)).status()).toBe(404);
});

test("a record that does not exist says so, with the way back", async ({ page }) => {
  await signIn(page);
  await page.goto("/records/no-such-record");
  await expect(page.getByText("הרשומה לא נמצאה. ייתכן שנמחקה.")).toBeVisible();
  await page.getByRole("link", { name: "→ חזרה לרשומות" }).click();
  await expect(page).toHaveURL(/\/records$/);
});
