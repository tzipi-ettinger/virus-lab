// The whole path a user takes, through the real server and database: sign in,
// upload a form, find its record, open it, export it, sign out.
//
// The server runs with EXTRACTION_PROVIDER=fake: each page gets a fixture from
// backend/tests/fixtures/extraction, picked by the file name. "e2e-sample.pdf"
// page 1 gets 01_meuhedet_clean.json, so its record is known in advance. The page
// itself is blank: the fake provider never looks at it.
// Owner: shared

import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { blankPdf } from "./blankPdf";

const SAMPLE = { name: "e2e-sample.pdf", mimeType: "application/pdf", buffer: blankPdf() };
// From 01_meuhedet_clean.json. The model "read" a 10-digit ID; the rules drop the
// extra leading zero and flag it, and the raw reading stays on the record.
const COMMITMENT = "730578626";
const RAW_NATIONAL_ID = "0011223344";
const NATIONAL_ID = "011223344";

const USER = process.env.E2E_USER ?? "e2e";
const PASSWORD = process.env.E2E_PASSWORD ?? "";

test.beforeAll(() => {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD to the password of E2E_USER (default: e2e)");
});

async function signIn(page: Page) {
  await page.getByLabel("שם משתמש").fill(USER);
  await page.getByLabel("סיסמה", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: /^כניסה/ }).click();
}

test("sign in, upload, find the record, export it, sign out", async ({ page }) => {
  // Every screen is behind sign-in, and signing in opens the upload.
  await page.goto("/records");
  await expect(page).toHaveURL(/\/login$/);
  await signIn(page);
  await expect(page).toHaveURL(/\/upload$/);

  // Upload: the file is read and saved as one pending record.
  await page.locator("input[type=file]").setInputFiles(SAMPLE);
  const row = page.locator(".upload-item", { hasText: "e2e-sample.pdf" });
  await expect(row).toHaveClass(/is-done/, { timeout: 60_000 });
  await expect(row).toContainText("רשומה אחת");

  // The records screen finds it by its commitment number.
  await page.goto(`/records?q=${COMMITMENT}`);
  const record = page.getByRole("row", { name: new RegExp(COMMITMENT) }).first();
  await expect(record).toBeVisible();

  // Its page shows the fields as the server saved them.
  await record.getByRole("link").first().click();
  await expect(page).toHaveURL(/\/records\/[^/?]+$/);
  const recordUrl = page.url();
  await expect(page.getByText(RAW_NATIONAL_ID, { exact: true }).first()).toBeVisible();

  // The CSV export of the filtered list holds it.
  await page.goto(`/records?q=${COMMITMENT}`);
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "CSV" }).click(),
  ]);
  const csv = await readFile(await download.path(), "utf-8");
  expect(csv).toContain(`,${COMMITMENT},`);
  expect(csv).toContain(`,${NATIONAL_ID},`); // as text: the leading zero stays

  // Signing out ends the session: the records are behind sign-in again.
  await page.getByRole("button", { name: "יציאה" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/records");
  await expect(page).toHaveURL(/\/login$/);

  // A link to a record opens that record once signed in.
  await page.goto(recordUrl);
  await expect(page).toHaveURL(/\/login$/);
  await signIn(page);
  await expect(page).toHaveURL(recordUrl);
  await expect(page.getByText(RAW_NATIONAL_ID, { exact: true }).first()).toBeVisible();
});

test("a wrong password is refused, and no records are shown", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("שם משתמש").fill(USER);
  await page.getByLabel("סיסמה", { exact: true }).fill(`${PASSWORD}-wrong`);
  await page.getByRole("button", { name: /^כניסה/ }).click();

  await expect(page.getByText("שם המשתמש או הסיסמה שגויים")).toBeVisible();
  const answer = await page.request.get("/api/v1/records");
  expect(answer.status()).toBe(401);
});
