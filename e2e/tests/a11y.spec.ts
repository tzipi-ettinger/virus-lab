// Accessibility: every screen, checked by axe-core against WCAG 2.0 levels A and AA
// (the level Israel's standard 5568 adopts for websites), on a desktop and on a
// phone. The screens are checked with content: a few forms are uploaded first.
//
// "e2e-a11y.pdf" has four blank pages; the fake provider answers them with
// fixtures 04 to 07 (two central numbers, a wrong date, no commitment, a misread
// ID), so the review and records screens show their warnings too.
//
// axe finds about a third of WCAG problems; keyboard use and screen-reader
// wording still need a person (docs/ACCESSIBILITY.md).
// Owner: shared

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { blankPdf } from "./blankPdf";
import { measureContrast } from "./contrast";
import { requirePassword, signIn } from "./session";

const FORMS = { name: "e2e-a11y.pdf", mimeType: "application/pdf", buffer: blankPdf(4) };
const WCAG_2_0_AA = ["wcag2a", "wcag2aa"];

test.beforeAll(requirePassword);
// Each screen's unmeasured text is photographed one element at a time.
test.setTimeout(180_000);

// Without it, axe can measure an element halfway through a fade-in and report its
// contrast at half opacity. The app honours prefers-reduced-motion, so this is a
// real way users see it.
test.use({ reducedMotion: "reduce" });

/** Every WCAG 2.0 A/AA violation on the page as it is now, one readable line each. */
async function expectAccessible(page: Page, screen: string) {
  await page.waitForLoadState("networkidle");
  await page.mouse.move(0, 0); // no hover color on whatever was clicked last
  const { violations, incomplete } = await new AxeBuilder({ page }).withTags(WCAG_2_0_AA).analyze();
  const found = violations.map(
    (v) =>
      `${v.id} [${v.impact}] ${v.help} (${v.nodes.length}×): ` +
      v.nodes
        .slice(0, 3)
        .map((node) => node.target.join(" "))
        .join(" | "),
  );

  // The text axe couldn't measure (a gradient or a stripe behind it), measured here.
  const unmeasured = incomplete.find((result) => result.id === "color-contrast")?.nodes ?? [];
  for (const node of unmeasured) {
    const selector = node.target.join(" ");
    const contrast = await measureContrast(page, selector);
    if (contrast && contrast.ratio < contrast.required) {
      found.push(`color-contrast ${selector}: ${contrast.ratio.toFixed(2)}:1, needs ${contrast.required}:1`);
    }
  }

  // Soft: one run reports every screen, not only the first that fails.
  expect.soft(found, `${screen}: WCAG 2.0 AA violations`).toEqual([]);
}

async function walkEveryScreen(page: Page) {
  await page.goto("/login");
  await expect(page.getByLabel("שם משתמש")).toBeVisible();
  await expectAccessible(page, "login");

  await signIn(page);
  await expect(page).toHaveURL(/\/upload$/);
  await expectAccessible(page, "upload, empty");

  // Once the file is read, the screen moves to the review table on its own.
  await page.locator("input[type=file]").setInputFiles(FORMS);
  const row = page.locator(".upload-item", { hasText: FORMS.name });
  await expect(row).toHaveClass(/is-done/, { timeout: 60_000 });
  await expect(page.getByRole("table").first()).toBeVisible();
  await expectAccessible(page, "review");

  await page.getByRole("button", { name: /העלאת קבצים נוספים/ }).click();
  await expect(row).toBeVisible();
  await expectAccessible(page, "upload, done");

  await page.goto("/records");
  const firstRecord = page.getByRole("row").nth(1);
  await expect(firstRecord).toBeVisible();
  await expectAccessible(page, "records");

  await firstRecord.getByRole("link").first().click();
  await expect(page).toHaveURL(/\/records\/[^/?]+$/);
  await expectAccessible(page, "record");

  await page.goto("/stats");
  await expectAccessible(page, "stats");

  await page.goto("/");
  await expectAccessible(page, "landing");

  await page.goto("/no-such-page");
  await expectAccessible(page, "not found");
}

test("every screen meets WCAG 2.0 AA on a desktop", async ({ page }) => {
  await walkEveryScreen(page);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

  test("every screen meets WCAG 2.0 AA on a phone", async ({ page }) => {
    await walkEveryScreen(page);
  });
});
